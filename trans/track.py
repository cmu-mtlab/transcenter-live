#!/usr/bin/env python

# Translation tasks
TASKS = (REALTIME, REALTIME_STATIC, OFFLINE) = ('realtime', 'realtime-static', 'offline')
TASK_DESCS = ('Realtime Translation Post-Editing', 'Realtime Translation Post-Editing', 'Offline Translation Post-Editing')
TASK_DICT = dict(zip(TASKS, TASK_DESCS))

# Edit operations
EDIT_CODES = (u'-', u'd', u'i')
EDITS = (SAME, DEL, INS) = (0, 1, 2)
EDIT_SET = set(EDITS)
EDIT_DICT = dict(zip(EDIT_CODES, EDITS))
EDIT_UNDICT = dict(zip(EDITS, EDIT_CODES))

# Events (including rewrites but not atomic edits)
EV_CODES = (u'f', u'b', u's', u'r', u'pa', u're', u'kc', u'mc', u'rw', u'co', u'sc')
EVENTS = (FOCUS, BLUR, SUBMIT, RATE, PAUSE, RESUME, KC, MC, RW, COPY, SCOPY) = (100, 101, 102, 103, 104, 105, 106, 107, 108, 109, 110)
EV_SET = set(EVENTS)
EV_DICT = dict(zip(EV_CODES, EVENTS))
EV_UNDICT = dict(zip(EVENTS, EV_CODES))

# Single event from editor (including rewrites but not atomic edits)
class event:

    def __init__(self, user, task, webdata):

        self.user = user
        self.task = task
        self.time = long(webdata[u't'])
        self.sent = int(webdata[u'i'] or 0)
        self.event = EV_DICT[webdata[u'e']]
        self.start = int(webdata[u's'] or 0)
        self.before = webdata[u'b']
        self.after = webdata[u'a']

    def __str__(self):
        return u'event({{time: {time}, user: {user}, task: {task}, sent: {sent}, event: {event}, start: {start}, before: {before}, after: {after}}})'.format(
            time=self.time, user=self.user, task=self.task, sent=self.sent, event=EV_UNDICT[self.event], start=self.start, before=self.before, after=self.after)

    def get_edits(self):
        edits = []
        if self.event == RW:
            # Rewrites send a start position and substrings of the sentence.  The diff region is calculated client-side
            for (op, pos, data) in report_str_diff(self.before, self.after):
                edits.append(edit(self, self.start + pos, op, data))
        elif self.event in (COPY, SCOPY):
            edits.append(edit(self, self.start, self.event, self.after))
        return edits


# Single atomic edit (insert, delete, copy, source copy)
class edit:

    def __init__(self, ev, caret, op, data):
        self.time = ev.time
        self.user = ev.user
        self.task = ev.task
        self.sent = ev.sent
        self.caret = caret
        self.op = op
        self.data = data

    def __str__(self):
        return u'edit({{time: {time}, user: {user}, task: {task}, sent: {sent}, caret: {caret}, op: {op}, data: {data}}})'.format(
            time=self.time, user=self.user, task=self.task, sent=self.sent, caret=self.caret, op=EDIT_UNDICT[self.op], data=self.data)


def apply_edit(s, ed):
    if ed.op == DEL:
        return s[0:ed.caret] + s[ed.caret+len(ed.data):]
    elif ed.op == INS:
        return s[0:ed.caret] + ed.data + s[ed.caret:]
    elif ed.op in (COPY, SCOPY):
        return s

# Modified Levenshtein distance: insertions and deletions only,
# group operations of the same type when possible.
# Returns (dist, path), path rewrites src as tgt
def str_diff(src, tgt):

    d = [[]] * (len(src) + 1) # distance
    p = [[]] * (len(src) + 1) # path

    # Init
    for i in range(0, len(src) + 1):
        d[i] = [0] * (len(tgt) + 1)
        p[i] = [0] * (len(tgt) + 1)

    for i in range(1, len(src) + 1):
        d[i][0] = i
        p[i][0] = DEL

    for j in range(1, len(tgt) + 1):
        d[0][j] = j
        p[0][j] = INS

    # Shortest path with operation switch cost
    for j in range(1, len(tgt) + 1):
        for i in range(1, len(src) + 1):
            d_sam = (d[i-1][j-1] + (0 if p[i-1][j-1] == SAME else 0.01)) if src[i-1] == tgt[j-1] else -1
            d_del = d[i-1][j] + 1 + (0 if p[i-1][j] == DEL else 0.01)
            d_ins = d[i][j-1] + 1 + (0 if p[i][j-1] == INS else 0.01)
            if d_sam != -1 and d_sam < d_del and d_sam < d_ins:
                d[i][j] = d_sam
                p[i][j] = SAME
            elif d_del < d_ins:
                d[i][j] = d_del
                p[i][j] = DEL
            else:
                d[i][j] = d_ins
                p[i][j] = INS

    # Back-trace
    i = len(src)
    j = len(tgt)
    dist = d[i][j]
    path = []
    while i > 0 or j > 0:
        path.append(p[i][j])
        if p[i][j] == DEL:
            i -= 1
        elif p[i][j] == INS:
            j -= 1
        else:
            i -= 1
            j -= 1
    path.reverse()  # Reverse back-trace to get trace

    return (dist, path)

# (Mostly) linear time string diff for strings with a single edit
def fast_str_diff(src, tgt):
    i = 0
    min_len = min(len(src), len(tgt))
    while (i < min_len and src[i] == tgt[i]):
        i += 1
    j = 1
    while (j < min_len and src[-j] == tgt[-j]):
        j += 1
    j -= 1
    # Overlap
    overlap = i - min(len(src) - j, len(tgt) - j)
    if overlap > 0:
        # Move back i until it hits the beginning of the string, then move back j
        i -= overlap
        underflow = i
        if underflow < 0:
            i = 0
            j += -underflow
    src_part = src[i:-j] if j > 0 else src[i:]
    tgt_part = tgt[i:-j] if j > 0 else tgt[i:]
    diff = str_diff(src_part, tgt_part)
    path = [SAME] * i + diff[1] + [SAME] * j
    #print i, j
    #print '|{}| |{}|'.format(src_part, tgt_part)
    #print '|{}| |{}|'.format(src, tgt)
    #print str_diff(src, tgt)[1]
    #print cheap
    return (diff[0], path)

# Log differences between two strings
def report_str_diff(test, ref, fast=False):
    path = fast_str_diff(test, ref)[1] if fast else str_diff(test, ref)[1]
    res = []
    last_op = SAME
    t = 0
    r = 0
    op_start = -1  # start of last op in t or r
    pos = 0  # position in working string
    for i in range(len(path)):
        if path[i] != last_op:
            if last_op == DEL:
                res.append((DEL, pos, test[op_start:t]))
                #  Deleting text does not advance the caret
            elif last_op == INS:
                res.append((INS, pos, ref[op_start:r]))
                #  Inserting text advances the caret
                pos += (r - pos)
            op_start = t if path[i] == DEL else r
        if path[i] == SAME:
            t += 1
            r += 1
            pos += 1
        elif path[i] == DEL:
            t += 1
        elif path[i] == INS:
            r += 1
        last_op = path[i]
    if last_op == DEL:
        res.append((DEL, pos, test[op_start:t]))
    elif last_op == INS:
        res.append((INS, pos, ref[op_start:r]))
    return res
