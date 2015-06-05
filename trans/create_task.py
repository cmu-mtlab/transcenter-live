#!/usr/bin/env python

import codecs, os, re, sys

import track

def main(argv):

    # Unicode I/O
    sys.stdin = codecs.getreader('UTF-8')(sys.stdin)
    sys.stdout = codecs.getwriter('UTF-8')(sys.stdout)
    sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)

    def usage():
        print >> sys.stderr, u'Create translation task.  All input files should use UTF-8 encoding.'
        print >> sys.stderr, u''
        print >> sys.stderr, u'Realtime post-editing task with feedback:'
        print >> sys.stderr, u'{0} realtime <source> <realtime.d> <task_name> <task_dir.data>'.format(argv[0])
        print >> sys.stderr, u''
        print >> sys.stderr, u'Realtime post-editing task (no adaptation from feedback):'
        print >> sys.stderr, u'{0} realtime-static <source> <realtime.d> <task_name> <task_dir.data>'.format(argv[0])
        print >> sys.stderr, u''
        print >> sys.stderr, u'Offline task (translations pre-generated):'
        print >> sys.stderr, u'{0} offline <source> <target> <task_name> <task_dir.data>'.format(argv[0])
        print >> sys.stderr, u''
 
 
        print >> sys.stderr, u'Place output task directory in data/tasks'
        sys.exit(2)

    task = argv[1] if len(argv) > 1 else ''
    if task == track.REALTIME and len(argv[2:]) == 4:
        new_realtime(*argv[2:], learn=True)
    elif task == track.REALTIME_STATIC and len(argv[2:]) == 4:
        new_realtime(*argv[2:], learn=False)
    elif task == track.OFFLINE and len(argv[2:]) == 4:
        new_offline(*argv[2:])
    else:
        usage()

def new_realtime(source, config, t_name, t_dir, learn=True):
    t_dir = check_dir(t_dir)
    os.mkdir(t_dir)
    cfg_out = codecs.open(os.path.join(t_dir, 'config.txt'), 'wb', 'UTF-8')
    print >> cfg_out, u'name: {0}'.format(t_name)
    print >> cfg_out, u'task: {0}'.format(u'realtime' if learn else u'realtime-static')
    print >> cfg_out, u'config: {}'.format(os.path.abspath(config))
    print >> cfg_out, u'learn: {}'.format(learn)
    cfg_out.close()
    copy_norm(source, os.path.join(t_dir, 'source.txt'))
    print >> sys.stderr, u'New cdec-realtime post-edit task dir: {0}'.format(t_dir)

def new_offline(source, target, t_name, t_dir, learn=True):
    t_dir = check_dir(t_dir)
    os.mkdir(t_dir)
    cfg_out = codecs.open(os.path.join(t_dir, 'config.txt'), 'wb', 'UTF-8')
    print >> cfg_out, u'name: {0}'.format(t_name)
    print >> cfg_out, u'task: {0}'.format(u'offline')
    cfg_out.close()
    copy_norm(source, os.path.join(t_dir, 'source.txt'))
    copy_norm(target, os.path.join(t_dir, 'target.txt'))
    print >> sys.stderr, u'New offline post-edit task dir: {0}'.format(t_dir)

def check_dir(t_dir):
    if not t_dir.endswith('.data'):
        t_dir += '.data'
        print >> sys.stderr, u'Appending .data: {0}'.format(t_dir)
    if os.path.exists(t_dir):
        print >> sys.stderr, u'File {0} exists, exiting'.format(t_dir)
        sys.exit(1)
    return t_dir

def copy_norm(src, dest):
    src_in = codecs.open(src, 'rb', 'UTF-8')
    dest_out = codecs.open(dest, 'wb', 'UTF-8')
    i = 0
    for line in src_in:
        i += 1
        line = re.sub(u'\s+', u' ', line, flags=re.UNICODE)
        print >> dest_out, line.strip()
    dest_out.close()
    return i

if __name__ == '__main__':
    main(sys.argv)
