#!/usr/bin/env python

import codecs, collections, os, shutil, sqlite3, subprocess, sys, tempfile

import web

import io_extra, track

render = web.template.render(io_extra.T_DIR)

TERCOM = os.path.join(os.path.dirname(__file__), 'lib', 'tercom-0.8.0.jar')

HEADERS = (H_ID,  H_SOURCE,  H_MT,  H_POST_EDITED,  H_REFERENCE,  H_HTER, H_RATING,  H_KEYPRESS,  H_MOUSECLICK,  H_EDITS,  H_TIME) = \
          (u'ID', u'Source', u'MT', u'Post-Edited', u'Reference', u'HTER', u'Rating', u'Keypress', u'Mouseclick', u'Edits', 'Time')

# Min length for a pause
PAUSE_SHORT = 2 * 1000 
PAUSE_MEDIUM = 6 * 1000
PAUSE_LONG = 60 * 1000

# Read stats from database into memory
def get_stats(t_dir):

    header = []  # Column headings
    static_data = []  # Columns that are the same for all users
    users = []  # Users in order
    user_dict = {}  # user_dict[user] = user_i
    user_data = []  # data[user_i][type_i] = [val1, val2, ...]
    col_avg = []  # Does column average (or is static)?
                  # True: average or use static, False: drop in average report

    # Get the directory name / database entry for this task
    task_id = os.path.basename(os.path.abspath(t_dir))

    # Read config
    config = io_extra.read_cfg(os.path.join(t_dir, 'config.txt'))
    task = config[u'task']

    # Populate left/right plus headers (including next header for user input)
    if task in (track.REALTIME, track.REALTIME_STATIC, track.OFFLINE):
        header.append(H_SOURCE)
        col_avg.append(True)
        static_data.append(io_extra.read_utf8(os.path.join(t_dir, 'source.txt')))
        header.append(H_MT)
        col_avg.append(False)
        header.append(H_POST_EDITED)
        col_avg.append(False)

    n_sent = len(static_data[0])  # Source length

    # Pre-pend sentence IDs
    header.insert(0, H_ID)
    static_data.insert(0, range(1, n_sent + 1))
    col_avg.insert(0, True)

    # User Data
    conn = sqlite3.connect(os.path.join(t_dir, 'data.db'))
    c = conn.cursor()

    # Find users who finished this task
    i = 0
    for (u,) in c.execute('''SELECT DISTINCT user FROM status WHERE status='finished' ORDER BY user ASC'''):
        users.append(u)
        user_data.append([])
        user_dict[u] = i
        i += 1

    # MT
    res = c.execute('''SELECT user, sent, text FROM mt ORDER BY user ASC, sent ASC, time ASC''')
    add_vals(user_dict, user_data, res, n_sent, mt=True, task=task)

    # Post-edited
    res = c.execute('''SELECT user, sent, text FROM translations ORDER BY user ASC, sent ASC, time ASC''')
    add_vals(user_dict, user_data, res, n_sent)

    # Compute HTER
    header.append(H_HTER)
    for user in user_data:
        user.append(hter(user[0], user[1], norm=True))

    # Get user ratings
    header.append(H_RATING)
    col_avg.append(True)
    res = c.execute('''SELECT user, sent, rating FROM ratings ORDER BY user ASC, sent ASC, time ASC''')
    add_vals(user_dict, user_data, res, n_sent)

    # Key/mouse counts
    res = c.execute('''SELECT user, sent, op, count FROM counts ORDER BY user ASC, sent ASC, time ASC''')
    header.append(H_KEYPRESS)
    header.append(H_MOUSECLICK)
    col_avg.append(True)
    col_avg.append(True)
    add_km_sums(user_dict, user_data, res, n_sent)

    # User edit counts
    res = c.execute('''SELECT user, sent, caret, op, input FROM edits ORDER BY user ASC, sent ASC, time ASC''')
    header.append(H_EDITS)
    add_edits(user_dict, user_data, res, n_sent)
    col_avg.append(True)

    # Times from sentence focus/blur
    res = c.execute('''SELECT user, sent, op, time FROM events ORDER BY user ASC, sent ASC, time ASC''')
    header.append(H_TIME)
    add_times(user_dict, user_data, res, n_sent)
    col_avg.append(True)

    c.close()

    return (config, header, col_avg, static_data, users, user_data)

# For each user, for each sentence, values from sql res
def add_vals(user_dict, data, res, n_sent, mt=False, task=None):

    vals = [[None for i in range(n_sent)] for i in range(len(user_dict))]  # vals[user_i][sent_i] = data

    for r in res:
        # 0 to cover REALTIME_STATIC that only has mt for user STATIC
        user_i = user_dict.get(r[0], -1)
        # This could be better engineered
        if user_i == -1 and r[0] != 'STATIC':
            continue
        sent_i = r[1] - 1
        # All users share mt for STATIC
        if mt and task == track.REALTIME_STATIC:
            for user_i in user_dict.itervalues():
                vals[user_i][sent_i] = r[2]
        else:
            vals[user_i][sent_i] = r[2]

    for i in range(len(user_dict)):
        data[i].append(vals[i])

def add_km_sums(user_dict, data, res, n_sent):

    key = [[0 for i in range(n_sent)] for i in range(len(user_dict))]  # key[user_i][sent_i] = data
    mouse = [[0 for i in range(n_sent)] for i in range(len(user_dict))]  # mouse[user_i][sent_i] = data

    for r in res:
        user_i = user_dict.get(r[0], -1)
        if user_i == -1:
            continue
        sent_i = r[1] - 1
        vals = key if r[2] == track.KC else mouse
        vals[user_i][sent_i] += r[3]  # Sum key and mouse counts

    for i in range(len(user_dict)):
        data[i].append(key[i])
        data[i].append(mouse[i])

def add_times(user_dict, data, res, n_sent):

    times = [[0 for i in range(n_sent)] for i in range(len(user_dict))]  # times[user_i][sent_i] = data
    # Time sentence last focused
    last_focus = [[-1 for i in range(n_sent)] for i in range(len(user_dict))]  # last_focus[user_i][sent_i] = time

    for r in res:
        user_i = user_dict.get(r[0], -1)
        if user_i == -1:
            continue
        sent_i = r[1] - 1
        op = r[2]
        time = r[3]
        if op == track.FOCUS:
            last_focus[user_i][sent_i] = time
        elif op == track.BLUR:
            last = last_focus[user_i][sent_i]
            if last == -1:
                io_extra.log(u'Warning: mismatched blur ignored: {}'.format(r))
                continue
            times[user_i][sent_i] += (time - last)
            last_focus[user_i][sent_i] = -1
        # else do not count event

    for i in range(len(user_dict)):
        data[i].append(times[i])

def add_edits(user_dict, data, res, n_sent):

    edits = [[0 for i in range(n_sent)] for i in range(len(user_dict))]  # edits[user_i][sent_i] = data

    for r in res:
        user_i = user_dict.get(r[0], -1)
        if user_i == -1:
            continue
        sent_i = r[1] - 1
        edits[user_i][sent_i] += 1  # Count edit actions

    for i in range(len(user_dict)):
        data[i].append(edits[i])


def html_table(csv_file, html_file):

    # Read csv data
    plus_list = lambda x: [(y, []) for y in x]
    data = zip(*[plus_list(line.strip().split(u'\t')) for line in codecs.open(csv_file, mode='rb', encoding='UTF-8')])

    # Add css classes to data
    for col in data:
        if col[0][0] == H_RATING:
            class_rating(col)
        if col[0][0] in (H_SOURCE, H_MT, H_REFERENCE, H_POST_EDITED):
            # Includes header
            for i in range(0, len(col)):
                col[i][1].append(u'sent')
        if col[0][0] in (H_ID, H_RATING, H_KEYPRESS, H_MOUSECLICK, H_EDITS, H_TIME):
            for i in range(1, len(col)):
                col[i][1].append(u'right')

    # Write out report using template
    html_out = codecs.open(html_file, mode='wb', encoding='UTF-8')
    html_out.write(unicode(render.report_table(zip(*data))))
    html_out.close()


def class_rating(col):

    for i in range(1, len(col)):
        n = int(round(float(col[i][0]), 0))
        col[i][1].append(u'rating' + unicode(n))


def report_stats(t_dir, r_dir):

    (config, header, col_avg, static_data, users, user_data) = get_stats(t_dir)

    csv_files = []

    # Write user-specific reports
    for (i, u) in enumerate(users):
        out_f = os.path.join(r_dir, 'summary.' + u + '.csv')
        csv_files.append(out_f)
        out_csv = codecs.open(out_f, mode='wb', encoding='UTF-8')
        print >> out_csv, u'\t'.join(header)
        for row in zip(*static_data + user_data[i]):
            print >> out_csv, u'\t'.join((unicode(e) for e in row))
        out_csv.close()

    # HTML tables from csv files
    for f in csv_files:
        html_table(f, f[:-4] + '.html')


def report_edits_pauses(t_dir, r_dir):

    users = []  # Users in order
    user_dict = {}  # user_dict[user] = user_i
    user_trans = []  # user_trans[user_i][sent_i] = [inter1, inter2]
                     # where intermediate is (left, diff, right, type, time)
    base_trans = collections.defaultdict(dict)  # base_trans[user_i] = list of translations before editing

    # Get the directory name / database entry for this task
    task_id = os.path.basename(os.path.abspath(t_dir))

    # Read config
    config = io_extra.read_cfg(os.path.join(t_dir, 'config.txt'))
    task = config[u'task']

    conn = sqlite3.connect(os.path.join(t_dir, 'data.db'))
    c = conn.cursor()
    # Find users who finished this task
    i = 0
    for (u,) in c.execute('''SELECT DISTINCT user FROM status WHERE status='finished' ORDER BY user ASC'''):
        users.append(u)
        user_dict[u] = i
        i += 1

    # Populate base translations (mt) for each user
    for user in users:
        for (sent, text) in c.execute('''SELECT sent, text FROM mt WHERE user=? ORDER BY sent ASC''', ('STATIC' if task == track.REALTIME_STATIC else user,)):
            base_trans[user][sent] = text
        # Each user starts with a list of intermediates, starting with the base translation
        user_trans.append([[['', t, '', -1, 'start', '']] for (i, t) in sorted(base_trans[user].iteritems())])

    # Read user edits
    res = c.execute('''SELECT user, sent, caret, op, input, time FROM edits ORDER BY user ASC, sent ASC, time ASC''')

    # Trace edits, annotate with types, times
    for r in res:
        user_i = user_dict.get(r[0], -1)
        if user_i == -1:
            continue
        sent_i = r[1] - 1
        caret = r[2]
        op = r[3]
        diff = r[4]
        time = r[5]
        if user_trans[user_i][sent_i][-1][3] in (-1, track.INS):
            prev = u''.join(user_trans[user_i][sent_i][-1][:3])
        elif user_trans[user_i][sent_i][-1][3] == track.DEL:
            prev = u''.join((user_trans[user_i][sent_i][-1][0], user_trans[user_i][sent_i][-1][2]))
        else:
            io_extra.log('Unknown edit op, using emptry string')
            prev = u''
        left = prev[:caret]
        # For deletes, diff overlaps prev, so cut out
        right = prev[caret + len(diff):] if op == track.DEL else prev[caret:]
        if op == track.INS:
            opclass = u'ins'
        elif op == track.DEL:
            opclass = u'del'
        else:
            # Only count inserts and deletes
            continue
        user_trans[user_i][sent_i].append([left, diff, right, op, opclass, unicode(time)])

    # Final outputs
    for trans in user_trans:
        for sent in trans:
            op = sent[-1][3]
            if op == -1:
                prev = sent[-1][1]
            elif op == track.INS:
                prev = u''.join(sent[-1][:3])
            else:
                prev = u''.join((sent[-1][0], sent[-1][2]))
            sent.append(['', prev, '', -1, 'end', ''])

    # Pull initial and final focus/blur times
    res = c.execute('''SELECT user, sent, time FROM events ORDER BY user ASC, sent ASC, time ASC''')
    i = -1
    for r in res:
        user_i = user_dict.get(r[0], -1)
        if user_i == -1:
            continue
        sent_i = r[1] - 1
        # Initial focus
        if sent_i != i:
            user_trans[user_i][sent_i][0][5] = str(r[2])
        else:
            # overwrite with every following record
            user_trans[user_i][sent_i][-1][5] = str(r[2])
        i = sent_i

    # Write user-specific reports (CSV)
    for (i, u) in enumerate(users):
        csv_out = codecs.open(os.path.join(r_dir, 'edits.' + u + '.csv'), mode='wb', encoding='UTF-8')
        print >>csv_out, u'\t'.join(('Time', 'Operation', 'Left', 'Edit', 'Right'))
        for sent_edits in user_trans[i]:
            for edit in sent_edits:
                print >>csv_out, u'\t'.join((edit[5], edit[4], edit[0], edit[1], edit[2]))
            # "empty" line
            print >>csv_out, u'\t'.join(('', '', '', '', ''))
        csv_out.close()

    # Escape everything
    for trans in user_trans:
        for sent in trans:
            for edit in sent:
                edit[0] = io_extra.html_escape(edit[0])
                edit[1] = io_extra.html_escape(edit[1])
                edit[2] = io_extra.html_escape(edit[2])
    c.close()

    # Write user-specific reports (HTML)
    for (i, u) in enumerate(users):
        # Write out report using template
        html_out = codecs.open(os.path.join(r_dir, 'edits.' + u + '.html'), mode='wb', encoding='UTF-8')
        html_out.write(unicode(render.report_edits(user_trans[i])))
        html_out.close()

    # Write user-specific pause reports (CSV only)
    for (i, u) in enumerate(users):
        csv_out = codecs.open(os.path.join(r_dir, 'pause.' + u + '.csv'), mode='wb', encoding='UTF-8')
        print >>csv_out, u'\t'.join(('ID', 'Initial', 'Final', 'Short', 'Medium', 'Long', 'Total Time', 'Pause Time', 'Words', 'APR', 'PWR'))
        for (j, sent_edits) in enumerate(user_trans[i]):
            # Count pauses (initial, final, short, medium, long)
            ip = 0
            fp = 0
            pause = {'s': 0, 'm': 0, 'l': 0, 't': 0}
            total = 0
            words = 0
            apr = 0
            pwr = 0
            def mark_pause(p):
                # Actually a pause
                if p >= PAUSE_SHORT:
                    if p >= PAUSE_LONG:
                        pause['l'] += 1
                    elif p >= PAUSE_MEDIUM:
                        pause['m'] += 1
                    else:
                        # p >= PAUSE_SHORT
                        pause['s'] += 1
                    pause['t'] += p
            # Initial pause:
            ip = 0
            try:
                ip = long(sent_edits[1][5]) - long(sent_edits[0][5])
            except:
                io_extra.log(u'Warning: cannot compute initial pause, setting to 0 for ({}, {})'.format(u, j + 1))
            mark_pause(ip)
            # If edited
            if len(sent_edits) > 2:
                for k in range(2, len(sent_edits) - 1):
                    p = long(sent_edits[k][5]) - long(sent_edits[k - 1][5])
                    mark_pause(p)
                # Final pause
                fp = long(sent_edits[-1][5]) - long(sent_edits[-2][5])
                mark_pause(fp)
            # Total time
            total = 0
            try:
                total = long(sent_edits[-1][5]) - long(sent_edits[0][5])
            except:
                io_extra.log(u'Warning: cannot compute total, setting to 0 for ({}, {})'.format(u, j + 1))
            # Words
            words = len(sent_edits[-1][1].split())
            # Average pause ratio
            allp = pause['s'] + pause['m'] + pause['l']
            try:
                apr = (float(pause['t']) / allp) / (float(total) / words)
            except:
                # No pauses or no words
                apr = 0
            # Pause to word ratio
            pwr = float(allp) / words
            print >>csv_out, u'\t'.join(str(n) for n in (j + 1, ip, fp, pause['s'], pause['m'], pause['l'], total, pause['t'], words, apr, pwr))
        csv_out.close()


def hter(hyps, refs, norm=True):

    work = tempfile.mkdtemp(prefix='ter.')

    h = os.path.join(work, 'hyps')
    mktrans(hyps, h)

    r = os.path.join(work, 'refs')
    mktrans(refs, r)

    out = open(os.path.join(work, 'out'), 'w')
    err = open(os.path.join(work, 'err'), 'w')
    tab = os.path.join(work, 'ter')

    cmd = ['java', '-jar', TERCOM, '-h', h, '-r', r, '-o', 'sum', '-n', tab, '-s']
    if norm:
        cmd.append('-N')
    p = subprocess.Popen(cmd, stdout=out, stderr=err)
    p.wait()
    out.close()
    err.close()

    res = []
    t = open(tab + '.sum')
    while True:
        line = t.readline()
        if line.startswith('Sent Id'):
            t.readline()
            break
    while True:
        line = t.readline()
        if line.startswith('---'):
            break
        res.append(round(float(line.split()[-1]), 2))

    shutil.rmtree(work)
    return res


def mktrans(lines, tmp):
    with codecs.open(tmp, 'w', 'utf-8') as o:
        i = 0
        for line in lines:
            i += 1
            print >>o, u'{0}  ({1})'.format(line, i)
    o.close()


def main(argv):

    # Unicode I/O
    sys.stdin = codecs.getreader('UTF-8')(sys.stdin)
    sys.stdout = codecs.getwriter('UTF-8')(sys.stdout)
    sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)

    if len(argv[1:]) != 2:
        print >> sys.stderr, u'TransCenter Report Generation'
        print >> sys.stderr, u''
        print >> sys.stderr, u'Usage: {0} <task_dir.data> <out_report>'.format(argv[0])
        sys.exit(2)

    t_dir = argv[1]
    r_dir = argv[2]

    if os.path.exists(r_dir):
        print >> sys.stderr, u'Error: directory {0} exists.'.format(r_dir)
        sys.exit(1)
    else:
        os.mkdir(r_dir)

    report_stats(t_dir, r_dir)
    report_edits_pauses(t_dir, r_dir)


if __name__ == '__main__':
    main(sys.argv)
