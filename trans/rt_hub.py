import collections
import os
import StringIO
import sys
import threading
import time

import io_extra

# Try to import realtime
try:
    import rt
except ImportError as ie:
    try:
        rt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'cdec', 'realtime')
        sys.path.append(rt_path)
        import rt
    except:
        sys.stderr.write('Error: cannot import rt.  Make sure Realtime (cdec/realtime) is on your Python path.\n')
        raise ie

class RealtimeHub:

    def __init__(self, trans_db, db_write_lock, timeout=600):
        self.timeout = timeout
        self.clean_freq = min(60, timeout)
        self.db = trans_db
        self.db_lock = db_write_lock
        # realtime_d -> RealtimeTranslator
        self.tr = {}
        self.tr_locks = collections.defaultdict(rt.util.FIFOLock)
        self.tr_nctx = collections.defaultdict(int)
        # Set of (user, task)
        self.ids = set()
        self.id_locks = collections.defaultdict(rt.util.FIFOLock)
        self.id_rtd = {}
        # Last use (for timeout)
        self.last = {}
        self.cleaner = threading.Thread(target=self.keep_clean)
        self.cleaner_lock = rt.util.FIFOLock()
        self.next_clean = int(time.time()) + self.clean_freq
        self.cleaner.start()

    def close(self):
        self.cleaner_lock.acquire()
        self.next_clean = 0
        self.cleaner_lock.release()
        for realtime_d in self.tr:
            self.tr[realtime_d].close()

    # Every minute, drop inactive contexts, check for zero-context translators
    # Check for action every second to handle clean shutdown
    def keep_clean(self):
        while True:
            time.sleep(1)
            self.cleaner_lock.acquire()
            # Done
            if self.next_clean == 0:
                break
            now = int(time.time())
            if now >= self.next_clean:
                for id in list(self.ids):
                    id_lock = self.id_locks[id]
                    id_lock.acquire()
                    try:
                        # Drop context
                        if now - self.last[id] >= self.timeout:
                            io_extra.log(u'HUB: id timeout: {}'.format(id))
                            self.drop(id)
                            # Check if translator closes
                            rtd = self.id_rtd.pop(id)
                            tr_lock = self.tr_locks[rtd]
                            tr_lock.acquire()
                            self.tr_nctx[rtd] -= 1
                            # Close if 0 active contexts
                            # Currently disabled due to segfault in grammar extractor in Cython-generated code after restart
                            # TODO: investigate what's causing this so we can free idle translators
                            if False and self.tr_nctx[rtd] == 0:
                                io_extra.log(u'HUB: closing translator: {}'.format(rtd))
                                tr = self.tr.pop(rtd)
                                tr.close()
                                self.tr_locks.pop(rtd)
                                self.tr_nctx.pop(rtd)
                            tr_lock.release()
                    except:
                        io_extra.log(u'HUB: id error (likely forced restart): {}'.format(id))
                    id_lock.release()
                self.next_clean = int(time.time()) + self.clean_freq
            self.cleaner_lock.release()

    def manual_start(self, realtime_d):
        tr_lock = self.tr_locks[realtime_d]
        tr_lock.acquire()
        tr = self.tr.get(realtime_d, None)
        if not tr:
            io_extra.log(u'HUB: starting new translator: {}'.format(realtime_d))
            tr = rt.RealtimeTranslator(realtime_d, norm=True)
            self.tr[realtime_d] = tr
        else:
            io_extra.log(u'HUB: already active: {}'.format(realtime_d))
        tr_lock.release()
 
    def drop(self, id, keep_lock=False):
        self.ids.remove(id)
        self.last.pop(id)
        if not keep_lock:
            self.id_locks.pop(id)
        self.tr[self.id_rtd[id]].drop_ctx(id)


    def interact(self, user, task, realtime_d, source, reference, next, next_id, static=False, first=False):
        '''In order:
        - learn from source-reference
        - save state
        - translate next
        First sentence: source and reference == None
        Last sentence: next == None
        Each user-task pair should map to ONE realtime_d
        Each realtime_d can serve MANY user-task pairs across users and tasks
        '''
        # Id is user-task.  One translator can have multiple entries for same user or task, but user-task is unique.
        id = u'{}-{}'.format(user, task)
        id_lock = self.id_locks[id]
        id_lock.acquire()
        # Get rtd, translator by id
        rtd = self.id_rtd.get(id, None)
        if not rtd:
            rtd = realtime_d
            self.id_rtd[id] = rtd
        tr_lock = self.tr_locks[rtd]
        tr_lock.acquire()
        tr = self.tr.get(rtd, None)
        # Start translator if needed
        if not tr:
            io_extra.log(u'HUB: starting new translator: {}'.format(rtd))
            tr = rt.RealtimeTranslator(rtd, norm=True)
            self.tr[rtd] = tr
        # Force context restart if first sentence requested (editor re-start)
        if first and id in self.ids:
            io_extra.log(u'HUB: editor restart detected, forcing restart: {}'.format(id))
            self.drop(id, keep_lock=True)
            self.tr_nctx[rtd] -= 1
        # Start context if needed
        if id not in self.ids:
            self.ids.add(id)
            # Count as context for realtime_d
            self.tr_nctx[rtd] += 1
            # Release lock after handling possible first context start to avoid cleaner removing immediately (0 contexts)
            tr_lock.release()
            # Load state if present
            db = self.db[task]
            self.db_lock.acquire()
            res = list(db.select(u'state', dict(user=user), where=u'user = $user', order=u'time DESC'))
            self.db_lock.release()
            if len(res) > 0:
                io_extra.log(u'HUB: starting context and loading state: {} ({}) {}'.format(rtd, self.tr_nctx[rtd], id))
                #                                      convert to utf-8 for Realtime
                sio = StringIO.StringIO(res[0]['state'].encode('utf-8'))
                tr.load_state(sio, id.encode('utf-8'))
            else:
                io_extra.log(u'HUB: starting new context: {} ({}) {}'.format(rtd, self.tr_nctx[rtd], id))
        else:
            # Release lock immediately if id exists
            tr_lock.release()
        io_extra.log(u'HUB: interact ({}): {} ||| {} ||| {}'.format(id, source, reference, next))
        # Learn and update state in DB unless first sentence or static
        if not static and None not in (source, reference):
            # Learn
            # Give Realtime utf-8-ecoded text
            tr.learn(source.encode('utf-8'), reference.encode('utf-8'), id.encode('utf-8'))
            # Save state at time
            sio = StringIO.StringIO()
            tr.save_state(sio, id.encode('utf-8'))
            db = self.db[task]
            self.db_lock.acquire()
            #                                        milliseconds                                       store unicode
            db.insert(u'state', time=int(time.time() * 1000), user=user, state=sio.getvalue().decode('utf-8'))
            self.db_lock.release()
        # Translate, except last sentence
        hyp = None
        if next is not None:
            # Translate
            # Give Realtime utf-8-ecoded text
            hyp = tr.translate(next.encode('utf-8'), id.encode('utf-8')).decode('utf-8')
            db = self.db[task]
            self.db_lock.acquire()
            #                                     milliseconds                      already unicode
            db.insert(u'mt', time=int(time.time() * 1000), user=user, sent=next_id, text=hyp)
            self.db_lock.release()
        # last before release/return
        self.last[id] = int(time.time())
        id_lock.release()
        return hyp
