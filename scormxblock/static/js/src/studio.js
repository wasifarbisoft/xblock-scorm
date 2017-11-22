function ScormStudioXBlock(runtime, element) {

  var handlerUrl = runtime.handlerUrl(element, 'studio_submit');

  $(element).find('.save-button').bind('click', function() {
    var form_data = new FormData();
    var file_data = $(element).find('#scorm_file').prop('files')[0];
    var display_name = $(element).find('input[name=display_name]').val();
    var description = $(element).find('textarea[name=description]').val();
    var weight = $(element).find('input[name=weight]').val();
    var display_width = $(element).find('input[name=display_width]').val();
    var display_height = $(element).find('input[name=display_height]').val();
    var display_type = $(element).find('input[name=display_type]:checked').val();
    var scorm_player = $(element).find('select[name=scorm_player]').val();
    var encoding = $(element).find('select[name=encoding]').val();
    var player_configuration = $(element).find('textarea[name=player_configuration]').val();
    form_data.append('file', file_data);
    form_data.append('display_name', display_name);
    form_data.append('description', description);
    form_data.append('display_width', display_width);
    form_data.append('display_height', display_height);
    form_data.append('weight', weight);
    form_data.append('display_type', display_type);
    form_data.append('scorm_player', scorm_player);
    form_data.append('encoding', encoding);
    form_data.append('player_configuration', player_configuration);
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

}
