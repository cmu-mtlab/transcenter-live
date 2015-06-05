#!/usr/bin/env python

import collections
import os
import shutil
import subprocess
import sys
import tempfile

# Hardcode if auto detect fails
#TOK = '/home/user/cdec/corpus/tokenize-anything.sh'
TOK = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'cdec', 'corpus', 'tokenize-anything.sh')
TER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'lib', 'tercom-0.8.0.jar')

if not os.path.exists(TOK):
    sys.stderr.write('Error: cdec tokenizer not found.  Edit {} as needed.\n'.format(os.path.abspath(__file__)))
    sys.exit(1)

def main(argv):

    if len(argv[1:]) < 1:
        sys.stderr.write('Report editing effort for MT system.  Input files in form task.user.csv, (copied report summaries).\n')
        sys.stderr.write('Usage: {} task1.user1.csv [task1.user2.csv task2.user1.csv ...]\n'.format(argv[0]))
        sys.exit(2)

    files = argv[1:]
    
    work = tempfile.mkdtemp(prefix='eval_mt.')
    tok = subprocess.Popen([TOK, '-u'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    
    edits = collections.defaultdict(list)
    length = collections.defaultdict(list)
    rating = collections.defaultdict(list)

    # Process files
    for f in files:
        sys.stderr.write('{}\n'.format(f))
        (task, user, _) = os.path.basename(f).split('.')
        with open(f) as inp, open(os.path.join(work, 'mt'), 'w') as mt, open(os.path.join(work, 'pe'), 'w') as pe:
            label = dict((k, v) for (v, k) in enumerate(inp.readline().strip().split('\t')))
            e, l, r = [], [], []
            # Files, length, rating
            i = 0
            for line in inp:
                i += 1
                fields = line.strip().split('\t')
                tok.stdin.write('{}\n'.format(fields[label['MT']]))
                mt.write('{}  ({})\n'.format(tok.stdout.readline().strip(), i))
                tok.stdin.write('{}\n'.format(fields[label['Post-Edited']]))
                pe.write('{}  ({})\n'.format(tok.stdout.readline().strip(), i))
                try:
                    rf = float(fields[label['Rating']])
                except:
                    # Default to neutral score if error (None)
                    rf = 3.0
                r.append(rf)
        # HTER
        with open(os.path.join(work, 'out'), 'w') as out, open(os.path.join(work, 'err'), 'w') as err:
            tab = os.path.join(work, 'ter')
            p = subprocess.Popen(['java', '-jar', TER, '-h', os.path.join(work, 'mt'), '-r', os.path.join(work, 'pe'), '-o', 'sum', '-n', tab, '-s'], stdout=out, stderr=err)
            p.wait()
        # Read summary file
        with open(os.path.join(work, 'ter.sum')) as inp:
            for line in inp:
                fields = line.split('|')
                if len(fields) == 9 and fields[0][0].isdigit():
                    e.append(float(fields[6].strip()))
                    l.append(float(fields[7].strip()))
        edits[task].append(e)
        length[task].append(l)
        rating[task].append(r)

    # Compute scores
    total_e = 0.0
    total_l = 0.0
    avg_r = []
    for task in edits:
        users = len(edits[task])
        total_e += sum((sum(vals) / users) for vals in zip(*edits[task]))
        total_l += sum((sum(vals) / users) for vals in zip(*length[task]))
        for val in ((sum(vals) / users) for vals in zip(*rating[task])):
            avg_r.append(val)
    total_h = total_e / total_l
    total_r = sum(avg_r) / len(avg_r)
    sys.stderr.write('HTER: {}\n'.format(total_h))
    sys.stderr.write('Rating: {}\n'.format(total_r))

    # Cleanup
    tok.stdin.close()
    tok.wait()
    shutil.rmtree(work)

if __name__ == '__main__':
    main(sys.argv)
