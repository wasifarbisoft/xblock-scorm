from __future__ import absolute_import

import encodings
import json
import logging
import mimetypes
import os
from datetime import datetime

import pkg_resources
import pytz
import six
from django.conf import settings
from django.core.files.storage import default_storage
from django.http import QueryDict
from mako.template import Template as MakoTemplate
from six.moves import range
from webob import Response
from xblock.core import XBlock
from xblock.fields import Boolean, DateTime, Float, Integer, Scope, String
from xblock.fragment import Fragment

from openedx.core.lib.xblock_utils import add_staff_markup
from util.date_utils import get_default_time_display

from . import constants
from .scorm_file_uploader import STATE as UPLOAD_STATE
from .scorm_file_uploader import ScormPackageUploader


# Make '_' a no-op so we can scrape strings
def _(text):
    return text


logger = logging.getLogger(__name__)

# importing directly from settings.XBLOCK_SETTINGS doesn't work here... doesn't have vals from ENV TOKENS yet
scorm_settings = settings.ENV_TOKENS['XBLOCK_SETTINGS']['ScormXBlock'] if hasattr(settings, 'ENV_TOKENS') else {}
DEFINED_PLAYERS = scorm_settings.get("SCORM_PLAYER_BACKENDS", {})
SCORM_STORAGE = scorm_settings.get("SCORM_PKG_STORAGE_DIR", "scorms")
SCORM_DISPLAY_STAFF_DEBUG_INFO = scorm_settings.get("SCORM_DISPLAY_STAFF_DEBUG_INFO", False)
SCORM_PKG_INTERNAL = {"value": "SCORM_PKG_INTERNAL", "display_name": "Internal Player: index.html in SCORM package"}
DEFAULT_SCO_MAX_SCORE = 100
DEFAULT_IFRAME_WIDTH = 800
DEFAULT_IFRAME_HEIGHT = 400

AVAIL_ENCODINGS = encodings.aliases.aliases


@XBlock.needs('i18n')
class ScormXBlock(XBlock):
    has_score = True
    has_author_view = True
    has_custom_completion = True

    display_name = String(
        display_name=_("Display Name"),
        help=_("Display name for this module"),
        default="SCORM",
        scope=Scope.settings
    )
    description = String(
        display_name=_("Description"),
        help=_("Brief description of the SCORM modules will be displayed above the player. Can contain HTML."),
        default="",
        scope=Scope.settings
    )
    scorm_file = String(
        display_name=_("Upload scorm file (.zip)"),
        help=_('Upload a new SCORM package.'),
        scope=Scope.settings
    )
    scorm_player = String(
        values=[{"value": key, "display_name": DEFINED_PLAYERS[key]['name']} for key in DEFINED_PLAYERS.keys()] +
               [SCORM_PKG_INTERNAL, ],
        display_name=_("SCORM player"),
        help=_("SCORM player configured in Django settings, or index.html file contained in SCORM package"),
        scope=Scope.settings
    )
    # this stores latest raw SCORM API data in JSON string
    raw_scorm_status = String(
        scope=Scope.user_state,
        default='{}'
    )
    scorm_initialized = Boolean(
        scope=Scope.user_state,
        default=False
    )
    lesson_status = String(
        scope=Scope.user_state,
        default='not attempted'
    )
    lesson_score = Float(
        scope=Scope.user_state,
        default=0
    )
    scorm_progress = Float(
        scope=Scope.user_state,
        default=0
    )
    weight = Integer(
        default=1,
        help=_('SCORM block\'s problem weight in the course, in points.  If not graded, set to 0'),
        scope=Scope.settings
    )
    auto_completion = Boolean(
        display_name=_("Enable completion upon viewing SCORM file"),
        default=False,
        scope=Scope.settings
    )
    is_next_module_locked = Boolean(
        display_name=_("Locking"),
        help=_('Enable requirement to complete SCORM content before moving to next module'),
        default=False,
        scope=Scope.settings,
    )
    display_type = String(
        display_name=_("Display Type"),
        values=["iframe", "popup"],
        default="iframe",
        help=_("Open in a new popup window, or an iframe.  This setting may be overridden by "
               "player-specific configuration."),
        scope=Scope.settings
    )
    popup_launch_type = String(
        display_name=_("Popup Launch Type"),
        values=["auto", "manual"],
        default="auto",
        help=_("Open in a new popup through button or automatically."),
        scope=Scope.settings
    )
    launch_button_text = String(
        display_name=_("Launch Button Text"),
        help=_("Display text for Launch Button"),
        default="Launch",
        scope=Scope.settings
    )
    display_width = Integer(
        display_name=_("Display Width (px)"),
        help=_('Width of iframe or popup window'),
        default=820,
        scope=Scope.settings
    )
    display_height = Integer(
        display_name=_("Display Height (px)"),
        help=_('Height of iframe or popup window'),
        default=450,
        scope=Scope.settings
    )
    encoding = String(
        display_name=_("SCORM Package text encoding"),
        default='cp850',
        help=_("Character set used in SCORM package.  Defaults to cp850 (or IBM850), "
               "for Latin-1: Western European languages)"),
        values=[{"value": AVAIL_ENCODINGS[key], "display_name": key} for key in sorted(AVAIL_ENCODINGS.keys())],
        scope=Scope.settings
    )
    player_configuration = String(
        display_name=_("Player Configuration"),
        default='',
        help=_("JSON object string with overrides to be passed to selected SCORM player.  "
               "These will be exposed as data attributes on the host iframe and sent in a window.postMessage "
               "to the iframe's content window. Attributes can be any.  "
               "'Internal player' will always check this field for an 'initial_html' attribute "
               "to override index.html as the initial page."),
        scope=Scope.settings
    )
    scorm_file_name = String(
        display_name=_("Scorm File Name"),
        help=_("Scorm Package Uploaded File Name"),
        default="",
        scope=Scope.settings
    )
    file_uploaded_date = DateTime(
        default=None, scope=Scope.settings,
        help="Scorm File Last Uploaded Date"
    )

    @property
    def student_id(self):
        if hasattr(self, "scope_ids"):
            return self.scope_ids.user_id
        else:
            return None

    @property
    def student_name(self):
        if hasattr(self, "xmodule_runtime"):
            user = self.xmodule_runtime._services['user'].get_current_user()
            try:
                return user.display_name
            except AttributeError:
                return user.full_name
        else:
            return None

    @property
    def course_id(self):
        if hasattr(self, "xmodule_runtime"):
            return self._serialize_opaque_key(self.xmodule_runtime.course_id)
        else:
            return None

    def _reverse_student_name(self, name):
        parts = name.split(' ', 1)
        parts.reverse()
        return ', '.join(parts)

    def _serialize_opaque_key(self, key):
        if hasattr(key, 'to_deprecated_string'):
            return key.to_deprecated_string()
        else:
            return six.text_type(key)

    def resource_string(self, path):
        """Handy helper for getting resources from our kit."""
        data = pkg_resources.resource_string(__name__, path)
        return data.decode("utf8")

    def student_view(self, context=None, authoring=False):
        scheme = 'https' if settings.HTTPS == 'on' else 'http'
        lms_base = settings.ENV_TOKENS.get('LMS_BASE')
        if isinstance(context, QueryDict):
            context = context.dict()

        scorm_player_url = ""

        course_directory = self.scorm_file
        if self.scorm_player == 'SCORM_PKG_INTERNAL':
            # TODO: support initial filename other than index.html for internal players
            scorm_player_url = '{}://{}{}'.format(scheme, lms_base, self.scorm_file)
        elif self.scorm_player:
            player_config = DEFINED_PLAYERS[self.scorm_player]
            player = player_config['location']
            if '://' in player:
                scorm_player_url = player
            else:
                scorm_player_url = '{}://{}{}'.format(scheme, lms_base, player)
            course_directory = '{}://{}{}'.format(scheme, lms_base, self.runtime.handler_url(self, "proxy_content"))

        html = self.resource_string("static/html/scormxblock.html")

        # don't call handlers if student_view is not called from within LMS
        # (not really a student)
        if not authoring:
            get_url = '{}://{}{}'.format(scheme, lms_base, self.runtime.handler_url(self, "get_raw_scorm_status"))
            set_url = '{}://{}{}'.format(scheme, lms_base, self.runtime.handler_url(self, "set_raw_scorm_status"))
            get_completion_url = '{}://{}{}'.format(scheme, lms_base,
                                                    self.runtime.handler_url(self, "get_scorm_completion"))
        # PreviewModuleSystem (runtime Mixin from Studio) won't have a hostname
        else:
            # we don't want to get/set SCORM status from preview
            get_url = set_url = get_completion_url = '#'

        # if display type is popup, don't use the full window width for the host iframe
        iframe_width = self.display_type == 'popup' and DEFAULT_IFRAME_WIDTH or self.display_width
        iframe_height = self.display_type == 'popup' and DEFAULT_IFRAME_HEIGHT or self.display_height
        show_popup_manually = self.display_type == 'popup' and self.popup_launch_type == 'manual'
        lock_next_module = self.is_next_module_locked and self.scorm_progress < constants.MAX_PROGRESS_VALUE
        try:
            player_config = json.loads(self.player_configuration)
        except ValueError:
            player_config = {}

        frag = Fragment()
        frag.add_content(MakoTemplate(text=html.format(self=self, scorm_player_url=scorm_player_url,
                                                       get_url=get_url, set_url=set_url,
                                                       get_completion_url=get_completion_url,
                                                       iframe_width=iframe_width, iframe_height=iframe_height,
                                                       player_config=player_config,
                                                       show_popup_manually=show_popup_manually,
                                                       scorm_file=course_directory,
                                                       is_next_module_locked=lock_next_module)
                                      ).render_unicode())

        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        context['block_id'] = self.url_name
        js = self.resource_string("static/js/src/scormxblock.js")
        jsfrag = MakoTemplate(js).render_unicode(**context)
        frag.add_javascript(jsfrag)

        # TODO: this will only work to display staff debug info if 'scormxblock' is one of the
        # categories of blocks that are specified in lms/templates/staff_problem_info.html so this will
        # for now have to be overridden in theme or directly in edx-platform
        # TODO: is there another way to approach this?  key's location.category isn't mutable to spoof 'problem',
        # like setting the name in the entry point to 'problem'.  Doesn't seem like a good idea.  Better to
        # have 'staff debuggable' categories configurable in settings or have an XBlock declare itself staff debuggable
        if SCORM_DISPLAY_STAFF_DEBUG_INFO and not authoring:  # don't show for author preview
            from courseware.access import has_access
            from courseware.courses import get_course_by_id

            course = get_course_by_id(self.xmodule_runtime.course_id)
            dj_user = self.xmodule_runtime._services['user']._django_user
            has_instructor_access = bool(has_access(dj_user, 'instructor', course))
            if has_instructor_access:
                disable_staff_debug_info = settings.FEATURES.get('DISPLAY_DEBUG_INFO_TO_STAFF', True) and False or True
                block = self
                view = 'student_view'
                frag = add_staff_markup(dj_user, has_instructor_access, disable_staff_debug_info,
                                        block, view, frag, context)

        frag.initialize_js('ScormXBlock_{0}'.format(context['block_id']))
        return frag

    def author_view(self, context=None):
        return self.student_view(context, authoring=True)

    def studio_view(self, context=None):
        html = self.resource_string("static/html/studio.html")
        frag = Fragment()
        file_uploaded_date = get_default_time_display(self.file_uploaded_date) if self.file_uploaded_date else ''
        context = {'block': self, 'file_uploaded_date': file_uploaded_date}
        frag.add_content(MakoTemplate(text=html).render_unicode(**context))
        frag.add_css(self.resource_string("static/css/scormxblock.css"))
        frag.add_javascript(self.resource_string("static/js/src/studio.js"))
        frag.add_javascript_url(self.runtime.local_resource_url(self, 'public/jquery.fileupload.js'))
        frag.initialize_js('ScormStudioXBlock')
        return frag

    @XBlock.handler
    def upload_status(self, request, suffix=''):
        """
        Scorm package upload to storage status
        """
        upload_percent = ScormPackageUploader.get_upload_percentage(self.location.block_id)

        logger.info('Upload percentage is: {}'.format(upload_percent))

        return Response(json.dumps({"progress": upload_percent}))

    @XBlock.handler
    def file_upload_handler(self, request, suffix=''):
        """
        Handler for scorm file upload
        """
        response = {}
        scorm_uploader = ScormPackageUploader(
            request=request, xblock=self,
            scorm_storage_location=SCORM_STORAGE
        )

        try:
            state, data = scorm_uploader.upload()
        except Exception as e:
            logger.error('Scorm package upload error: {}'.format(e.message))
            ScormPackageUploader.clear_percentage_cache(self.location.block_id)
            return Response(json.dumps({'status': 'error', 'message': e.message}))

        if state == UPLOAD_STATE.PROGRESS:
            response = {"files": [{
                "size": data
            }]}
        elif state == UPLOAD_STATE.COMPLETE and data:
            ScormPackageUploader.clear_percentage_cache(self.location.block_id)
            self.scorm_file = data
            response = {'status': 'OK'}

        return Response(json.dumps(response))

    @XBlock.handler
    def studio_submit(self, request, suffix=''):
        self.display_name = request.params['display_name']
        self.description = request.params['description']
        self.weight = request.params['weight']
        self.display_width = request.params['display_width']
        self.display_height = request.params['display_height']
        self.display_type = request.params['display_type']
        self.launch_button_text = request.params['launch_button_text']
        self.popup_launch_type = request.params['popup_launch_type']
        self.scorm_player = request.params['scorm_player']
        self.encoding = request.params['encoding']
        self.auto_completion = request.params['auto_completion']
        self.is_next_module_locked = request.params['is_next_module_locked']
        if request.params['new_scorm_file_uploaded'] == 'true':
            self.scorm_file_name = request.params['scorm_file_name']
            self.file_uploaded_date = datetime.utcnow().replace(tzinfo=pytz.utc)

        if request.params['player_configuration']:
            try:
                json.loads(request.params['player_configuration'])  # just validation
                self.player_configuration = request.params['player_configuration']
            except ValueError as e:
                return Response(json.dumps({'result': 'failure',
                                            'error': 'Invalid JSON in Player Configuration'.format(e)}),
                                content_type='application/json')

        return Response(json.dumps({'result': 'success'}), content_type='application/json')

    # if player sends SCORM API JSON directly
    @XBlock.json_handler
    def scorm_get_value(self, data, suffix=''):
        name = data.get('name')
        if name == 'cmi.core.lesson_status':
            return {'value': self.lesson_status}
        return {'value': ''}

    # if player sends SCORM API JSON directly
    @XBlock.json_handler
    def scorm_set_value(self, data, suffix=''):
        context = {'result': 'success'}
        name = data.get('name')
        if name == 'cmi.core.lesson_status' and data.get('value') != 'completed':
            self.lesson_status = data.get('value')
            self._publish_grade()
            context.update({"lesson_score": self.lesson_score})
        if name == 'cmi.core.score.raw':
            self._set_lesson_score(data.get('value', 0))
        return context

    def _get_all_scos(self):
        return json.loads(self.raw_scorm_status).get('scos', None)

    def _status_serialize_key(self, key, val):
        """
        update value in JSON serialized raw_scorm_status
        passing a string key and a deserialized object
        """
        status = json.loads(self.raw_scorm_status)
        status[key] = val
        self.raw_scorm_status = json.dumps(status)

    def _scos_set_values(self, key, val, overwrite=False):
        """
        set a value for a key on all scos
        return new full raw scorm data
        """
        scos = self._get_all_scos()
        if scos:
            for sco in scos:
                if not scos[sco].get('key') or (scos[sco].get('key') and overwrite):
                    scos[sco][key] = val
            self._status_serialize_key('scos', scos)

    def _init_scos(self):
        """
        initialize all SCOs with proper credit and status values in case
        content package does not do this correctly
        """

        # set all scos lesson status to 'not attempted'
        # set credit/no-credit on all scos
        credit = self.weight > 0 and 'credit' or 'no-credit'
        self._scos_set_values('cmi.core.credit', credit)
        self._scos_set_values('cmi.core.lesson_status', 'not attempted', True)
        self.scorm_initialized = True

    @XBlock.handler
    def get_raw_scorm_status(self, request, suffix=''):
        """
        retrieve JSON SCORM API status as stored by SSLA player (or potentially others)
        """
        # TODO: handle errors
        # TODO: this is specific to SSLA player at this point.  evaluate for broader use case
        response = Response(self.raw_scorm_status, content_type='application/json', charset='UTF-8')
        if self.auto_completion:
            # Mark 100% progress upon launching the scorm content if auto_completion is true
            self._publish_progress(constants.MAX_PROGRESS_VALUE)

        return response

    @XBlock.handler
    def set_raw_scorm_status(self, request, suffix=''):
        """
        store JSON SCORM API status from SSLA player (or potentially others)
        """
        # TODO: this is specific to SSLA player at this point.  evaluate for broader use case
        data = request.POST['data']
        scorm_data = json.loads(data)

        new_status = scorm_data.get('status', 'not attempted')

        if not self.scorm_initialized:
            self._init_scos()

        old_scorm_data = json.loads(self.raw_scorm_status)
        self.raw_scorm_status = data

        self.lesson_status = new_status
        score = scorm_data.get('score', '')
        self._publish_grade(new_status, score)
        self.publish_progress(old_scorm_data, scorm_data)
        self.save()

        # TODO: handle errors
        return Response(json.dumps(self.raw_scorm_status), content_type='application/json', charset='UTF-8')

    @XBlock.handler
    def get_scorm_completion(self, request, suffix=''):
        completion = {'completion': self.scorm_progress or 0}
        return Response(
            json.dumps(completion),
            content_type='application/json'
        )

    @XBlock.handler
    def proxy_content(self, request, suffix=''):
        storage = default_storage
        contents = ''
        content_type = 'application/octet-stream'
        path_to_file = os.path.join(SCORM_STORAGE, self.location.block_id, suffix)

        if storage.exists(path_to_file):
            f = storage.open(path_to_file, 'rb')
            contents = f.read()
            ext = os.path.splitext(path_to_file)[1]
            if ext in mimetypes.types_map:
                content_type = mimetypes.types_map[ext]
        else:
            return Response('Did not exist in storage: ' + path_to_file, status=404,
                            content_type='text/html', charset='UTF-8')
        return Response(contents, content_type=content_type)

    def generate_report_data(self, user_state_iterator, limit_responses=None):
        """
        Return a list of student responses to this block in a readable way.
        Arguments:
            user_state_iterator: iterator over UserStateClient objects.
                E.g. the result of user_state_client.iter_all_for_block(block_key)
            limit_responses (int|None): maximum number of responses to include.
                Set to None (default) to include all.
        Returns:
            each call returns a tuple like:
            ("username", {
                           "Question": "What's your favorite color?"
                           "Answer": "Red",
                           "Submissions count": 1
            })
        """

        count = 0
        for user_state in user_state_iterator:
            for report in self._get_user_report(user_state.state):

                if limit_responses is not None and count >= limit_responses:
                    # End the iterator here
                    return

                count += 1
                yield (user_state.username, report)

    def _get_user_report(self, user_state):
        interaction_prefix = "cmi.interactions."
        raw_status = json.loads(user_state['raw_scorm_status'])
        scos = raw_status.get('scos', {})

        for sco in scos.values():
            sco_data = sco.get('data') or {}
            interactions_count = sco_data.get(interaction_prefix + '_count', 0)

            for interaction_index in range(interactions_count):
                current_interaction_prefix = interaction_prefix + str(interaction_index) + "."

                report = {
                    self.ugettext('Question'): sco_data.get(current_interaction_prefix + "description"),
                    self.ugettext('Answer'): sco_data.get(current_interaction_prefix + "learner_response"),
                    self.ugettext('Submissions count'): interactions_count
                }
                yield report

    def _get_value_from_sco(self, sco, key, default):
        """
        return a set or default value from a key in a SCO
        treat blank string values as empty
        """
        try:
            val = sco[key]
        except (KeyError, ValueError):
            return default
        finally:
            if str(val) == '':
                return default
            else:
                return val

    def _set_lesson_score(self, scos):
        """
        roll up a total lesson score from an average of SCO scores
        """
        # note SCORM 2004+ supports complex weighting of scores from multiple SCOs
        # see http://scorm.com/blog/2009/10/score-rollup-in-scorm-1-2-theres-no-silver-bullet/
        # For now we will weight each SCO equally and take an average
        # TODO: handle more complex weighting when we support SCORM2004+
        total_score = 0
        for sco in scos.keys():
            sco = scos[sco]['data']
            total_score += int(self._get_value_from_sco(sco, 'cmi.core.score.raw', 0))
        score_rollup = float(total_score) / float(len(list(scos.keys())))
        self.lesson_score = score_rollup
        return score_rollup

    def _publish_grade(self, status, score):
        """
        publish the grade in the LMS.
        """

        # We must do this regardless of the lesson
        # status to avoid race condition issues where a grade of None might overwrite a
        # grade value for incomplete lesson statuses.

        # translate the internal score as a percentage of block's weight
        # we are assuming here the best practice for SCORM 1.2 of a max score of 100
        # if we weren't dealing with KESDEE publisher's incorrect usage of cmi.core.score.max
        # we could compute based on a real max score
        # in practice, SCOs will almost certainly have a max of 100
        # http://www.ostyn.com/blog/2006/09/scoring-in-scorm.html
        # TODO: handle variable max scores when we support SCORM2004+ or a better KESDEE workaround
        if score != '':
            self.runtime.publish(
                self,
                'grade',
                {
                    'value': (float(score) / float(DEFAULT_SCO_MAX_SCORE)) * self.weight,
                    'max_value': self.weight,
                })

    def publish_progress(self, old_scorm_data, current_scorm_data):
        """
        Update progress % if cmi.progress_measure is emitted (i.e. it exists)
        Else check status and mark 100% completion if course is complete
        """
        progress_measure = self.calculate_progress_measure(current_scorm_data)
        if progress_measure:
            # We do not want the elif to run if progress_measure exits but is invalid
            if self.is_progress_measure_valid(progress_measure, old_scorm_data):
                self._publish_progress(progress_measure)
        elif current_scorm_data.get('status', '') in constants.SCORM_COMPLETION_STATUS:
            self._publish_progress(constants.MAX_PROGRESS_VALUE)

    def _publish_progress(self, completion):
        """
        Update completion by calling the completion API
        """
        self.scorm_progress = completion
        self.runtime.publish(self, 'completion', {'completion': completion})

    def calculate_progress_measure(self, scorm_data):
        """
        Returns the averaged progress_measure of all scos in the current scorm content
        :return: progress_measure if found, else 0
        """
        progress_sum = 0
        scos = scorm_data.get('scos', {})
        for sco in scos.values():
            sco_data = sco.get('data', {})
            try:
                progress_sum += float(sco_data.get('cmi.progress_measure', '0.0'))
            except (ValueError, AttributeError):
                pass

        return progress_sum / len(scos) if len(scos) else 0

    def is_progress_measure_valid(self, current_progress_measure, old_scorm_data):
        """
        - Checks if the current progress (to be updated on the LMS) is greater than
        the previously stored progress
        - This is done to ensure that restarting a scorm course does not resets its
        progress on our LMS
        """
        if old_scorm_data:
            # If old data exists for comparison
            old_progress_measure = self.calculate_progress_measure(old_scorm_data)
            if old_progress_measure:
                if current_progress_measure > old_progress_measure:
                    return True
            return False
        else:
            # If nothing to compare, return valid
            return True

    @staticmethod
    def workbench_scenarios():
        """A canned scenario for display in the workbench."""
        return [
            ("ScormXBlock",
             """<vertical_demo>
                <scormxblock/>
                </vertical_demo>
             """),
        ]
