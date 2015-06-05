#!/usr/bin/env python

import sys
from BeautifulSoup import UnicodeDammit

def main(argv):

    if len(argv[1:]) != 2:
        print >> sys.stderr, 'Mystery text goes in, UTF-8 comes out.  No-op on UTF-8 input.'
        print >> sys.stderr, 'Usage: {0} text.in utf8-text.out'.format(argv[0])
        sys.exit(2)

    in_f = open(argv[1])
    out_f = open(argv[2], 'w')

    for line in in_f:
        line = line.rstrip('\n')
        # If not valid utf-8
        try:
            unicode(line, 'utf-8')
        # Try to detect encoding
        except:
            u = UnicodeDammit(line)
            line = u.unicode.encode('utf-8')
        print >> out_f, line

if __name__ == '__main__':
    main(sys.argv)
