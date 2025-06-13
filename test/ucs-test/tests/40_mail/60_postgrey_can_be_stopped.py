#!/usr/share/ucs-test/runner python3
## desc: Test postgrey can be stopped
## exposure: careful
## packages: [univention-postgrey]

import subprocess
import time

import psutil

from univention.testing import utils


def is_running(process_name):
    state = False
    for _count in range(5):
        try:
            pinfo = [proc.name() for proc in psutil.process_iter() if proc.name() == process_name]
        except psutil.NoSuchProcess:
            pass
        else:
            if pinfo:
                state = True
                time.sleep(1)
            else:
                time.sleep(1)
    return state


def main():
    # save original state
    postgrey_is_running = is_running('/usr/sbin/postg')

    # Make sure postgrey is running
    if not postgrey_is_running:
        cmd = ['/etc/init.d/postgrey', 'start']
        subprocess.call(cmd, stderr=open('/dev/null', 'w'))

    # /etc/init.d/postgrey stop
    cmd = ['/etc/init.d/postgrey', 'stop']
    subprocess.call(cmd, stderr=open('/dev/null', 'w'))
    if is_running('/usr/sbin/postg'):
        utils.fail('/etc/init.d/postgrey stop did not stop the process')
    else:
        print('** /etc/init.d/postgrey stop stopped the process successfully')

    # revert to original state
    if postgrey_is_running:
        cmd = ['/etc/init.d/postgrey', 'start']
        subprocess.call(cmd, stderr=open('/dev/null', 'w'))


if __name__ == '__main__':
    main()
