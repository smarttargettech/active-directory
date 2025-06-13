#!/usr/share/ucs-test/runner python3
## desc: Imap Server with hundreds of connections
## tags: [producttest]
## exposure: dangerous
## packages: [univention-mail-server]

import resource
import subprocess
import time

import psutil

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set

from essential.mailclient import MailClient_SSL


MAX_CONNECTIONS = 700


def run_cmd(cmd):
    """Execute the given command"""
    print('Executing: %r' % (cmd,))
    return subprocess.call(cmd, stderr=open('/dev/null', 'w'))


def set_openfiles_limit(new_limit):
    """
    Set ulimit -n new_limit
    for the current process only
    """
    resource.setrlimit(resource.RLIMIT_NOFILE, new_limit)


def used_memory():
    """
    Get System used memory

    :returns: used memory in bytes
    """
    return psutil.virtual_memory().used / (1024 * 1024.0)


def main():
    with udm_test.UCSTestUDM() as udm:
        with ucr_test.UCSTestConfigRegistry() as ucr:
            domain = ucr.get('domainname')
            host = '%s.%s' % (ucr.get('hostname'), domain)
            password = 'univention'
            usermail = '%s@%s' % (uts.random_name(), domain)
            _userdn, _username = udm.create_user(
                set={
                    'password': password,
                    'mailHomeServer': host,
                    'mailPrimaryAddress': usermail,
                },
            )
            handler_set([
                'mail/dovecot/limits/default_process_limit=2000',
                'mail/dovecot/limits/default_client_limit=2000',
                'mail/dovecot/limits/auth/client_limit=10000',
                'mail/dovecot/limits/anvil/client_limit=8003',
            ])
            run_cmd(['/etc/init.d/dovecot', 'restart'])
            for i in range(10):
                try:
                    imap = MailClient_SSL(host)
                except Exception:
                    print('dovecot is not yet ready... retrying in 2s...')
                    time.sleep(2)
                    continue
                break
            set_openfiles_limit((2048, 2048))
            mem_start = used_memory()
            servers = []
            time_start = time.monotonic()
            for i in range(MAX_CONNECTIONS):
                if i % 20 == 0:
                    print(f'Open connections: {i}/{MAX_CONNECTIONS}')
                imap = MailClient_SSL(host)
                servers.append(imap)
            print('%d IMAP connections are OK (took %f seconds)' % (i + 1, time.monotonic() - time_start))

            time_start = time.monotonic()
            for imap in servers:
                imap.log_in(usermail, password)
            print('%d IMAP logins are OK (took %f seconds)' % (i + 1, time.monotonic() - time_start))
            mem_finish = used_memory()

            time_start = time.monotonic()
            for imap in servers:
                imap.logout()
            print('%d IMAP logouts are OK (took %f seconds)' % (i + 1, time.monotonic() - time_start))

            mem_per_proc = (mem_finish - mem_start) / 1500.0
            print('Memory Used = %.3fMB per connection (Warning: only rough estimation)' % mem_per_proc)


if __name__ == '__main__':
    main()
