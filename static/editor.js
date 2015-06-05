/*

Logged events with codes:
[f]ocus / [b]lur
[s]ubmit / [r]ating
[kc] keycount / [mc] mousecount
[rw] rewrite (includes delete/cut)
[co]py / [sc] source copy
[pa]use / [re]sume

Checklist for Chromium/Firefox/Opera:
- focus
- blur
- submit
- rate
- pause
- unpause
- keyboard input
- keyboard delete
- keyboard input with text selected
- keyboard delete with text selected
- keyboard cut/copy/paste
- keyboard paste with text selected
- keyboard undo/redo
- text drag selected by mouse
- text drag selected by keybaord
- context menu cut/copy/paste
- context menu paste with text selected
- enter text into empty field
- enter text at begin and end pos
- full line delete
- full line replace

*/

var font_black = '#000000';
var bg_select = '#d0e0ff';
var bg_alert = '#ffbbbb';
var bg_blur = new Array('#ffffff', '#eeeeee');

var textpadding = 0; // .src, .hyp textarea padding x2 in px (set at init)

var cur_sent_id = 0; // Int ID of currently focused sentence
var cur_sent_text = 0 // Text of currently focused sentence
var cur_sent_kc = 0; // Keycount and mousecount are accumulated and sent
var cur_sent_mc = 0; // in batch when user submits a sentence.

var warn_exit = true;

var cancel_rating_event = false; // Set to true when rating by keyboard

var task = ''; // Task type to see what to send

// Translation / rating state
var last_translated = 0;
var last_rated = 0;
var system_loaded = false;
var paused = false;

$(document).ready(function() {

    /* Init */

    task = $('#task').val();

    // Find vertical text padding for auto-expand
    var p = $('.src').css('padding-top');
    textpadding = 2 * parseInt(p.substr(0, p.length - 2));

    // Expand inputs
    var sources = $('.src');
    sent_total = sources.length;
    sources.each(function() {
        var n = parseInt($(this).attr('name'));
        var src_h = $(this).get(0).scrollHeight;
        var hyp_h = $('.hyp[name="' + n + '"]').get(0).scrollHeight;
        var all_h = Math.max(src_h, hyp_h);
        resize_inputs(n, all_h);
        set_back(n, bg_blur[n % 2]);
    });

    /* UI hooks */

    // Warn on exit unless submitting task
    window.onbeforeunload = function() {
        if (cur_sent_id != 0) {
            log_event(cur_sent_id, 's', '', '', $('.hyp[name="' + cur_sent_id + '"]').val());
            log_event(cur_sent_id, 'kc', '', '', cur_sent_kc);
            log_event(cur_sent_id, 'mc', '', '', cur_sent_mc);
            cur_sent_kc = 0;
            cur_sent_mc = 0;
        }
        if (warn_exit) {
            return 'Translations not yet submitted.';
        } else {
            // Need plain return for compatibility
            return;
        }
    }

    // Focus sentence
    $('.src, .hyp, .rating').live('focus', function() {
        var n = parseInt($(this).attr('name'));
        switch_highlight(cur_sent_id, n);
        cur_sent_id = n;
        cur_sent_text = $('.hyp[name="' + n + '"]').val();
        // Only log editing time
        if ($(this).hasClass('hyp')) {
            // LOG: Focus event
            log_event(n, 'f', '', '', cur_sent_text);
        }
    });

    // Click sentence line
    $('.linecell').click(function() {
        $('.hyp[name="' + $(this).attr('name') + '"]').focus();
    });

    // Blur sentence
    $('.hyp').live('blur', function(){
        var n = $(this).attr('name');
        // LOG: Blur event
        log_event(n, 'b', '', '', '');
        // LOG: Submit sentence
        log_event(n, 's', '', '', $(this).val());
        log_event(n, 'kc', '', '', cur_sent_kc);
        log_event(n, 'mc', '', '', cur_sent_mc);
        cur_sent_kc = 0;
        cur_sent_mc = 0;
    });

    // Track keys pressed
    $('.hyp').bind('keydown', function(event){
        cur_sent_kc += 1;
    });

    // Track mouse actions
    $('.hyp').bind('mousedown', function(event){
        cur_sent_mc += 1;
    });

    // Editor: catch keydown to include special keys
    $('.hyp').keydown(function(event){
        // Enter/tab move to rating
        if (event.which == 13 || event.which == 9) {
            event.preventDefault();
            // Shift moves back
            if (event.shiftKey) {
                sel_prev();
            } else {
                sel_rating();
            }
        }
    });

    // Editor: Input.  Text area value has changed.
    $('.hyp').bind('input', function(event){
        handle_input(this, event);
    });
    function handle_input(elem) {
        // Log rewrite
        var n = $(elem).attr('name');
        var diff = str_diff_bound(cur_sent_text, elem.value)
        log_event(n, 'rw', diff.start, diff.before, diff.after);
        // See if input needs to be resized
        check_resize($(elem));
        // Update current text for future rewrites
        cur_sent_text = elem.value
    }

    // Editor: copy (including source)
    $('.src, .hyp').bind('copy', function(event){
        var n = $(this).attr('name');
        var sel = getInputSelection(this);
        var text = $(this).val().substring(sel.start, sel.end);
        if($(this).hasClass('src')) {
            //LOG: source copy event
            log_event(n, 'sc', sel.start, '', text);
        } else {
            //LOG: copy event
            log_event(n, 'co', sel.start, '', text);
        }
    });

    // Rating: key selects value and moves to next
    $('.rating').keypress(function(event){
        if (event.which >= 49 && event.which <= 53) {
            event.preventDefault();
            $(this).val(event.which - 48);
            //LOG: rating event
            var n = $(this).attr('name');
            log_event(n, 'r', '', '', $(this).val());
            cancel_rating_event = true;
            report_translate_next();
        }
    });

    // Rating: selecting value moves to next
    $('.rating').change(function(){
        if (cancel_rating_event) {
            cancel_rating_event = false;
            return;
        }
        //LOG: rating event
        var n = $(this).attr('name');
        log_event(n, 'r', '', '', $(this).val());
        report_translate_next();
    });

    // Pause button
    $('#pause').click(function(){
        pause();
    });

    // Resume button
    $('#resume').click(function(){
        resume();
    });

    // Start button
    $('#start').click(function(){
        start();
    });

    // Help button
    $('#help').click(function(){
        pause();
        window.open('/help');
    });

    // Submit button
    $('#submit').click(function(){
        var ratings = $('.rating');
        var done = true;
        ratings.each(function() {
            if ($(this).val() == 0) {
                done = false;
            }
        });
        if (!done){
            alert('Please complete all tasks.');
        } else {
            warn_exit = false;
            location.replace('/done');
        }
    });

    /* Start Translation */

    // Find last translated and rated
    var hyps = $('.hyp');
    hyps.each(function() {
        var n = parseInt($(this).attr('name'));
        if ($(this).val() != '') {
            last_translated = n;
        }
        if ($('.rating[name="' + n + '"]').val() != 0) {
            last_rated = n;
        }
    });

    // Translate next sentence unless rating pending (translation in progress)
    if (last_translated == last_rated) {
        cur_sent_id = last_rated;
        $('.rating[name="' + cur_sent_id + '"]').focus();
        report_translate_next();
    }
});

function log_event(index, event, start, before, after) {
    var time = (new Date()).getTime();
    var msg = {'t': time, 'i': index, 'e': event, 's': start, 'b': before, 'a': after};
    // GET should work fine on modern browsers.  Switch to (slower) POST if
    // this causes problems.
    $.get('/submit', msg);
}

// Shouldn't need to use this for input.  Javascript should encode input strings properly for GET/POST.
function html_escape(s) {
    return s.toString().replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace('\'', '&apos;');
}

function pause() {
    // LOG: pause event
    log_event('', 'pa', '', '', '');
    $('#darkback').css('visibility', 'visible');
    $('#pauseback').css('visibility', 'visible');
    paused = true;
}

function resume() {
    $('#darkback').css('visibility', 'hidden');
    $('#pauseback').css('visibility', 'hidden');
    // LOG: resume event
    log_event('', 're', '', '', '');
    paused = false;
}

function start() {
    $('#darkback').css('visibility', 'hidden');
    $('#splashback').css('visibility', 'hidden');
    // Focus first sentence
    $('.hyp[name="' + (cur_sent_id + 1) + '"]').focus();
}

function switch_highlight(old_n, new_n) {
    if (old_n == new_n) {
        return;
    }
    if (old_n != 0) {
        set_back(old_n, bg_blur[old_n % 2]);
        if ($('.rating[name="' + old_n + '"]').val() == 0) {
            $('.ratingcell[name="' + old_n + '"]').css('background', bg_alert);
        }
    }
    set_color(new_n, font_black);
    set_back(new_n, bg_select);
}

// Resize if scrollheight changes
function check_resize(obj) {
    var h = obj.height();
    var sh = obj.get(0).scrollHeight - textpadding;
    if (sh > h) {
        resize_inputs(obj.attr('name'), sh + textpadding);
    }
}

function resize_inputs(line, h) {
    $('.src[name="' + line + '"]').css('height', h);
    $('.hyp[name="' + line + '"]').css('height', h);
}

function set_color(n, color) {
    $('.src[name="' + n + '"]').css('color', color);
    $('.hyp[name="' + n + '"]').css('color', color);
}

function set_back(n, color) {
    $('tr[name="' + n + '"]').css('background-color', color);
    $('.src[name="' + n + '"]').css('background-color', color);
    $('.hyp[name="' + n + '"]').css('background-color', color);
    $('.ratingcell[name="' + n + '"]').css('background-color', color);
}

function sel_rating() {
    $('.rating[name="' + cur_sent_id + '"]').focus();
}

function sel_prev() {
    if (cur_sent_id > 1) {
        $('.hyp[name="' + (cur_sent_id - 1) + '"]').focus();
    }
}

function report_translate_next() {
    // Re-rating of previously edited sentence
    // (do not translate)
    if (cur_sent_id < last_translated) {
        $('.hyp[name="' + (cur_sent_id + 1) + '"]').focus();
        return;
    }
    // Otherwise translate
    var first_or_repeat = (last_translated == last_rated);
    last_rated = cur_sent_id;
    last_translated = cur_sent_id + 1;
    var source = '';
    var reference = '';
    var next = '';
    // Find current source/reference pair except before first sentence
    // OR when re-starting and re-translating (don't duplicate learn requests)
    if (!first_or_repeat) {
        source = $('.src[name="' + cur_sent_id + '"]').val();
        reference = $('.hyp[name="' + cur_sent_id + '"]').val();
    }
    // Find next sentence except at end of document
    if (cur_sent_id < sent_total) {
        next = $('.src[name="' + (cur_sent_id + 1) + '"]').val();
        var message = 'Translating...';
        if (!system_loaded) {
            $('#startmsg').html('Loading translation system.<br />This may take a few minutes.');
            $('#start').html('Loading...');
            $('#start').prop('disabled', true);
            $('#darkback').css('visibility', 'visible');
            $('#splashback').css('visibility', 'visible');
        }
        $('.hyp[name="' + (cur_sent_id + 1) + '"]').val(message);
        check_resize($('.hyp[name="' + (cur_sent_id + 1) + '"]'));
    }
    // Ajax post to translator
    need_enable = !system_loaded;
    system_loaded = true;
    $.post(
            '/translator',
            // i is sentence being translated
            {'i': (cur_sent_id + 1), 's': source, 'r': reference, 'n': next, 't': task, 'f': first_or_repeat},
            function(data) {
                // If not last sentence, enable and populate next
                if (cur_sent_id < sent_total) {
                    $('.hyp[name="' + (cur_sent_id + 1) + '"]').prop('disabled', false);
                    $('.rating[name="' + (cur_sent_id + 1) + '"]').prop('disabled', false);
                    $('.hyp[name="' + (cur_sent_id + 1) + '"]').val(data);
                    check_resize($('.hyp[name="' + (cur_sent_id + 1) + '"]'));
                    if (need_enable) {
                        // Enable start button
                        $('#startmsg').html('Translation system loaded.<br />Click Start to begin!');
                        $('#start').html('Start');
                        $('#start').prop('disabled', false);
                    } else {
                        // Focus last (updates cur_sent_id)
                        if (!paused) {
                            $('.hyp[name="' + (cur_sent_id + 1) + '"]').focus();
                        }
                    }
                }
            },
            'text'
    );
}

// Bound region of difference between two strings in linear time.
function str_diff_bound(src, tgt) {
    var sl = src.length
    var tl = tgt.length
    var i = 0;
    var min_len = Math.min(sl, tl);
    while (i < min_len && src.charAt(i) == tgt.charAt(i)) {
        i += 1;
    }
    var j = 1;
    while (j < min_len && src.charAt(sl - j) == tgt.charAt(tl - j)) {
        j += 1;
    }
    j -= 1;
    // Overlap
    var overlap = i - Math.min(sl - j, tl - j);
    if (overlap > 0) {
        // Move back i until it hits the beginning of the string, then move back j
        i -= overlap;
        var underflow = 1;
        if (underflow < 0) {
            i = 0;
            j += -underflow;
        }
    }
    return {start: i, before: src.substring(i, sl - j), after: tgt.substring(i, tl - j)};
}

// Cross-browser input selection finder
// Taken from Rangy (http://code.google.com/p/rangy/)
// Author: Tim Down (MIT license)
function getInputSelection(el) {
        var start = 0, end = 0, normalizedValue, range,
                textInputRange, len, endRange;

        if (typeof el.selectionStart == "number" && typeof el.selectionEnd == "number") {
                start = el.selectionStart;
                end = el.selectionEnd;
        } else {
                range = document.selection.createRange();

                if (range && range.parentElement() == el) {
                        len = el.value.length;
                        normalizedValue = el.value.replace(/\r\n/g, "\n");

                        // Create a working TextRange that lives only in the input
                        textInputRange = el.createTextRange();
                        textInputRange.moveToBookmark(range.getBookmark());

                        // Check if the start and end of the selection are at the very end
                        // of the input, since moveStart/moveEnd doesn't return what we want
                        // in those cases
                        endRange = el.createTextRange();
                        endRange.collapse(false);

                        if (textInputRange.compareEndPoints("StartToEnd", endRange) > -1) {
                                start = end = len;
                        } else {
                                start = -textInputRange.moveStart("character", -len);
                                start += normalizedValue.slice(0, start).split("\n").length - 1;

                                if (textInputRange.compareEndPoints("EndToEnd", endRange) > -1) {
                                        end = len;
                                } else {
                                        end = -textInputRange.moveEnd("character", -len);
                                        end += normalizedValue.slice(0, end).split("\n").length - 1;
                                }
                        }
                }
        }

        return {
                start: start,
                end: end
        };
}
