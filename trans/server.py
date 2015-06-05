#!/usr/bin/env python

import codecs, collections, getopt, itertools, logging, os, StringIO, sys, time, threading, traceback

import web

import io_extra, rt_hub, track

# Suppress verbose info for cdec realtime
logging.basicConfig(level=logging.WARN)

# Start logging immediately
io_extra.start_logging()

# Admin-defined values including title and email address
config = collections.defaultdict(lambda: u'config.txt error')
def reload_config():
    global config
    config = io_extra.read_cfg(os.path.join(io_extra.DATA_DIR, 'config.txt'))
reload_config()

# Admin-defined user groups and codes
groups = {}  # groups[code] = group
def reload_groups():
    global groups
    # These are stored val: key
    groups = dict((v, k) for (k, v) in io_extra.read_cfg(os.path.join(io_extra.DATA_DIR, 'groups.txt')).iteritems())
reload_groups()

dbg_editor = False

# Database connections and write lock
dbg_sql = False
user_db = io_extra.get_user_db(os.path.join(io_extra.DIR, 'data', 'user.db'))
user_db.printing = dbg_sql
trans_db = collections.defaultdict(lambda: None)  # trans_db[task] = database
db_write_lock = threading.RLock()

# Debug output and lock
dbg_track = False
dbg_lock = threading.RLock()
dbg_strings = collections.defaultdict(lambda: u'')

# User event queues and lock
ev_queue = collections.deque([])
ed_queue = collections.deque([])
queue_lock = threading.RLock()

# (user, task) -> realtime.d
rtd = {}

#
# Webpy App
#

web.config.debug = False

urls = (
    '/', 'start',
    '/admin', 'admin',
    '/browsers', 'browsers',
    '/done', 'done',
    '/editor', 'editor',
    '/favicon.ico', 'favicon',
    '/help', 'helppage',
    '/list', 'listpage',
    '/login', 'login',
    '/logout', 'logout',
    '/recover', 'recover',
    '/register', 'register',
    '/submit', 'submit',
    '/translator', 'translator',
)

render = web.template.render(io_extra.T_DIR)

app = web.application(urls, globals())

session_db = io_extra.get_web_db()
session_store = web.session.DBStore(session_db, 'sessions')
session_store.cleanup(0)
session = web.session.Session(app, session_store)

class start:

    def GET(self):
        return render.start(config['title'])


class login:

    def POST(self):
        try:
            # First check login information
            ip = web.ctx.get(u'ip')
            ua = web.ctx.env[u'HTTP_USER_AGENT'] if u'HTTP_USER_AGENT' in web.ctx.env else 'No user-agent'
            data = web.input()
            user = data.get(u'uid')
            password = data.get(u'pass')
            res = list(user_db.select(u'users', dict(user=user, password=password), where=u'user = $user and password = $password'))
            if len(res) == 0:
                io_extra.log(u'LOGIN: bad account: {0} {1} {2}'.format(ip, user, ua))
                return render.info(u'Login information does not match any account.  Please try again.')
            # Login success: set session
            session.user = user
            session.group = res[0]['groupname']
            io_extra.log(u'LOGIN: user logged in: {0} {1} {2}'.format(ip, user, ua))
            # Redirect to list now that user is logged in
            return render.gotolist()
        except Exception:
            io_extra.log(u'LOGIN: exception:')
            io_extra.log(traceback.format_exc())
            return render.info(u'Error encountered.  Please try again')


class logout:

    def GET(self):
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        if not user:
            io_extra.log(u'LOGOUT: unauthorized access: {0}'.format(ip))
            return render.info(u'You must be logged in to logout.  Although since you are not logged in, you are in fact logged out.')
        # End user session
        session.kill()
        io_extra.log(u'LOGOUT: user logged out: {0} {1}'.format(ip, user))
        return render.info(u'You have successfully logged out.')


class register:

    def POST(self):
        message = ''
        try:
            ip = web.ctx.get(u'ip')
            data = web.input()
            user = data.get(u'newuid')
            code = data.get(u'newgroup')
            password = data.get(u'newpass')
            email = data.get(u'newemail')
            reload_groups()  # Make sure groups are up to date
            # Attempt to add user
            (log_msg, user_msg) = add_user(ip, user, code, password, email)[1:]
            io_extra.log(log_msg)
            message = user_msg
        except Exception:
            io_extra.log(u'REG: exception:')
            io_extra.log(traceback.format_exc())
            message = u'Error encountered.  Please try again.'
        # Notify user
        return render.info(message)


class recover:

    def POST(self):
        message = ''
        try:
            ip = web.ctx.get(u'ip')
            data = web.input()
            email = data.get(u'recemail')
            (log_msg, user_msg) = recover_account(ip, email)[1:]
            io_extra.log(log_msg)
            message = user_msg
        except Exception:
            io_extra.log(u'REC: exception:')
            io_extra.log(traceback.format_exc())
            message = u'Error encountered.  Please try again.'
        return render.info(message)


class listpage:
    def GET(self):
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        # Not logged in
        if not user:
            io_extra.log(u'LIST: unauthorized access: {0}'.format(ip))
            return render.info(u'You must be logged in to access this page.  Please login using your account information.')
        # Logged in
        tasks = io_extra.list_tasks(escape=True)
        # List page uses user DB copy of status (faster, false positives aren't terrible)
        status = get_user_task_status(user, escape=True)
        return render.listpage(user, tasks, status)

# Return {task1: status1, ...}
def get_user_task_status(user, escape=False):
    res = user_db.select(u'status', dict(user=user), where=u'user = $user')
    pairs = ((r['task'], r['status']) for r in res)
    if escape:
        pairs = ((io_extra.html_escape(k), v) for (k, v) in pairs)
    return dict(pairs)


class editor:

    def GET(self):
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        if not user:
            io_extra.log(u'EDITOR: unauthorized access: {0}'.format(ip))
        else:
            io_extra.log(u'EDITOR: direct access attempted: {0}'.format(ip))
        return render.info(u'This page must be accessed from the translation task list.  Please login and select a task.')

    def POST(self):
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        data = web.input()
        taskdir = data.get(u'taskdir')
        # Not logged in
        if not user:
            io_extra.log(u'EDITOR: unauthorized access: {0}'.format(ip))
            return render.info(u'You must be logged in to access this page.  Please login using your account information.')
        # No task chosen
        if not taskdir:
            io_extra.log(u'EDITOR: no task selected: {0} {1}'.format(ip, user))
            return render.info(u'You must select a translation task.')
        # Set task in session
        session.task = taskdir
        # Load task data from task dir and database
        db = trans_db[taskdir]
        if not db:
            db = io_extra.get_trans_db(os.path.join(io_extra.TASK_DIR, taskdir, 'data.db'))
            db.printing = dbg_sql
            trans_db[taskdir] = db
        task = io_extra.task(user, taskdir, db)  # Loads everything into a task object
        # Config for realtime
        rtd[(user, taskdir)] = task.realtime_d
        # Update status in user DB
        res = list(user_db.select(u'status', dict(user=user, task=taskdir), where=u'user = $user and task = $task'))
        if len(res) == 0:
            user_db.insert(u'status', user=user, task=taskdir, status=u'started')
        else:
            user_db.update(u'status', vars=dict(user=user, task=taskdir), where=u'user = $user and task = $task', status=u'started')
        # Update status in task DB
        res = list(db.select(u'status', dict(user=user), where=u'user = $user'))
        db_write_lock.acquire()
        if len(res) == 0:
            db.insert(u'status', user=user, status=u'started')
        else:
            db.update(u'status', vars=dict(user=user), where=u'user = $user', status=u'started')
        db_write_lock.release()
        # Load editor
        return render.editor(task)


class favicon:

    def GET(self):
        f = open(os.path.join(io_extra.ST_DIR, 'favicon.ico'), 'rb')
        return f.read()


class helppage:

    def GET(self):
        email = config['admin_email'].partition('@')
        return render.help(email)


class browsers:

    def GET(self):
        return render.browsers()


class translator:

    def GET(self):
        data = web.input()
        return self.handle(data)        

    def POST(self):
        data = web.input()
        return self.handle(data)

    def handle(self, data):
        global dbg_editor, hub, off_hub
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        task = session.get(u'task')
        realtime_d = rtd[(user, task)]
        # Not logged in
        if not user:
            io_extra.log(u'SUBMIT: unauthorized access: {0}'.format(ip))
            return render.info(u'You must be logged in to access this page.  Please login using your account information.')
        # No task chosen
        if not task:
            io_extra.log(u'SUBMIT: no task selected: {0} {1}'.format(ip, user))
            return render.info(u'You must select a translation task.')
        # Translation data
        next_id = data[u'i']
        source = data[u's']
        if source == '':
            source = None
        reference = data[u'r']
        if reference == '':
            reference = None
        next = data[u'n']
        if next == '':
            next = None
        t = data[u't']
        static = (t == track.REALTIME_STATIC)
        # First sentence for a non-static translator? (don't (re)learn)
        first = ((data[u'f'] == 'true') and not static)
        # Editor debugging, don't call hub
        if dbg_editor:
            io_extra.log(u'DBG-HUB: ({}-{}): {} ||| {} ||| {}'.format(user, task, source, reference, next))
            return 'test string'
        # Offline translation
        if task in off_hub:
            if next:
                translation = off_hub[task][next]
                trans_db[task].insert(u'mt', time=int(time.time() * 1000), user=user, sent=next_id, text=translation)
                return translation
            return None
        #                   All static tasks use the same instance
        return hub.interact('STATIC' if static else user, task, realtime_d, source, reference, next, next_id, static, first)


class submit:

    def GET(self):
        data = web.input()
        return self.handle(data)

    def POST(self):
        data = web.input()
        return self.handle(data)

    def handle(self, data):
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        task = session.get(u'task')
        # Not logged in
        if not user:
            io_extra.log(u'SUBMIT: unauthorized access: {0}'.format(ip))
            return render.info(u'You must be logged in to access this page.  Please login using your account information.')
        # No task chosen
        if not task:
            io_extra.log(u'SUBMIT: no task selected: {0} {1}'.format(ip, user))
            return render.info(u'You must select a translation task.')
        ev = track.event(user, task, data)
        edits = ev.get_edits()
        # Sync add to event queue
        queue_lock.acquire()
        ev_queue.append(ev)
        for e in edits:
            ed_queue.append(e)
        queue_lock.release()
        # Debug
        if dbg_track:
            dbg_lock.acquire()
            if ev.event == track.FOCUS:
                dbg_strings[ev.user] = ev.after
                io_extra.log(u'{0}: |{1}|'.format(ev.user, dbg_strings[ev.user]))
            if edits:
                for e in edits:
                    dbg_strings[ev.user] = track.apply_edit(dbg_strings[ev.user], e)
                    io_extra.log(u'{0}: |{1}| {2} {3}'.format(e.user, dbg_strings[ev.user], e.caret, e.data))
            else:
                io_extra.log(u'{0}'.format(ev))
            dbg_lock.release()


class done:

    def GET(self):
        ip = web.ctx.get(u'ip')
        user = session.get(u'user')
        task = session.get(u'task')
        # Not logged in
        if not user:
            io_extra.log(u'DONE: unauthorized access: {0}'.format(ip))
            return render.info(u'You must be logged in to access this page.  Please login using your account information.')
        # No task chosen
        if not task:
            io_extra.log(u'DONE: no task selected: {0} {1}'.format(ip, user))
            return render.info(u'You must select a translation task.')
        # Mark task completed in user DB
        res = list(user_db.select(u'status', dict(user=user, task=task), where=u'user = $user and task = $task'))
        if len(res) == 0:
            user_db.insert(u'status', user=user, task=task, status=u'finished')
        else:
            user_db.update(u'status', vars=dict(user=user, task=task), where=u'user = $user and task = $task', status=u'finished')
        # Mark task in task DB
        # Rely on task DB for reporting status and possible errors
        db = trans_db[task]
        res = list(db.select(u'status', dict(user=user), where=u'user = $user'))
        if len(res) == 0:
            db.insert(u'status', user=user, status=u'finished')
            io_extra.log(u'DONE: Error?  Task finished before started: {0} {1} {2}'.format(ip, user, task))
        else:
            db.update(u'status', vars=dict(user=user), where=u'user = $user', status=u'finished')
            io_extra.log(u'DONE: User finished task: {0} {1} {2}'.format(ip, user, task))
        return render.gotolist()


class admin:

    def POST(self):
        ip = web.ctx.get(u'ip')
        data = web.input()
        password = data.get(u'adminpass')
        if password != config[u'admin_password']:
            io_extra.log(u'ADMIN: bad admin password: {0}'.format(ip))
            return render.info(u'Incorrect admin password.')
        # Logged in as admin
        session.admin = True
        return render.admin()


# Attempt to add new user
# Return status (success, log_msg, user_msg)
def add_user(ip, user, code, password, email):
    # Check code
    if code not in groups:
        return (False,
                u'REG: Bad group code: {0} {1}'.format(ip, code),
                u'The group code you provided does not match any existing group.  Please make sure your group code is correct.')
    # Check email
    if len(list(user_db.select(u'users', dict(email=email), where=u'email = $email'))) != 0:
        return (False,
                u'REG: Duplicate email: {0} {1}'.format(ip, email),
                u'This email address is already registered.  Use the Recover Account option to retrieve your login information.')
    # Check user ID
    if len(list(user_db.select(u'users', dict(user=user), where=u'user = $user'))) != 0:
        return (False,
                u'REG: Duplicate user ID: {0} {1}'.format(ip, user),
                u'User ID {0} has already been taken.  Please select another user ID.'.format(user))
    # Success: store new user in database
    db_write_lock.acquire()
    user_db.insert(u'users', user=user, password=password, groupname=groups[code], email=email)
    db_write_lock.release()
    return (True,
            u'REG: New user: {0} {1} {2}'.format(ip, user, email),
            u'Registration successful.  Please login with your new account.')

# Attempt to recover account
# Return status (success, log_msg, user_msg)
def recover_account(ip, email):
    res = list(user_db.select(u'users', dict(email=email), where=u'email = $email'))
    # No match
    if len(res) == 0:
        return (False,
                u'REC: Bad email: {0} {1}'.format(ip, email),
                u'Email address not registered.')
    # Success: this can take awhile.  Start a separate thread.
    def send_account(*args):
        web.sendmail(*args)
        io_extra.log(u'REC: Account info sent: {0}'.format(email))
    threading.Thread(target=send_account,
                     args=(config[u'from_email'],
                           res[0][u'email'],
                           u'TransCenter Account Information',
                           u'TransCenter Account Information:\nUser ID: {0}\nPassword: {1}'.format(res[0]['user'],
                                                                                                  res[0]['password']))).start()
    return (True,
            u'REC: Sending acount info: {0} {1}'.format(ip, email),
            u'Your password will be emailed to you shortly.  ' + \
            u'If you do not get an email from TransCenter within 20 minutes, please try again.  ' + \
            u'If multiple recovery attempts fail, an administrator can send you your login information.  ' + \
            u'Be sure to check your spam folder in case your email provider thinks the message is unsolicited.')


def main(argv):
    global dbg_editor, dbg_sql, dbg_track, hub, off_hub

    # Unicode I/O
    sys.stdin = codecs.getreader('UTF-8')(sys.stdin)
    sys.stdout = codecs.getwriter('UTF-8')(sys.stdout)
    sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)

    if len(argv[1:]) > 0 and argv[1] in ('-h', '--help'):
        print >> sys.stderr, u'TransCenter Live Server'
        print >> sys.stderr, u'Usage: {0} [-p port=8080] [-t timeout=600] [--dbg-editor] [--dbg-sql] [--dbg-track] [--dbg-webpy]'.format(argv[0])
        print >> sys.stderr, u'(crtl+c to stop server)'
        sys.exit(2)

    opts, argv = getopt.getopt(argv[1:], 'p:t:', ['dbg-editor', 'dbg-sql', 'dbg-track', 'dbg-webpy'])
    sys.argv = [sys.argv[0]]
    test_file = False
    timeout = 600
    for o, a in opts:
        if o == '-p':
            sys.argv.append(a)
        elif o == '-t':
            timeout = int(a)
        elif o == '--dbg-editor':
            dbg_editor = True
        elif o == '--dbg-sql':
            dbg_sql = True
            user_db.printing = dbg_sql
        elif o == '--dbg-track':
            dbg_track = True
        elif o == '--dbg-webpy':
            web.config['debug'] = True

    # Realtime hub
    io_extra.log(u'STATUS: starting Realtime hub...')
    hub = rt_hub.RealtimeHub(trans_db, db_write_lock, timeout=timeout) if not dbg_editor else None
    # [task][source] = target
    off_hub = {}
    # Init translators
    # TODO: change to on-demand/timeout
    for task in sorted((f for f in os.listdir(io_extra.TASK_DIR) if f.endswith('.data'))):
        config = io_extra.read_cfg(os.path.join(io_extra.TASK_DIR, task, 'config.txt'))
        if config['task'] in (track.REALTIME, track.REALTIME_STATIC):
            realtime_d = config['config']
            hub.manual_start(realtime_d)
        # Load offline data
        elif config['task'] == 'offline':
            off_hub[task] = dict((s.strip(), t.strip()) for (s, t) in itertools.izip(codecs.open(os.path.join(io_extra.TASK_DIR, task, 'source.txt'), 'rb', 'UTF-8'), codecs.open(os.path.join(io_extra.TASK_DIR, task, 'target.txt'), 'rb', 'UTF-8')))

    io_extra.log(u'STATUS: Realtime hub started.')

    # Database writer
    writer = threading.Thread(target=io_extra.run_database_writer, args=(trans_db, db_write_lock, ev_queue, ed_queue, queue_lock))
    writer.start()
    io_extra.log(u'STATUS: Database writing started.')

    # Start web app
    io_extra.log(u'STATUS: Main webpy app starting.')
    app.run()

    # Cleanup
    ev_queue.append(None)
    if not dbg_editor:
        hub.close()
    io_extra.log(u'STATUS: Realtime hub closed.')
    writer.join()
    io_extra.log(u'STATUS: All database writes finished.')
    session_store.cleanup(0)
    io_extra.log(u'STATUS: Ready to shutdown.')

if __name__ == '__main__':
    main(sys.argv)
