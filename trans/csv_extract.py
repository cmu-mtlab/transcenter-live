#!/usr/bin/env python

import csv, sys

def main(argv):

    if len(argv[1:]) < 1:
        print >> sys.stderr, 'Usage: {0} <csv-file> [col-id]'.format(argv[0])
        print >> sys.stderr, 'Prints column ids, extracts col-id if provided'
        sys.exit(2)

    i = int(argv[2]) if len(argv[1:]) > 1 else -1

    reader = open(argv[1])
    header = reader.readline().strip().split('\t')
    if i == -1:
        print >>sys.stderr, ', '.join(['{0}: {1}'.format(x[1], x[0]) for x in zip(range(len(header)), header)])
        sys.exit(0)

    for line in reader:
        print line.strip().split('\t')[i]

if __name__ == '__main__':
    main(sys.argv)
