#!/usr/bin/env python

import sys
from io_extra import new_trans_db, new_user_db

def main(argv):

    if len(argv[1:]) != 2:
        print >> sys.stderr, 'Create new SQLite databases for TransCenter'
        print >> sys.stderr, ''
        print >> sys.stderr, 'Usage: {0} <type> <out.db>'.format(argv[0])
        print >> sys.stderr, ''
        print >> sys.stderr, 'Databse types:'
        print >> sys.stderr, 'user   data/user.db'
        print >> sys.stderr, 'trans  data/trans/dataset_name.db'
        print >> sys.stderr, ''
        print >> sys.stderr, 'This script should only need to be run during development'
        sys.exit(2)

    db_type = argv[1]
    db_file = argv[2]

    if db_type == 'user':
        new_user_db(db_file)
    elif db_type == 'trans':
        new_trans_db(db_file)
    else:
        print >> sys.stderr, 'Unknown database type.  See help message.'
        sys.exit(1)

if __name__ == '__main__':
    main(sys.argv)
