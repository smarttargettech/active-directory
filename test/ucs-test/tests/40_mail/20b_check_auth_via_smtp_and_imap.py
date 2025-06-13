#!/usr/share/ucs-test/runner python3
## desc: Check authentication via SMTP, IMAP, POP3, sieve, testsaslauthd
## tags: [apptest]
## exposure: dangerous
## packages: [univention-mail-server]

import imaplib
import poplib
import subprocess
import time

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mail import send_mail


class AuthTests:
    def __init__(self, ucr, udm):
        self.ucr = ucr
        self.udm = udm
        self.domain = self.ucr.get('domainname')

        self.username = uts.random_name()
        self.email = '%s@%s' % (self.username, self.domain)
        self.password = 'univention'
        self.userdn, self.username = self.udm.create_user(
            username=self.username,
            set={
                'password': self.password,
                'mailHomeServer': '%s.%s' % (self.ucr.get('hostname'), self.domain),
                'mailPrimaryAddress': self.email,
            },
        )

    def test_smtp_auth(self, user):
        try:
            send_mail(
                sender=self.email,
                recipients=['noreply@univention.de'],
                port=587,
                tls=True,
                ssl=False,
                username=self.email,
                password=self.password)
            print(f'>>> test_smtp_auth({user}): successfully sent mail - auth is ok')
            return True
        except Exception as exc:
            print(f'>>> test_smtp_auth({user}): sending mail failed - {exc}')
            return False

    def test_imap_auth(self, user):
        try:
            imapcon = imaplib.IMAP4_SSL(host='localhost')
            print(imapcon.login(user, self.password))
            print(f'>>> test_imap_auth({user}): successful IMAP auth')
            return True
        except Exception as exc:
            print(f'>>> test_imap_auth({user}): IMAP auth failed - {exc}')
            return False

    def test_pop3_auth(self, user):
        try:
            pop3con = poplib.POP3_SSL(host='localhost')
            print(pop3con.user(user))
            print(pop3con.pass_(self.password))
            print(f'>>> test_pop3_auth({user}): successful POP3 auth')
            return True
        except Exception as exc:
            print(f'>>> test_pop3_auth({user}): POP3 auth failed - {exc}')
            return False

    def test_saslauthd(self, user):
        if not self.ucr.is_true('mail/cyrus'):
            return None
        exitcode = subprocess.call(['testsaslauthd', '-u', self.username, '-p', self.password])
        print('>>> test_saslauthd(%s): exitcode=%r' % (user, exitcode))
        return exitcode == 0

    def test_sieve(self, user):
        proc = subprocess.Popen([
            'sieve-connect', '--nosslverify', '--notlsverify',
            '--user', user,
            '--authzid', user,
            '--server', '{}.{}'.format(self.ucr.get('hostname'), self.ucr.get('domainname')),
            '--port', '4190', '-4',
            '--passwordfd', '0',
            '--list'], stdin=subprocess.PIPE)
        command = '%s\n' % (self.password,)
        proc.communicate(command.encode('UTF-8'))
        exitcode = proc.returncode
        print('>>> test_sieve(%s): exitcode=%r' % (user, exitcode))
        return exitcode == 0

    def restart_services(self):
        subprocess.call(['service', 'nscd', 'restart'])
        subprocess.call(['sss_cache', '-E'])
        subprocess.call(['service', 'saslauthd', 'restart'])
        subprocess.call(['service', 'postfix', 'restart'])
        if self.ucr.is_true('mail/cyrus'):
            subprocess.call(['service', 'cyrus-imapd', 'restart'])
        if self.ucr.is_true('mail/dovecot'):
            subprocess.call(['service', 'dovecot', 'restart'])
        utils.wait_for_replication()  # _and_postrun()
        time.sleep(8)   # postrun (15s) is too much

    def set_userPassword(self, value):
        lo = utils.get_ldap_connection()
        password = lo.get(self.userdn, ['userPassword'])['userPassword']
        print("password ", password)
        lo.modify(self.userdn, [('userPassword', password, [value.encode('UTF-8')])])

    def run_tests(self):
        result = {}
        checks = (
            ('smtp_mailPrimaryAddress', self.email, self.test_smtp_auth),
            ('smtp_uid', self.username, self.test_smtp_auth),
            ('imap_mailPrimaryAddress', self.email, self.test_imap_auth),
            ('imap_uid', self.username, self.test_imap_auth),
            ('pop3_mailPrimaryAddress', self.email, self.test_pop3_auth),
            ('pop3_uid', self.username, self.test_pop3_auth),
            ('testsaslauthd_mailPrimaryAddress', self.email, self.test_saslauthd),
            ('testsaslauthd_uid', self.username, self.test_saslauthd),
            ('sieve_mailPrimaryAddress', self.email, self.test_sieve),
            ('sieve_uid', self.username, self.test_sieve),
        )
        self.restart_services()

        for (key, user, func) in checks:
            result[f'pre_change_{key}'] = func(user)

        self.set_userPassword('{K5KEY}')
        self.restart_services()

        for (key, user, func) in checks:
            result[f'post_change_{key}'] = func(user)

        print('RESULT:')
        print('=' * 55)
        results = sorted(result.items(), key=lambda x: x[0], reverse=True)
        for key, val in results:
            print('{:<45}: {}'.format(key, {True: 'OK', False: 'FAILED', None: 'SKIPPED'}[val]))

        if any(x is False for x in result.values()):
            utils.fail('Not all authentication were okay!')


def main():
    with udm_test.UCSTestUDM() as udm, ucr_test.UCSTestConfigRegistry() as ucr:
        authtest = AuthTests(ucr, udm)
        authtest.run_tests()


if __name__ == '__main__':
    main()
