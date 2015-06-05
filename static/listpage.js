// Supported browsers: Chrome/Chromium, Mozilla-based (Firefox or similar)
$.browser.chrome = ($.browser.webkit && /chrom(e|ium)/.test(navigator.userAgent.toLowerCase()));
if (!($.browser.mozilla || $.browser.chrome)) {
    location.replace('/browsers');
}
 
$(document).ready(function() {
   
    var links = $('.task');
    links.each(function() {
        var task = $(this).attr('name');
            $(this).click(function() {
                $('#' + task).submit();
            });
    });

});
