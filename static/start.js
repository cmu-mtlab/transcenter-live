// Supported browsers: Chrome/Chromium, Mozilla-based (Firefox or similar)
$.browser.chrome = ($.browser.webkit && /chrom(e|ium)/.test(navigator.userAgent.toLowerCase()));
if (!($.browser.mozilla || $.browser.chrome)) {
    location.replace('/browsers');
}

$(document).ready(function() {

    $('#alogin').click(function() {
        show_login();
    });

    $('#aregister').click(function() {
        show_register();
    });

    $('#arecover').click(function() {
        show_recover();
    });

    $('#aadmin').click(function() {
        show_admin();
    });

    $('#logbutton').click(function(e) {
        if (!validate_log()) {
            e.preventDefault();
        }
    });

    $('#newbutton').click(function(e) {
        if (!validate_reg()) {
            e.preventDefault();
        }
    });

    $('#recbutton').click(function(e) {
        if (!validate_rec()) {
            e.preventDefault();
        }
    });

    $('#adminbutton').click(function(e) {
        if (!validate_admin()) {
            e.preventDefault();
        }
    });

    // Default
    show_login();
    $('[name="uid"]').focus();
});

function show_login() {
    $('#register').css('visibility', 'hidden');
    $('#recover').css('visibility', 'hidden');
    $('#admin').css('visibility', 'hidden');
    $('#login').css('visibility', 'visible');
    $('#aregister').css('color', '#0000ff');
    $('#arecover').css('color', '#0000ff');
    $('#aadmin').css('color', '#0000ff');
    $('#alogin').css('color', '#000000');
}

function show_register() {
    $('#recover').css('visibility', 'hidden');
    $('#login').css('visibility', 'hidden');
    $('#admin').css('visibility', 'hidden');
    $('#register').css('visibility', 'visible');
    $('#arecover').css('color', '#0000ff');
    $('#alogin').css('color', '#0000ff');
    $('#aadmin').css('color', '#0000ff');
    $('#aregister').css('color', '#000000');
}

function show_recover() {
    $('#login').css('visibility', 'hidden');
    $('#register').css('visibility', 'hidden');
    $('#admin').css('visibility', 'hidden');
    $('#recover').css('visibility', 'visible');
    $('#alogin').css('color', '#0000ff');
    $('#aregister').css('color', '#0000ff');
    $('#aadmin').css('color', '#0000ff');
    $('#arecover').css('color', '#000000');
}

function show_admin() {
    $('#login').css('visibility', 'hidden');
    $('#register').css('visibility', 'hidden');
    $('#recover').css('visibility', 'hidden');
    $('#admin').css('visibility', 'visible');
    $('#alogin').css('color', '#0000ff');
    $('#aregister').css('color', '#0000ff');
    $('#arecover').css('color', '#0000ff');
    $('#aadmin').css('color', '#000000');
}

function validate_log() {
    if ($('[name="uid"]').val() == '' ||
        $('[name="pass"]').val() == '') {
        alert('Please enter user ID and password.');
        return false;
    }
    return true;
}

function validate_reg() {
    if ($('[name="newuid"]').val() == '' ||
        $('[name="newpass"]').val() == '' ||
        $('[name="newpasstwo"]').val() == '' ||
        $('[name="newemail"]').val() == '' ||
        $('[name="newgroup"]').val() == '') {
        alert('Please fill all fields.');
        return false;
    }
    if ($('[name="newpass"]').val() != $('[name="newpasstwo"]').val()) {
        alert('Passwords do not match.');
        return false;
    }
    return true;
}

function validate_rec() {
    if ($('[name="recemail"]').val() == '') {
        alert('Please enter an email address.');
        return false;
    }
    return true;
}

function validate_admin() {
    if ($('[name="adminpass"]').val() == '') {
        alert('Please enter a password.');
        return false;
    }
    return true;
}
