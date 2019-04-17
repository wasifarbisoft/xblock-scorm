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

    //post message with data to player frame
    //player must be in an iframe and not a popup due to limitations in Internet Explorer's postMessage implementation
    host_frame_${block_id} = $('#scormxblock-${block_id}');
    host_frame_${block_id}.data('csrftoken', $.cookie('csrftoken'));
    if (host_frame_${block_id}.data('display_type') == 'iframe') {
      host_frame_${block_id}.css('height', host_frame_${block_id}.data('display_height') + 'px');
      $('.scorm_launch button').css('display', 'none');
      showScormContent(host_frame_${block_id})
    }
    else if (isAutoPopup()){
      $('.scorm_launch button').css('display', 'none');
      showScormContent(host_frame_${block_id})
    }
    else{
      launch_btn_${block_id} = $('#scorm-launch-${block_id}');
      launch_btn_${block_id}.on('click', function() {
        showScormContent(host_frame_${block_id})
        launch_btn_${block_id}.attr('disabled','true')
        });
      $(host_frame_${block_id}).on('unload', function() {
        launch_btn_${block_id}.removeAttr('disabled');
      })
    }

    if (host_frame_${block_id}.data('is_next_module_locked') == "True") {
      disableNextModuleArrow();
    }
    document.handleScormPopupClosed = function() {
      launch_btn = $('.scorm_launch button');
      launch_btn.removeAttr('disabled');
      // Changing src to empty exits the ssla player. Done for
      // saving user data and smooth second launch.
      host_frame_${block_id}.attr('src','');
      if (isAutoPopup()){
        launch_btn.css('display', 'inline-block');
        launch_btn.on('click', function() {
            showScormContent(host_frame_${block_id})
            launch_btn.attr('disabled','true')
        });
      }
    }

    function isAutoPopup(){
      if ((host_frame_${block_id}.data('display_type') == 'popup') && (host_frame_${block_id}.data('popup_launch_type') == 'auto')){
        return true;
      }
      return false;
    }

    function disableNextModuleArrow() {
      if (isNewUI()) {
        disableNextModuleArrowForNewUI();
      }
      else {
        disableNextModuleArrowForOldUI();
      }
    }

    function isNewUI() {
      return $("body").hasClass("new-theme");
    }

    function disableNextModuleArrowForOldUI() {
      var nextModuleLink = $(".controls .next");
      if (isNextLinkAlreadyDisabled(nextModuleLink)) return;
      nextModuleLink.addClass("complete-scorm future");
      nextModuleLink.attr("href", "javascript:void()");

      var completionPopup = document.createElement('div');
      completionPopup.className = "complete-scorm-content";
      completionPopup.innerHTML = '<i class="fa fa-lock"></i>Complete all content to unlock';

      $(".controls .next .mcka-tooltip").prepend(completionPopup);
    }

    function disableNextModuleArrowForNewUI() {
      var nextModuleLink = $(".controls .right");
      if (isNextLinkAlreadyDisabled(nextModuleLink)) return;

      nextModuleLink.addClass("disable");
      nextModuleLink.attr("href", "javascript:void()");
      var completionPopupContent = '<i class=material-icons locked>lock</i><b>Complete all content to unlock<br></b>';
      var popupContent = $(".controls .right span").attr("data-content");

      $(".controls .right span").attr("data-content", completionPopupContent + popupContent);
    }

    function isNextLinkAlreadyDisabled(nextModuleLink) {
      var nextLinkValue = nextModuleLink.attr("href");
      // No need to do anything since next link is already disabled
      return nextLinkValue == "#" || nextLinkValue == "javascript:void()";
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
  });


}
