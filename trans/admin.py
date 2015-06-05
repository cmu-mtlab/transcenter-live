#!/usr/bin/env python

import codecs, sys

import server

def list_users():
    print u'{0:12}{1:12}{2:12}'.format('User', 'Group', 'Email')
    for res in server.user_db.select('users'):
        print u'{0:12}{1:12}{2:12}'.format(res['user'], res['groupname'], res['email'])

# Different from server since we don't want to actually send email
def recover(email):
    res = list(server.user_db.select(u'users', dict(email=email), where=u'email = $email'))
    if len(res) == 0:
        print u'Email address {0} not registered.'.format(email)
        sys.exit(1)
    else:
        print u'Account information:\nEmail: {0}\nUser ID: {1}\nPassword: {2}'.format(
            res[0]['email'], res[0]['user'], res[0]['password'])
        sys.exit(0)

def main(argv):

    # Unicode I/O
    sys.stdin = codecs.getreader('UTF-8')(sys.stdin)
    sys.stdout = codecs.getwriter('UTF-8')(sys.stdout)
    sys.stderr = codecs.getwriter('UTF-8')(sys.stderr)

    def usage():
        print >> sys.stderr, u'Usage {0} <task> <args>'.format(argv[0])
        print >> sys.stderr, u''
        print >> sys.stderr, u'Tasks:'
        print >> sys.stderr, u''
        print >> sys.stderr, u'adduser <userID> <groupcode> <password> <email>'
        print >> sys.stderr, u'listusers'
        print >> sys.stderr, u'recover <email>'

    if len(argv[1:]) < 1:
        usage()
        sys.exit(2)

    if argv[1] == 'adduser' and len(argv[1:]) == 5:
        (success, log_msg) = server.add_user(u'localhost', argv[2], argv[3], argv[4], argv[5])[:2]
        print log_msg
        if success:
            print u'User {0} successfully added.'.format(argv[2])
            sys.exit(0)
        else:
            print u'Error adding user.'
            sys.exit(1)
    elif argv[1] == 'listusers':
        list_users()
    elif argv[1] == 'recover' and len(argv[1:]) == 2:
        recover(argv[2])
    else:
        usage()
        sys.exit(1)

if __name__ == '__main__':
    main(sys.argv)
