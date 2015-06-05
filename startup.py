#!/usr/bin/env python

import sys, time
from multiprocessing import Process

import trans

if __name__ == '__main__':

    # Run TransCenter server in separate process
    p = Process(target=trans.server.main, args=(sys.argv,))

    # Use if we need to force quit
    def term():
        p.terminate()
        print >> sys.stderr, 'Server killed.'
        sys.exit(1)

    # Start server
    try:
        p.start()
        p.join()

    # Guarantee that server shuts down on keyboard interrupt
    except KeyboardInterrupt:
        print >> sys.stderr, 'TransCenter Server interrupted.'
        print >> sys.stderr, 'Giving server 5 seconds to shutdown... (ctrl+c again to kill immediately)'
        try:
            for i in range(20):
                time.sleep(0.25)
                if not p.is_alive():
                    break
            if p.is_alive():
                term()
            else:
                print >> sys.stderr, 'Clean shutdown.'
                sys.exit(0)
        except KeyboardInterrupt:
            term()
