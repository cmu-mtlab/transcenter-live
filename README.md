TransCenter
===========

TransCenter Live: Web-based post-editing environment for use with Realtime (cdec)

Author: Michael Denkowski (http://www.cs.cmu.edu/~mdenkows/, mdenkows@cs.cmu.edu)

Copyright: Carnegie Mellon University

License: LGPL

Included libraries:
-------------------

web.py (http://webpy.org/) - Public Domain

jQuery (http://jquery.com/) - MIT License

Beautiful Soup (http://www.crummy.com/software/BeautifulSoup/) - MIT License

chardet (http://pypi.python.org/pypi/chardet) - LGPL

Required Software:
------------------

Realtime (cdec) (http://www.cs.cmu.edu/~mdenkows/cdec-realtime.html, https://github.com/redpony/cdec) - Apache License

Usage:
------

**TransCenter Server**

To start a TransCenter server, run:

    $ python startup.py

Use ctrl+c to stop the server.

The server can be started with the following options:

    -p port      : Change port (Default 8080)
    -t timeout   : Timeout for cdec systems
    --dbg-editor : Run editor only (do not call cdec)
    --dbg-sql    : Print SQL queries before executing
    --dbg-track  : Print user edits and events
    --dbg-webpy  : Run webpy in debug mode, may cause issues with user sessions

Edit the file data/config.txt to configure your server:

* title: the title of your translation project to appear on the login screen
* from\_email: the email address that system emails (such as account recovery) will be from
* admin\_email: the email address that users can send email to for help and support.  This address is shown on the help page.  The help page uses basic javascript email obfuscation to thwart spambots.
* admin\_password: password that administrators can use to login

**Creating New Tasks**

To create a translation task using the command line tool:

    $ python trans/create_task.py

The following types of tasks are available:

* Realtime post-editing task with feedback
* Realtime post-editing task (no adaptation from feedback):
* Offline task (translations pre-generated with cdec, Moses, etc.)

See the usage message for more information.  To see full descriptions of tasks, see the TransCenter help page (startup TransCenter and click Help).

Place generated task directories in data/tasks to make them available for users to work on.  Finished tasks can be moved to data/archive.  Archived tasks will not appear to users but are available for report generation.

**Report Generation**

To generate reports, use the command line report tool:

    $ python trans/report.py

The following types of reports are output:

* Summary: source, initial and final translations, ratings, and various statistics collected during translation
* Edits: edit trace for each sentence

Reports are output for each user and averaged reports are output for compatible report types.  Reports are output in both formatted HTML and tab delimited comma separated value (CSV) files where appropriate.

**Admin Commands**

To execute admin actions using the command line tool:

    $ python trans/admin.py

Admin actions include adding, listing, and recovering user accounts.  See the
usage message for more details.

Test Cases:
-----------

The following are tested in Chrome and Firefox:

* Exit editor, timeout, resume
* Exit while (Translating...), restart
