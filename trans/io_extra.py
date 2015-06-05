#!/usr/bin/env python

import codecs, collections, datetime, os, re, sqlite3, sys, time, traceback

import web

import track

DIR = os.path.dirname(os.path.dirname(__file__))
T_DIR = os.path.join(DIR, 'templates')
ST_DIR = os.path.join(DIR, 'static')
DATA_DIR = os.path.join(DIR, 'data')
LOG_DIR = os.path.join(DIR, 'log')
TASK_DIR = os.path.join(DATA_DIR, 'tasks')
WEB_DB = os.path.join(DATA_DIR, 'web.db')

log_out = None  # stream to log file if open

# An instance of a task accepted by a user.
# Class contains data to be sent to editor template.
# Data is always escaped.
class task:

    post_ratings = [
        (0, u'Rate Translation'),
        (5, u'5 - Very Good'),
        (4, u'4 - Usable'),
        (3, u'3 - Neutral'),
        (2, u'2 - Non-usable'),
        (1, u'1 - Gibberish'),
        ]

    def __init__(self, user, t_dir, t_db):

        self.user = user
        self.config = read_cfg(os.path.join(TASK_DIR, t_dir, 'config.txt'))
        self.task = self.config['task']
        self.name = self.config['name']
        if self.task in (track.REALTIME, track.REALTIME_STATIC):
            self.realtime_d = self.config['config']
        else:
            self.realtime_d = None

        self.left_title = u'Source'
        self.right_title = u'Translation'
        self.left = [line for line in read_utf8_iter(os.path.join(TASK_DIR, t_dir, 'source.txt'))]
        self.right = [''] * len(self.left)
        self.ratings = task.post_ratings
        self.static = (self.task == track.REALTIME_STATIC)

        self.user_trans = [-1] * len(self.left)
        times = [0] * len(self.left)
        res = t_db.select(u'translations', dict(user=user), where=u'user = $user')
        for r in res:
            i = r['sent'] - 1
            t = r['time']
            if t > times[i]:
                times[i] = t
                self.user_trans[i] = r['text']

        self.user_ratings = [0] * len(self.left)
        times = [0] * len(self.left)
        res = t_db.select(u'ratings', dict(user=user), where=u'user = $user')
        for r in res:
            i = r['sent'] - 1
            t = r['time']
            if t > times[i]:
                times[i] = t
                self.user_ratings[i] = r['rating']



# Open a stream to a file with the current second in yyyymmddhhmmss format
# and start logging
def start_logging():
    global log_out
    now = datetime.datetime.today().strftime('%Y%m%d%H%M%S')
    log_file = '{0}.log'.format(now)
    if not os.path.exists(LOG_DIR):
        os.mkdir(LOG_DIR)
    log_out = codecs.open(os.path.join(LOG_DIR, log_file), mode='wb', encoding='UTF-8', buffering=0)

# Print a message to stderr and a log file
def log(msg):
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print >> sys.stderr, u'LOG: {0} : {1}'.format(now, msg)
    if log_out:
        print >> log_out, u'{0} : {1}'.format(now, msg)

def store_event(ev, db):
    # Submit finished sentence
    if ev.event == track.SUBMIT:
        # Normalize whitespace before logging final translation
        text = re.sub(u'\s+', u' ', ev.after, flags=re.UNICODE).strip()
        db.insert(u'translations', time=ev.time, user=ev.user, sent=ev.sent,
            text=text)
    # User has rated translation
    elif ev.event == track.RATE:
        db.insert(u'ratings', time=ev.time, user=ev.user, sent=ev.sent,
            rating=int(ev.after))
    elif ev.event in (track.KC, track.MC):
        db.insert(u'counts', time=ev.time, user=ev.user, sent=ev.sent,
            op=ev.event, count=int(ev.after))
    # All other events
    else:
        db.insert(u'events', time=ev.time, user=ev.user, sent=ev.sent, op=ev.event)

def store_edit(ed, db):
    db.insert(u'edits', time=ed.time, user=ed.user, sent=ed.sent,
            caret=ed.caret, op=ed.op, input=ed.data)

# Every second, write all pending events to databases in batch mode
def run_database_writer(trans_db, db_write_lock, ev_queue, ed_queue, queue_lock):
    done = False
    while not done:
        try:
            time.sleep(1)
            # Sync get all from event queue
            queue_lock.acquire()
            events = list(ev_queue)
            ev_queue.clear()
            edits = list(ed_queue)
            ed_queue.clear()
            queue_lock.release()
            if not events and not edits:
                continue
            # Get lock and open database transactions
            db_write_lock.acquire()
            transact = collections.defaultdict(lambda: None)
            for ev in events:
                # Done event
                if ev == None:
                    done = True
                    continue
                try:
                    # Get database and transaction
                    db = trans_db[ev.task]
                    t = transact[ev.task]
                    if not t:
                        t = db.transaction()
                        transact[ev.task] = t
                    # Execute query
                    store_event(ev, db)
                except Exception:
                    log(u'Database exception writing event: {0}:'.format(ev))
                    log(traceback.format_exc())
            for ed in edits:
                try:
                    # Get database and transaction
                    db = trans_db[ed.task]
                    t = transact[ed.task]
                    if not t:
                        t = db.transaction()
                        transact[ed.task] = t
                    # Execute query
                    store_edit(ed, db)
                except Exception:
                    log(u'Database exception writing edit: {0}:'.format(ed))
                    log(traceback.format_exc())
            # Commit changes to all databases
            for t in transact.itervalues():
                t.commit()
            # Release lock
            db_write_lock.release()
        except Exception as e:
            # Catch exceptions that should only occur at dev time,
            # for example server restarting while editing page is
            # loaded.
            log(u'Database writer thread exception:')
            log(traceback.format_exc())

def get_trans_db(db_file):
    if not os.path.exists(db_file):
        new_trans_db(db_file)
    return web.database(dbn='sqlite', db=db_file)

def new_trans_db(db_file):
    log(u'DB: Creating translation database {0}'.format(db_file))
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    c.execute('''CREATE TABLE status (user text, status text)''')

    c.execute('''CREATE TABLE state (time integer, user text, state text)''')
 
    c.execute('''CREATE TABLE mt (time integer, user text, sent integer,
                 text text)''')

    c.execute('''CREATE TABLE translations (time integer, user text,
                 sent integer, text text)''')

    c.execute('''CREATE TABLE ratings (time integer, user text, sent integer,
                 rating integer)''')

    c.execute('''CREATE TABLE events (time integer, user text, sent integer,
                 op integer)''')

    c.execute('''CREATE TABLE counts (time integer, user text, sent integer,
                 op integer, count integer)''')

    c.execute('''CREATE TABLE edits (time integer, user text, sent integer,
                 caret integer, op integer, input text)''')
   
    c.close()

def get_user_db(db_file):
    if not os.path.exists(db_file):
        new_user_db(db_file)
    return web.database(dbn='sqlite', db=db_file)

def new_user_db(db_file):
    log(u'DB: Creating user database {0}'.format(db_file))
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute('''CREATE TABLE users (user text, password text, groupname text, email text)''')

    c.execute('''CREATE TABLE status (user text, task text, status text)''')
    c.close()

def get_web_db():
    db_file = WEB_DB
    if not os.path.exists(db_file):
        new_web_db(db_file)
    return web.database(dbn='sqlite', db=db_file)

def new_web_db(db_file):
    log(u'DB: Creating web database {0}'.format(db_file))
    conn = sqlite3.connect(db_file)
    c = conn.cursor()

    c.execute('''CREATE TABLE sessions (session_id char(128) UNIQUE NOT NULL, atime timestamp NOT NULL DEFAULT current_timestamp, data text)''')
   
    c.close()

# List available names and tasks in active data dir
# [(t_dir, t_name, task), ...]
def list_tasks(escape=False):
    task_list = []
    tasks = sorted((f for f in os.listdir(TASK_DIR) if f.endswith('.data')))
    for t in tasks:
        d = read_cfg(os.path.join(TASK_DIR, t, 'config.txt'))
        if escape:
            d['name'] = html_escape(d['name'])
        task_list.append((t, d['name'], track.TASK_DICT[d['task']]))
    return task_list

# Load sentences from task (basename, ends in .data)
# Get [(src1, tr1), (src2, tr2), ...]
def load_data(t, escape=False):
    d_dir = os.path.join(TASK_DIR, t)
    src = read_utf8_iter(os.path.join(d_dir, 'source.txt'))
    tr = read_utf8_iter(os.path.join(d_dir, 'trans.txt'))
    if escape:
        src = (html_escape(line) for line in src)
        tr = (html_escape(line) for line in tr)
    return zip(src, tr)

# Get a user's already submitted translations and ratings from the database
# Returns [(user_tr1, user_rat1), ...]
def get_user_data(n_sents, db, user):

    tr = [-1] * n_sents
    times = [0] * n_sents
    res = db.select(u'translations', dict(user=user), where=u'user = $user')
    for r in res:
        i = r['sent'] - 1
        t = r['time']
        if t > times[i]:
            times[i] = t
            tr[i] = r['text']

    ratings = [0] * n_sents
    times = [0] * n_sents
    res = db.select(u'ratings', dict(user=user), where=u'user = $user')
    for r in res:
        i = r['sent'] - 1
        t = r['time']
        if t > times[i]:
            times[i] = t
            ratings[i] = r['rating']

    return zip(tr, ratings)

def read_utf8(f):
    return [line.strip() for line in codecs.open(f, mode='rb', encoding='UTF-8')]

def read_utf8_iter(f):
    return (line.strip() for line in codecs.open(f, mode='rb', encoding='UTF-8'))

def read_cfg(f):
    return dict((k.strip(), v.strip()) for (k, _, v) in (line.partition(u': ') for line in codecs.open(f, mode='rb', encoding='UTF-8') if ':' in line))

def html_escape(s):
    return s.replace(u'&', u'&amp;').replace(u'<', u'&lt;').replace(u'>', u'&gt;').replace(u'"', u'&quot;').replace(u'\'', u'&apos;')
