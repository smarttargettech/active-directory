#!/usr/share/ucs-test/runner python3
## desc: http-proxy-ntlm-auth-perfomance-check
## roles: [domaincontroller_master, domaincontroller_backup, domaincontroller_slave]
## exposure: dangerous
## packages: [univention-squid]
## bugs: [26452,37931]
## tags:
##   - performance

import os
import time

import apt
import pycurl
from atexit import register

import univention.testing.ucr as ucr_test
from univention.config_registry import handler_set, handler_unset
from univention.testing import utils

from essential.simplesquid import SimpleSquid


def max_duration():
    meta_packages = ['ucs-school-multiserver', 'ucs-school-singleserver', 'ucs-school-replica']
    apt_cache = apt.Cache()
    apt_cache.open()
    for pkg in meta_packages:
        if pkg in apt_cache and apt_cache[pkg].is_installed:
            return 180
    return 150  # EC2 m3.medium PV


def doJobs(job, num):
    children = set()
    start = time.monotonic()
    for _ in range(num):
        child = os.fork()
        if child:
            os.write(1, b'<')
            children.add(child)
        else:
            os._exit(job.run())
    # wait for the children and check the status
    while children:
        pid, status = os.waitpid(0, 0)
        os.write(1, b'>')
        if os.WIFSIGNALED(status):
            utils.fail('job %d failed with signal %d' % (pid, os.WTERMSIG(status)))
        elif os.WIFEXITED(status) and os.WEXITSTATUS(status):
            utils.fail('job %d failed with status %d' % (pid, os.WEXITSTATUS(status)))
        children.remove(pid)
    end = time.monotonic()
    os.write(1, b" %.2f\n" % (end - start,))


class Job:

    def __init__(self, ucr):
        self.account = utils.UCSTestDomainAdminCredentials()
        self.host = '%(hostname)s.%(domainname)s' % ucr
        self.url = 'http://' + self.host + '/univention/'

    def run(self):
        c = pycurl.Curl()
        try:
            c.setopt(pycurl.PROXY, self.host)
            c.setopt(pycurl.PROXYPORT, 3128)
            c.setopt(pycurl.PROXYAUTH, pycurl.HTTPAUTH_NTLM)
            c.setopt(pycurl.PROXYUSERPWD, f"{self.account.username}:{self.account.bindpw}")
            c.setopt(pycurl.URL, self.url)
            c.setopt(pycurl.NOBODY, 1)
            try:
                c.perform()
                # check if NTLM auth is available
                if c.getinfo(pycurl.PROXYAUTH_AVAIL) is not pycurl.HTTPAUTH_NTLM:
                    return 2
                # check http code
                if c.getinfo(pycurl.HTTP_CODE) == 200:
                    return 0
            except pycurl.error as ex:
                print(ex)
                return 1
        finally:
            c.close()
        return 0


def main():
    squid = SimpleSquid()
    duration = -1
    with ucr_test.UCSTestConfigRegistry() as ucr:
        # set up squid
        handler_unset(['squid/basicauth', 'squid/krb5auth'])
        handler_set(['squid/ntlmauth=yes'])
        squid.restart()
        register(squid.restart)
        time.sleep(3)

        start = time.monotonic()

        # /var/log/syslog: (squid) Too many queued ntlmauthenticator requests
        # <http://wiki.squid-cache.org/KnowledgeBase/TooManyQueued>
        total = 30 + 60 * 40  # 30 for cold-LDAP-cache, 40 for hot-cache
        MAX_CONCURRENT = 2 * int(ucr.get("squid/ntlmauth/children", 10)) * 2 + 1
        concurrent = 0

        job = Job(ucr)
        while total > 0:
            concurrent = min(concurrent + 1, MAX_CONCURRENT, total)
            doJobs(job, concurrent)
            total -= concurrent

        end = time.monotonic()
        duration = end - start
        print(f'Test took {duration:.2f} seconds')

    MAX_DURATION = max_duration()
    if duration > MAX_DURATION:
        utils.fail('test took too long (%.2f > %d)' % (duration, MAX_DURATION))


if __name__ == '__main__':
    main()
