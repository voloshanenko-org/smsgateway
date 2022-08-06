function setActDate() {
    var today = new Date();
    var dd = today.getDate();
    var mm = today.getMonth() + 1;
    //January is 0!
    var yyyy = today.getFullYear();
    
    if (dd < 10) {
        dd = '0' + dd
    }
    
    if (mm < 10) {
        mm = '0' + mm
    }
    
    today = yyyy + '-' + mm + '-' + dd + '%';
    
    jQuery("#getsms input[name=date]").val(today)
}

$.tablesorter.addParser({
    id: "customDate",
    is: function(s) {
        //return false;
        //use the above line if you don't want table
        //sorter to auto detected this parser
        //else use the below line.
        //attention: doesn't check for invalid stuff
        //2009-77-77 77:77:77.0 would also be matched
        //if that doesn't suit you alter the regex to
        //be more restrictive
        return /\d{1,4}-\d{1,2}-\d{1,2} \d{1,2}:\d{1,2}:\d{1,2}\.\d+/.test(s);
    },
    format: function(s) {
        s = s.replace(/\-/g, " ");
        s = s.replace(/:/g, " ");
        s = s.replace(/\./g, " ");
        s = s.split(" ");
        return jQuery.tablesorter.formatFloat(((new Date(s[0],s[1] - 1,s[2],s[3],s[4],s[5]).getTime()) * 1000) + parseInt(s[6]));
    },
    type: "numeric"
});

window.onload = function() {
    getRouting();
    var oldVal = "";

    $("#mobiles").on("change keyup paste", function() {
        var currentVal = $(this).val();
        if(currentVal == oldVal) {
            return; //check to prevent multiple simultaneous triggers
        }
        oldVal = currentVal;

        var filteredData  = filterMobiles(this)

        $("#mobiles_count").text(filteredData[0] + filteredData[1])
        $("#mobiles_count_good").text(filteredData[0])
        $("#mobiles_count_bad").text(filteredData[1])
        $("#mobiles_bad").text(filteredData[3].join("\n"))
    });

    $("#content").on("change keyup paste", function() {
        var currentVal = $(this).val();
        if(currentVal == oldVal) {
            return; //check to prevent multiple simultaneous triggers
        }
        oldVal = currentVal;
        $("#content_count").text(currentVal.length)
    });
}
;
function getAllSms() {
    var datum = jQuery("#getsms input[name=date]").val();
    jQuery('div.sms').load('ajax/getsms', {
        all: "true",
        date: datum
    }, function() {
        if (jQuery("#sessiontimeout").length) {
            location.reload();
        }
        jQuery("#smsTable").tablesorter(
        {
            headers: {
                5: {
                    sorter: 'customDate'
                },
                8: {
                    sorter: 'customDate'
                }
            },
            sortList: [[5, 1], [8, 1]],
            theme: 'blue',
            widgets: ["zebra", "filter"],
            widthFixed: true
        });
    }
    );
}
function getSms() {
    var datum = jQuery("#getsms input[name=date]").val();
    jQuery('div.sms').load('ajax/getsms', {
        all: "false",
        date: datum
    }, function() {
        if (jQuery("#sessiontimeout").length) {
            location.reload();
        }
        jQuery("#smsTable").tablesorter(
        {
            headers: {
                5: {
                    sorter: 'customDate'
                },
                8: {
                    sorter: 'customDate'
                }
            },
            sortList: [[6, 0], [7, 1]],
            theme: 'blue',
            widgets: ["zebra", "filter"],
            widthFixed: true
        });
    }
    );
}

function getStatus() {
    
    jQuery.post("ajax/status", function(data) {
        if (jQuery("#sessiontimeout").length) {
            location.reload();
        }

        try{
            var status = JSON.parse(data);
            jQuery("#routerstatus").html(status['router']);
            if (status['router'] == 'alive') {
                jQuery("#routerstatus").css("background", "#669933");
            } else {
                JQuery("#routerstatus").css("background", "#E24C34");
            }
            jQuery("#watchdogstatus").html(status['watchdog']);
            if (status['watchdog'] == 'alive') {
                jQuery("#watchdogstatus").css("background", "#669933");
            } else {
                jQuery("#watchdogstatus").css("background", "#E24C34");
            }
        }catch (e){}
    }
    );
}

function sendSms() {
    if (jQuery("#sessiontimeout").length) {
        location.reload();
    }
    appid = $( "#appid" ).val()
    content = $( "#content" ).val()

    var filteredData  = filterMobiles($("#mobiles"))
    if (filteredData[2].length){
        if (content == ""){
            warning_message = "You need to type at least 1 symbol of sms to send!";
            showToastr("warning", warning_message);
        }else{
            sendsms_towis(appid, filteredData[2], content)
        }
    }else{
        warning_message = "You need to type at least 1 mobile number to send sms TO!";
        showToastr("warning", warning_message);
    }
}

function sendsms_towis(appid, mobiles, content){
    data = {
        appid: appid,
        mobile: mobiles,
        content: content
    }
    json_data = JSON.stringify(data);

    title = "Send SMS?"
    warning_message = content

    $('<div id="dialog-confirm" title=" ' + title + '">' +
        '<p><span class="ui-icon ui-icon-alert" style="float:left; margin:12px 12px 20px 0;">' +
        '</span>' + warning_message + '</p></div>').dialog({
        resizable: false,
        height: "auto",
        width: 400,
        modal: true,
        buttons: {
            "Start SMS campaign": function() {
                $( this ).dialog( "close" );
                $.postJSON('/sendsms', json_data).done(function(data) {
                    response_message = data.message
                    if (response_message.match('.*not valid.*')){
                        toast_type = "warning"
                    }else{
                        toast_type = "success"
                    }
                    title = "SENT OK!"
                    showToastr(toast_type, response_message);
                }).fail(function(data){
                    response_message = data.responseJSON.message
                    error_message = "Can't send sms! ERROR_CODE: " + data.status + ". ERROR_MESSAGE:" + response_message;
                    showToastr("error", error_message);
                });
            },
            "Cancel": function() {
                $( this ).dialog( "close" );
            }
        }
    });
}

function filterMobiles(element) {
    var mobiles = $(element).val();
    // Split each number per line, remove ; and remove empty elements if any
    mobiles_array_final = mobiles.split("\n").map(n => n.replace(";", "").trim()).filter(n => n);

    regex_list = $('#mobile_prefixes').val().split(",").filter(n => n);

    var count_good = 0
    var count_bad = 0
    mobiles_array_good = []
    mobiles_array_bad = []
    if (! regex_list){
        regex_list = [".*"]
    }

    mobiles_array_final.forEach(function (mobnum) {
        good = false
        if (mobnum.match(/^\d{12}$/)){
            for (rx in regex_list){
                regex = new RegExp("^" + regex_list[rx] + "\\d{7}$", 'gi')
                if (mobnum.match(regex)){
                    good = true
                }
            }
        }
        if (good){
            count_good +=1
            mobiles_array_good.push(mobnum)
        }else{
            count_bad += 1;
            mobiles_array_bad.push(mobnum)
        }

    });
    return [count_good, count_bad, mobiles_array_good, mobiles_array_bad]

}

jQuery["postJSON"] = function( url, data, callback ) {
    // shift arguments if data argument was omitted
    if ( jQuery.isFunction( data ) ) {
        callback = data;
        data = undefined;
    }

    return jQuery.ajax({
        url: url,
        type: "POST",
        contentType:"application/json; charset=utf-8",
        dataType: "json",
        data: data,
        success: callback
    });
};

function showToastr(toastr_type, toastr_message){
    if (toastr_type=="call_success"){
        toastr.options = {
            "debug": false,
            "newestOnTop": true,
            "progressBar": true,
            "positionClass": "toast-top-right",
            "preventDuplicates": false,
            "onclick": null,
            "showDuration": "300",
            "hideDuration": "1000",
            "timeOut": "10000",
            "extendedTimeOut": "1000",
            "showEasing": "swing",
            "hideEasing": "linear",
            "showMethod": "fadeIn",
            "hideMethod": "fadeOut"
        }
    } else if (toastr_type=="success"){
        toastr.options = {
            "debug": false,
            "newestOnTop": true,
            "progressBar": true,
            "positionClass": "toast-top-right",
            "preventDuplicates": false,
            "onclick": null,
            "showDuration": "300",
            "hideDuration": "1000",
            "timeOut": "1000",
            "extendedTimeOut": "1000",
            "showEasing": "swing",
            "hideEasing": "linear",
            "showMethod": "fadeIn",
            "hideMethod": "fadeOut"
        }
    }else if(toastr_type=="error"){
        toastr.options = {
            "closeButton": true,
            "debug": false,
            "newestOnTop": true,
            "positionClass": "toast-top-right",
            "preventDuplicates": true,
            "onclick": null,
            "showDuration": "300",
            "hideDuration": "1000",
            "timeOut": "0",
            "extendedTimeOut": "0",
            "showEasing": "swing",
            "hideEasing": "linear",
            "showMethod": "fadeIn",
            "hideMethod": "fadeOut"
        }
    }else if (toastr_type=="warning") {
        toastr.options = {
            "debug": false,
            "newestOnTop": true,
            "progressBar": true,
            "positionClass": "toast-top-right",
            "preventDuplicates": true,
            "onclick": null,
            "showDuration": "300",
            "hideDuration": "1000",
            "timeOut": "5000",
            "extendedTimeOut": "1000",
            "showEasing": "swing",
            "hideEasing": "linear",
            "showMethod": "fadeIn",
            "hideMethod": "fadeOut"
        }
    }
    if (toastr_type == "call_success"){
        toastr_type = "success"
    }
    toastr[toastr_type](toastr_message)
};

function isANumber(str){
    return !/\D/.test(str);
}

function restartAllModems(){
    var all_imsi = []
    $('#routingTable').find('tr').each(function() {
        imsi = $(this).find("td:nth-child(4)").html();
        if (imsi != undefined && isANumber(imsi.toString()) && imsi.toString().length == 15) {
            all_imsi.push(imsi);
        }
    });

    title = "Restart ALL modems?"
    warning_message = "Do you REALLY want to restart ALL modems"

    $('<div id="dialog-confirm" title=" ' + title + '">' +
        '<p><span class="ui-icon ui-icon-alert" style="float:left; margin:12px 12px 20px 0;">' +
        '</span>' + warning_message + '</p></div>').dialog({
        resizable: false,
        height: "auto",
        width: 400,
        modal: true,
        buttons: {
            "Restart Modem": function() {
                $( this ).dialog( "close" );
                all_imsi.forEach(function(imsi){
                    data = {
                        imsi: imsi.toString(),
                    }
                    json_data = JSON.stringify(data)
                    $.postJSON('/restartmodem', json_data).done(function(data) {
                        warning_message = "Modem restart initiated. Check status later on"
                        title = "RESTART OK!"
                        showToastr("warning", warning_message);
                    }).fail(function(data){
                        response_message = data.responseJSON.message
                        error_message = "Can't restart modem! ERROR_CODE: " + data.status + ". ERROR_MESSAGE:" + response_message;
                        showToastr("error", error_message);
                    });
                });

            },
            "Cancel": function() {
                $( this ).dialog( "close" );
            }
        }
    });

    $('#routingTable').find('tr').each(function() {
        var last_th = $(this).find('th').eq(-1).html()
        if (last_th != undefined && !last_th.match(/.*maintenance.*/)) {
            $(this).find('th').eq(-1).after('<th>maintenance <button class="btn" type="button" onclick="restartAllModems()">Restart ALL</button></th>');
        }
        var last_td = $(this).find('td').eq(-1).html()
        if (last_td != undefined && !last_td.match(/.*restartModem.*/)) {
            sim_imsi = $(this).find("td:nth-child(4)").html();
            $(this).find('td').eq(-1).after('<td><button class="btn" type="button" onclick="restartModem(' + sim_imsi + ')">Restart</button></td>');
        }
    });
}

function restartModem(imsi) {
    if (isANumber(imsi.toString()) && imsi.toString().length == 15){
        data = {
            imsi: imsi.toString(),
        }
        json_data = JSON.stringify(data)

        title = "Restart modem?"
        warning_message = "Do you REALLY want to restart modem with SIM IMSI " + imsi.toString()

        $('<div id="dialog-confirm" title=" ' + title + '">' +
            '<p><span class="ui-icon ui-icon-alert" style="float:left; margin:12px 12px 20px 0;">' +
            '</span>' + warning_message + '</p></div>').dialog({
                resizable: false,
                height: "auto",
                width: 400,
                modal: true,
                buttons: {
                    "Restart Modem": function() {
                        $( this ).dialog( "close" );
                        $.postJSON('/restartmodem', json_data).done(function(data) {
                            warning_message = "Modem restart initiated. Check status later on"
                            title = "RESTART OK!"
                            showToastr("warning", warning_message);
                        }).fail(function(data){
                            response_message = data.responseJSON.message
                            error_message = "Can't restart modem! ERROR_CODE: " + data.status + ". ERROR_MESSAGE:" + response_message;
                            showToastr("error", error_message);
                        });
                    },
                    "Cancel": function() {
                        $( this ).dialog( "close" );
                    }
                }
            });
    }
    else {
        warning_message = "IMSI can be only 15 digits string!"
        showToastr("warning", warning_message)
    }
}

function getRouting() {
    jQuery('div.routing').load('ajax/getrouting', function() {
        if (jQuery("#sessiontimeout").length) {
            location.reload();
        }
        jQuery("#routingTable").tablesorter(
        {
            headers: {
                0: {
                    sorter: 'customDate'
                }
            },
            sortList: [[4, 0], [8, 1]],
            theme: 'blue'
        });
        $('#routingTable').find('tr').each(function() {
            var last_th = $(this).find('th').eq(-1).html()
            if (last_th != undefined && !last_th.match(/.*maintenance.*/)) {
                $(this).find('th').eq(-1).after('<th>maintenance <button class="btn" type="button" onclick="restartAllModems()">Restart ALL</button></th>');
            }
            var last_td = $(this).find('td').eq(-1).html()
            if (last_td != undefined && !last_td.match(/.*restartModem.*/)) {
                sim_imsi = $(this).find("td:nth-child(4)").html();
                $(this).find('td').eq(-1).after('<td><button class="btn" type="button" onclick="restartModem(' + sim_imsi + ')">Restart</button></td>');
            }
        });
        getSMSCount();
    });

    getStatus();
    setTimeout(getRouting, 5000);
}

function getSMSCount(){
    var available_modems = 0;
    var scheduled_sms = 0;
    var scheduled_sms_modem = 0
    var total_scheduled_sms = 0;
    var sms_limit = 0;
    var total_sent_sms = 0;

    $('#routingTable').find('tr').each(function(){
        available_modems += 1;
        blocked = $(this).find("td:nth-child(6)").html();
        if (blocked == "No" || blocked == "N/A" || blocked == "Check Skipped"){
            temp_scheduled = parseInt($(this).find("td:nth-child(8)").html());
            if (temp_scheduled){
                scheduled_sms += temp_scheduled;
            }
            temp_sms_limit = parseInt($(this).find("td:nth-child(7)").html());
            if (temp_sms_limit){
                sms_limit += temp_sms_limit
            }
        }
        scheduled_sms_modem = parseInt($(this).find("td:nth-child(8)").html());
        sent_sms_modem = parseInt($(this).find("td:nth-child(9)").html());
        if(scheduled_sms_modem){
            total_scheduled_sms += scheduled_sms_modem;
        }
        if (sent_sms_modem){
            total_sent_sms += sent_sms_modem;
        }
    });

    if (available_modems > 0){
        available_modems -= 1;
    }

    availbale_sms = parseInt(sms_limit - scheduled_sms);
    $("#available_modems").text(available_modems);
    $("#available_sms").text(availbale_sms);
    $("#scheduled_sms").text(total_scheduled_sms);
    $("#sent_sms_active_modems").text(total_sent_sms);

    $.getJSON('/ajax/get_sms_stats').done(function(data) {
        $("#sent_sms_total_today").text(data.processed_sms);
        $("#unprocessed_sms").text(data.unprocessed_sms);
        availbale_sms = parseInt($("#available_sms").html()) - data.unprocessed_sms;
        if (availbale_sms > 0){
            $("#available_sms").text(availbale_sms);
        }
    }).fail(function(data){
        $("#sent_sms_total_today").text("N/A");
        $("#unprocessed_sms").text("N/A");
    });
}

$(document).ready(function() {
    setActDate();
    
    jQuery("#getsms").submit(function(event) {
        // Stop form from submitting normally
        event.preventDefault();
        
        // Get some values from elements on the page:
        var $form = $(this)
          , 
        dat = $form.find("input[name='date']").val()
          , 
        mob = $form.find("input[name='mobile']").val()
          , 
        url = $form.attr("action");
        
        // Send the data using post
        var posting = $.post(url, {
            date: dat,
            mobile: mob
        });
        
        // Put the results in a div
        posting.done(function(data) {
            jQuery("div.sms").empty().append(data);
            jQuery("#smsTable").tablesorter(
            {
                headers: {
                    5: {
                        sorter: 'customDate'
                    },
                    8: {
                        sorter: 'customDate'
                    }
                },
                sortList: [[5, 1], [8, 1]],
                theme: 'blue',
                widgets: ["zebra", "filter"]
            });
        }
        );
    }
    );
}
);
