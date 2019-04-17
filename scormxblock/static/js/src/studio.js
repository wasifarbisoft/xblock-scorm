function ScormStudioXBlock(runtime, element) {
  var new_scorm_file_uploaded = false;
  var handlerUrl = runtime.handlerUrl(element, 'studio_submit');
  var fileUploadUrl = runtime.handlerUrl(element, 'file_upload_handler');
  var pollingParams = {id: null, interval: 5000, url: runtime.handlerUrl(element, 'upload_status')};

  function log(msg){
    console.log(msg);
  }

  function updateProgressUI(step, percentVal) {
    if(step)
        $(element).find('.current-step').text(step);
    $(element).find('.progress-container .bar').css({width: percentVal});
    $(element).find('.status-container .progress-percent').text(percentVal);
  }
  
  function pollUploadStatus() {
    $.getJSON(pollingParams.url, function(data) {
      var percentVal = data.progress + '%';
      updateProgressUI('Unpack and Storing', percentVal);

      if(percentVal == '100%'){
        clearInterval(pollingParams.id);
        $(element).find('.status-container .success-msg').text('Scorm package has been succesfully uploaded!');
         $(element).find('.save-button').removeClass('disabled');
          new_scorm_file_uploaded = true;
      }else{
        pollingParams.id = setTimeout(pollUploadStatus, pollingParams.interval);
      }
    });
  }
  
  $(element).find('#scorm-file-select').bind('click', function(e) {
    e.preventDefault();
    $('#scorm_file').click();
  });

  $(element).find('#scorm_file').fileupload({
    dataType: 'json',
    type: 'POST',
    maxChunkSize: 20 * 1000000, // 20 MB
    autoUpload: false,
    url: fileUploadUrl,
    add: function(e, data) {
      var file = data.files[0];

      $(element).find('#scorm_file_name').text(file.name);
      $(element).find('#scorm-file-select').hide();
      $(element).find('.file-chosen').text('File Chosen: ' + file.name);
      $(element).find('.status-container').show();
      $(element).find('.save-button').addClass('disabled');

      data.submit().complete(function(result, textStatus, xhr) {
          if(result.status == 'error'){
            alert('Error while uploading scorm package: ' + result.message);

            $(element).find('.file-chosen').text('');
            $(element).find('#scorm-file-select').show();
            $(element).find('.status-container').hide();
            $(element).find('.save-button').removeClass('disabled')
          }
      });

    },
    progressall: function(e, data) {
      var percentInt = data.loaded / data.total * 100,
                    percentVal = parseInt(percentInt, 10) + '%',
                    doneAt=95;

      updateProgressUI('Uploading', percentVal);

      if(percentInt >= doneAt){
        pollingParams.id = setTimeout(pollUploadStatus, 3000);
      }
    }
  });

  $(element).find('.save-button').bind('click', function() {
    var form_data = new FormData();
    var file_data = $(element).find('#scorm_file').prop('files')[0];
    var display_name = $(element).find('input[name=display_name]').val();
    var description = $(element).find('textarea[name=description]').val();
    var weight = $(element).find('input[name=weight]').val();
    var display_width = $(element).find('input[name=display_width]').val();
    var display_height = $(element).find('input[name=display_height]').val();
    var display_type = $(element).find('input[name=display_type]:checked').val();
    var popup_launch_type = $(element).find('input[name=popup_launch_type]:checked').val();
    var launch_button_text = $(element).find('input[name=launch_button_text]').val();
    var scorm_player = $(element).find('select[name=scorm_player]').val();
    var encoding = $(element).find('select[name=encoding]').val();
    var auto_completion = $(element).find('input[name=auto_completion]').is(':checked');
    var is_next_module_locked = $(element).find('input[name=is_next_module_locked]').is(':checked');
    var player_configuration = $(element).find('textarea[name=player_configuration]').val();
    var scorm_file_name = $(element).find('#scorm_file_name').text();
    if (!launch_button_text){
      launch_button_text = 'Launch'
    }
    form_data.append('file', file_data);
    form_data.append('display_name', display_name);
    form_data.append('description', description);
    form_data.append('display_width', display_width);
    form_data.append('display_height', display_height);
    form_data.append('weight', weight);
    form_data.append('display_type', display_type);
    form_data.append('popup_launch_type', popup_launch_type);
    form_data.append('launch_button_text', launch_button_text);
    form_data.append('scorm_player', scorm_player);
    form_data.append('encoding', encoding);
    form_data.append('auto_completion', auto_completion);
    form_data.append('is_next_module_locked', is_next_module_locked);
    form_data.append('player_configuration', player_configuration);
    form_data.append('scorm_file_name', scorm_file_name);
    form_data.append('new_scorm_file_uploaded', new_scorm_file_uploaded);
    runtime.notify('save', {state: 'start'});

    $.ajax({
      url: handlerUrl,
      dataType: 'text',
      cache: false,
      contentType: false,
      processData: false,
      data: form_data,
      type: "POST",
      success: function(response){
        runtime.notify('save', {state: 'end'});
      }
    });

  });

  $(element).find('.cancel-button').bind('click', function() {
    runtime.notify('cancel', {});
  });

  // When Display Type is changed trigger the showHidePopupLaunchOptions function.
  $(element).find('input[name=display_type]').bind('click', function() {
    showHidePopupLaunchOptions()
  });

  // When Popup Launch Type is changed trigger the showHideLaunchButtonTextField function.
  $(element).find('input[name=popup_launch_type]').bind('click', function() {
    var display_type_popup = true;
    showHideLaunchButtonTextField(display_type_popup)

  });

  // When Display Type is popup show popup types and when it is iframe hide popup types
  // also trigger the showHideLaunchButtonTextField function.
  function showHidePopupLaunchOptions() {
      var display_type = $(element).find('input[name=display_type]:checked').val();
      var display_type_popup = false;
      if(display_type === 'popup'){
        $(element).find('#popup_type').show();
        display_type_popup = true;
        showHideLaunchButtonTextField(display_type_popup)
      }
      else{
        $(element).find('#popup_type').hide();
        showHideLaunchButtonTextField(display_type_popup)
      }
  }

  // When display type is popup and popup type is manual show launch button text field,
  // in other cases hide show launch button text field
  function showHideLaunchButtonTextField(display_type_popup) {
    if(display_type_popup === true){
      $(element).find('#launch_button').show();
      modifyLaunchButtonTextField();
    }
    else{
      $(element).find('#launch_button').hide();
    }
  }

  // Changes label text for launch button field
  function modifyLaunchButtonTextField() {
    var popup_launch_type = $(element).find('input[name=popup_launch_type]:checked').val();
    if (popup_launch_type === 'manual') {
      $(element).find('#launch_button .label').text('Launch Button Text');
      $(element).find('#launch_button .setting-help').text('Display text for Launch Button');
    }
    else if (popup_launch_type === 'auto') {
      $(element).find('#launch_button .label').text('Relaunch Button Text');
      $(element).find('#launch_button .setting-help').text('Display text for Relaunch Button');
    }
  }

  $(function ($) {
      showHidePopupLaunchOptions();
    })
}
