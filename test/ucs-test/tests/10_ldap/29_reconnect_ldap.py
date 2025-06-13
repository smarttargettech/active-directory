#!/usr/share/ucs-test/runner python3
## desc: test automatic reconnect of uldap.py
## tags: [skip_admember,reconnect]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - python3-univention-directory-manager
##   - python3-univention

import subprocess
import threading
import time

from ldap import LDAPError

from univention.uldap import getMachineConnection


failed = False
run_time = 10.0


def search_thread():
    global failed
    lo = getMachineConnection()
    lo.lo._retry_max = 10E4
    lo.lo._retry_delay = .001
    x = 0
    lo.search(filter="uid=Administrator", attr=["uid"])
    s = time.monotonic()
    print("go")
    while (time.monotonic() - s) < run_time:
        x += 1
        try:
            lo.search(filter="uid=Administrator", attr=["uid"])
        except LDAPError:
            failed = True
    print(f"Searches per sec: {x / run_time}")


def main():
    thread_count = 100
    my_thread = [None] * thread_count
    for i in range(thread_count):
        my_thread[i] = threading.Thread(target=search_thread)
    for t in my_thread:
        t.start()

    print("warmup")
    time.sleep(3)

    print("restart slapd")
    subprocess.check_call(["systemctl", "restart", "slapd.service"])
    print("restarted")

    for t in my_thread:
        t.join()

    print("done")
    assert not failed


if __name__ == '__main__':
    try:
        main()
    finally:
        subprocess.check_call(["systemctl", "restart", "slapd.service"])
