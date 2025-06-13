#!/usr/share/ucs-test/runner python3
## desc: check mail related modifications of user objects
## exposure: dangerous
## packages: [univention-mail-server]

import subprocess

import univention.config_registry
import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils

from essential.mailclient import MailClient_SSL


def check_login_lookup(host, mail, password, expected_result):
    """
    This function checks if it is possible to login via a mail address
    and a given password, also checks if it is possible to lookup
    the standard set of mailboxes: INBOX, Ham, Spam.
    An exception is thrown if the result of either the login or the lookup
    was not expected.
    """
    print(f'check_login_lookup() host={host!r} mail={mail!r} password={password!r} expected_result={expected_result!r}')
    imap = MailClient_SSL(host)
    if not mail:
        mail = '""'  # no IMAP quoting since Python 3: https://github.com/python/cpython/issues/98241
    try:
        imap.log_in(mail, password)
        for mailbox in ['INBOX', 'Ham', 'Spam']:
            imap.check_lookup(mail, {mailbox: expected_result})
        imap.logout()
        if not expected_result:
            utils.fail('Authentication passed, expected to fail.')
    except Exception as ex:
        auth_errors = ['AUTHENTICATIONFAILED', 'LOGIN => socket error', '[UNAVAILABLE] Internal error']
        error = ''.join(s.decode('UTF-8', 'replace') if isinstance(s, bytes) else s for s in ex.args)
        if any(msg in error for msg in auth_errors):
            if expected_result:
                utils.fail('Authentication failed, expected to pass.')
        elif 'Login failed' in error:
            if expected_result:
                utils.fail('Login failed, expected to pass.')
        else:
            raise


def main():
    with udm_test.UCSTestUDM() as udm:
        ucr_tmp = univention.config_registry.ConfigRegistry()
        ucr_tmp.load()
        cmd = ['/etc/init.d/dovecot', 'restart']
        with utils.AutoCallCommand(exit_cmd=cmd, stderr=open('/dev/null', 'w')):
            with ucr_test.UCSTestConfigRegistry() as ucr:
                domain = ucr.get('domainname')
                basedn = ucr.get('ldap/base')
                univention.config_registry.handler_set([
                    'mail/dovecot/mailbox/rename=yes',
                    'mail/dovecot/mailbox/delete=no',
                    'mail/dovecot/auth/cache_size=0',
                ])
                subprocess.call(['service', 'dovecot', 'restart'], stderr=open('/dev/null', 'w'))
                host = '{}.{}'.format(ucr.get('hostname'), domain)
                password = 'univention'
                account = utils.UCSTestDomainAdminCredentials()
                admin = account.binddn
                passwd = account.bindpw

                # Case 1
                # Create a user with mailHomeServer and mailPrimaryAddress
                # → mailbox should have been created and is accessible
                # Change mailPrimaryAddress
                # → mailbox with NEW name should have been created and is accessible
                # → mailbox with OLD name should NOT be accessible
                print("== case 1 ==")
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailHomeServer': host,
                        'mailPrimaryAddress': usermail,
                    },
                )
                check_login_lookup(host, usermail, password, True)
                new_usermail = f'{uts.random_name()}@{domain}'
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailPrimaryAddress': new_usermail},
                    check_for_drs_replication=True)
                check_login_lookup(host, new_usermail, password, True)
                check_login_lookup(host, usermail, password, False)

                # Case 2
                # Create a user with mailPrimaryAddress and without mailHomeServer
                # → mailbox should NOT have been created
                # Add local FQDN as mailHomeServer
                # → mailbox should have been created and is accessible
                print("== case 2 ==")
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailPrimaryAddress': usermail,
                    },
                )
                check_login_lookup(host, usermail, password, True)
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailHomeServer': host},
                    check_for_drs_replication=True)
                check_login_lookup(host, usermail, password, True)

                # Case 3
                # Create a user with mailPrimaryAddress and without mailHomeServer
                # → mailbox should NOT have been created
                # Add "foreign" FQDN as mailHomeServer
                # → mailbox should NOT have been created
                print("== case 3 ==")
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailPrimaryAddress': usermail,
                    },
                )
                check_login_lookup(host, usermail, password, True)
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailHomeServer': 'mail.example.com'},
                    check_for_drs_replication=True)
                check_login_lookup(host, usermail, password, False)

                # Case 4
                # Create a user without mailPrimaryAddress and mailHomeServer==$LOCALFQDN
                # → mailbox should NOT have been created
                # Add mailPrimaryAddress
                # → mailbox should have been created and is accessible
                print("== case 4 ==")
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailHomeServer': host,
                    },
                )
                check_login_lookup(host, '', password, False)
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailPrimaryAddress': usermail},
                    check_for_drs_replication=True)
                check_login_lookup(host, usermail, password, True)

                # Case 5
                # Create a user with mailHomeServer and mailPrimaryAddress
                # → mailbox should have been created and is accessible
                # Change mailHomeServer
                # → mailbox should NOT be accessible
                print("== case 5 ==")
                ip = uts.random_ip()
                new_host = uts.random_name()
                udm.create_object(
                    'computers/domaincontroller_slave',
                    set={
                        'ip': ip,
                        'name': new_host,
                        'dnsEntryZoneForward': f'zoneName={domain},cn=dns,{basedn} {ip}',
                    },
                    position='cn=computers,%s' % basedn,
                )
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailHomeServer': host,
                        'mailPrimaryAddress': usermail,
                    },
                )
                check_login_lookup(host, usermail, password, True)
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailHomeServer': f'{new_host}.{domain}'},
                    check_for_drs_replication=True)
                check_login_lookup(host, usermail, password, False)

                # Case 6
                # Create a user with mailHomeServer and mailPrimaryAddress
                # → mailbox should have been created and is accessible
                # Remove mailHomeServer
                # → mailbox should still be accessible
                print("== case 6 ==")
                ip = uts.random_ip()
                new_host = uts.random_name()
                udm.create_object(
                    'computers/domaincontroller_slave',
                    set={
                        'ip': ip,
                        'name': new_host,
                        'dnsEntryZoneForward': f'zoneName={domain},cn=dns,{basedn} {ip}',
                    },
                    position='cn=computers,%s' % basedn,
                )
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailHomeServer': host,
                        'mailPrimaryAddress': usermail,
                    },
                )
                check_login_lookup(host, usermail, password, True)
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailHomeServer': ''},
                    check_for_drs_replication=True)
                check_login_lookup(host, usermail, password, True)

                # Case 7
                # Create a user with mailHomeServer and mailPrimaryAddress
                # → mailbox should have been created and is accessible
                # Remove mailPrimaryAddress
                # → mailbox should NOT be accessible
                print("== case 7 ==")
                ip = uts.random_ip()
                new_host = uts.random_name()
                udm.create_object(
                    'computers/domaincontroller_slave',
                    set={
                        'ip': ip,
                        'name': new_host,
                        'dnsEntryZoneForward': f'zoneName={domain},cn=dns,{basedn} {ip}',
                    },
                    position='cn=computers,%s' % basedn,
                )
                usermail = f'{uts.random_name()}@{domain}'
                userdn, _username = udm.create_user(
                    set={
                        'password': password,
                        'mailHomeServer': host,
                        'mailPrimaryAddress': usermail,
                    },
                )
                check_login_lookup(host, usermail, password, True)
                udm.modify_object(
                    'users/user',
                    dn=userdn,
                    binddn=admin,
                    bindpwd=passwd,
                    set={'mailPrimaryAddress': ''},
                    check_for_drs_replication=True)
                check_login_lookup(host, usermail, password, False)


if __name__ == '__main__':
    main()
