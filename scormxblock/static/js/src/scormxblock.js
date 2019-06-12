var csrftoken;

function ScormXBlock_${block_id}(runtime, element) {

  function SCORM_API(){

    this.LMSInitialize = function(){
      console.log('LMSInitialize');
      return true;
    };

    this.LMSFinish = function() {
      console.log("LMSFinish");
      return "true";
    };

    this.LMSGetValue = function(cmi_element) {
      console.log("Getvalue for " + cmi_element);
      var handlerUrl = runtime.handlerUrl(element, 'scorm_get_value');

      var response = $.ajax({
        type: "POST",
        url: handlerUrl,
        data: JSON.stringify({'name': cmi_element}),
        async: false
      });
      response = JSON.parse(response.responseText);
      return response.value
    };

    this.LMSSetValue = function(cmi_element, value) {
      console.log("LMSSetValue " + cmi_element + " = " + value);
      var handlerUrl = runtime.handlerUrl(element, 'scorm_set_value');

      if (cmi_element == 'cmi.core.lesson_status'||cmi_element == 'cmi.core.score.raw'){

        $.ajax({
          type: "POST",
          url: handlerUrl,
          data: JSON.stringify({'name': cmi_element, 'value': value}),
          async: false,
          success: function(response){
            if (typeof response.lesson_score != "undefined"){
              $(".lesson_score", element).html(response.lesson_score);
            }
          }
        });

      }
      return true;
    };

    /*
    TODO: this is all racoongang stubs
    this.LMSCommit = function() {
        console.log("LMSCommit");
        return "true";
    };

    this.LMSGetLastError = function() {
      console.log("GetLastError");
      return "0";
    };

    this.LMSGetErrorString = function(errorCode) {
      console.log("LMSGetErrorString");
      return "Some Error";
    };

    this.LMSGetDiagnostic = function(errorCode) {
      console.log("LMSGetDiagnostic");
      return "Some Diagnostice";
    }
    */

  }

  $(function ($) {
    API = new SCORM_API();
    console.log("Initial SCORM data...");
    const completedFeedbackText = gettext('Content is complete, please continue.');
    const incompleteFeedbackText = gettext('Complete all content to continue.');
    const completionButtonTitle = gettext('Check for Completion');

    //post message with data to player frame
    //player must be in an iframe and not a popup due to limitations in Internet Explorer's postMessage implementation
    host_frame_${block_id} = $('#scormxblock-${block_id}');
    host_frame_${block_id}.data('csrftoken', $.cookie('csrftoken'));

    disablePopupIfMobile()
    if (host_frame_${block_id}.data('display_type') == 'iframe') {
      // Iframe
      host_frame_${block_id}.css('height', host_frame_${block_id}.data('display_height') + 'px');
      $('.scorm_launch button').css('display', 'none');
      showCompletionIfGatingEnabled();
      showScormContent(host_frame_${block_id});
    }
    else if (isAutoPopup()){
      // Auto popup
      $('.scorm_launch button').css('display', 'none');
      showScormContent(host_frame_${block_id});
    }
    else{
      // Manual popup
      launch_btn_${block_id} = $('#scorm-launch-${block_id}');
      launch_btn_${block_id}.on('click', function() {
        showScormContent(host_frame_${block_id});
        launch_btn_${block_id}.attr('disabled','true');
      });
      $(host_frame_${block_id}).on('unload', function() {
        launch_btn_${block_id}.removeAttr('disabled');
      })
    }

    function showCompletionIfGatingEnabled() {
      let isGatingEnabled = $('#scormxblock-${block_id}').attr('data-is_next_module_locked');
      if (isGatingEnabled === 'True') {
        $('#scorm-gating-${block_id}').removeAttr('hidden');
        $('#scorm-check-completion-${block_id}').text(completionButtonTitle);
      }
    }

    if (host_frame_${block_id}.data('is_next_module_locked') == "True") {
      // This function resides in apros, since most of the functionality is related to apros
      try{
        disableNextModuleArrow();
      }
      catch(error){
        console.log('disableNextModuleArrow() not defined');
      }

    }

    $('#scorm-check-completion-${block_id}').on('click', function(){
      // Empty feedback text
      // Update completion on backend by triggering the set_raw_scorm_status call
      $('#scorm-completion-feedback-${block_id}').text('');
      host_frame_${block_id}.attr('src', '');
      host_frame_${block_id}.attr('src', host_frame_${block_id}.data('player_url'));
      evaluateCompletion();
    })

    function evaluateCompletion()
    {
      // Interval of 2 seconds to let completion be updated at backend
      window.setTimeout(function(){
        $.ajax({
          type: 'POST',
          url: host_frame_${block_id}.data('get_completion_url'),
          content_type: 'application/json'
        }).done(function(data, status, xhr){
          if (xhr.status == 200) {
            let completion = 'completion' in data ? data.completion : 0;
            disableGatingOnCompletion(completion);
          }
        })
      }, 2 * 1000)
    }

    function disableGatingOnCompletion(completion) {
      if (completion === 1) {
        setFeedbackText(completedFeedbackText);
        unsetGatingFlagInIframe();
        if (shouldEnableRightArrowButton()) {
          // Function on Apros side course_lesson.js
          try{
            enableNextModuleArrow();
          }
          catch(error){
            console.log('enableNextModuleArrow() not defined');
          }

        }
      }
      else {
        setFeedbackText(incompleteFeedbackText);
      }
    }

    function setFeedbackText(feedbackText) {
      $('#scorm-completion-feedback-${block_id}').text(feedbackText);
    }

    function unsetGatingFlagInIframe() {
      host_frame_${block_id}.data('is_next_module_locked', "False");
      host_frame_${block_id}.attr('data-is_next_module_locked', "False");
    }

    function shouldEnableRightArrowButton() {
      // Check if other scorm iframes in the same page have gating applied
      // and are not yet complete
      let allScormIframesInPage = $('.scormxblock_hostframe')
      for (i=0; i<allScormIframesInPage.length; i=i+1) {
        let scorm_id = allScormIframesInPage[i].id;
        if ($('#' + scorm_id).attr('data-is_next_module_locked') === 'True') {
          return false;
        }
      }
      return true;
    }

    document.handleScormPopupClosed = function() {
      launch_btn = $('.scorm_launch button');
      launch_btn.removeAttr('disabled');

      // Changing src to empty exits the ssla player. This is done for
      // saving user data.
      host_frame_${block_id}.attr('src','');
      if (isAutoPopup()){
        launch_btn.css('display', 'inline-block');
        launch_btn.on('click', function() {
            showScormContent(host_frame_${block_id});
            launch_btn.attr('disabled','true');
        });
      }

      if (host_frame_${block_id}.data('is_next_module_locked') == "True") {
      // If gating is applied
        evaluateCompletion();
      }
    }

    function isAutoPopup(){
      if ((host_frame_${block_id}.data('display_type') == 'popup') && (host_frame_${block_id}.data('popup_launch_type') == 'auto')){
        return true;
      }
      return false;
    }

    function showScormContent(host_frame) {
      if (isAutoPopup()) {
        var launch_btn = $('.scorm_launch button');
        launch_btn.attr('disabled','true');
        launch_btn.css('display', 'inline-block');
      }
      playerWin = null;
      host_frame.attr('src',host_frame.data('player_url'));
      $(host_frame).on('load', function() {
        playerWin = host_frame[0].contentWindow;
        playerWin.postMessage(host_frame.data(), '*');
      });
    }

    function disablePopupIfMobile() {
      var isRNApp = (/com.mcka.RNApp/i.test(navigator.userAgent.toLowerCase()));
      if (isRNApp) {
        host_frame_${block_id}.data('display_type', 'iframe')
        host_frame_${block_id}.attr('data-display_type', 'iframe')
      }
    }
  });
}
