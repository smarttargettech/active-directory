#!/usr/share/ucs-test/runner python3
## desc: check if RADIUS authenticator shared secret is only readable by domain admins and machine accounts
## tags: [apptest, radius]
## packages:
##   - univention-radius
## join: true
## exposure: dangerous

#
# This test expects, that univention-radius has been successfully installed on the local system.
#

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
import univention.uldap
from univention.testing import utils


class Bunch:
    """
    >>> y = Bunch(foo=42, bar='TEST')
    >>> print repr(y.foo), repr(y.bar)
    42 'TEST'

    >>> x = Bunch()
    >>> x.a = 4
    >>> print x.a
    4
    """

    def __init__(self, **kwds):
        self.__dict__.update(kwds)

    def __str__(self):
        result = []
        for key, value in self.__dict__.items():
            result.append('%s=%r' % (key, value))
        return 'Bunch(' + ', '.join(result) + ')'

    def __repr__(self):
        return str(self)


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            print('*** create computer objects')
            computer = Bunch(
                name=uts.random_string(),
                password=uts.random_string(),
                addr=uts.random_ip())
            computer.dn = udm.create_object(
                'computers/memberserver',
                position='cn=computers,{}'.format(ucr.get('ldap/base')),
                name=computer.name,
                password=computer.password,
                ip=[computer.addr],
                options=['kerberos', 'samba', 'posix', 'radiusAuthenticator'],
                univentionRadiusClientSharedSecret=uts.random_string(),
                univentionRadiusClientType='other',
                univentionRadiusClientVirtualServer=computer.name,
                wait_for_replication=False)

            dn, username = udm.create_user()
            user = Bunch(dn=dn, name=username)

            def check_virtual_server(userdn, use_master, attrs):
                assert attrs.get('univentionRadiusClientVirtualServer', [b''])[0].decode('UTF-8') == computer.name, '{} is unable to read univentionRadiusClientVirtualServer of {} from {}'.format(
                    userdn,
                    computer.dn,
                    'domaincontroller_master' if use_master else 'localhost')

            def check_secret_is_readable(userdn, use_master, attrs):
                assert 'univentionRadiusClientSharedSecret' in attrs, '{} is unable to read univentionRadiusClientSharedSecret of {} from {}'.format(
                    userdn,
                    computer.dn,
                    'domaincontroller_master' if use_master else 'localhost')

            def check_secret_is_unreadable(userdn, use_master, attrs):
                assert 'univentionRadiusClientSharedSecret' not in attrs, '{} is unexpectedly able to read univentionRadiusClientSharedSecret of {} from {}'.format(
                    userdn,
                    computer.dn,
                    'domaincontroller_master' if use_master else 'localhost')

            targets = [(True, ucr.get('ldap/master'))]
            if ucr.get('server/role') != 'memberserver':
                targets.append((False, ucr.get('hostname')))

            for use_master, target_server in targets:
                print('*** testing {} account against {}'.format(ucr.get('ldap/hostdn'), target_server))
                lo = univention.uldap.getMachineConnection(ldap_master=use_master)
                attrs = lo.get(computer.dn)
                check_secret_is_readable(ucr.get('ldap/hostdn'), use_master, attrs)
                check_virtual_server(ucr.get('ldap/hostdn'), use_master, attrs)

                account = utils.UCSTestDomainAdminCredentials()
                print(f'*** testing {account.binddn} account against {target_server}')
                lo = univention.admin.uldap.access(
                    host=target_server,
                    port=int(ucr.get('ldap/master/port', '7389')),
                    base=ucr.get('ldap/base'),
                    binddn=account.binddn,
                    bindpw=account.bindpw)
                attrs = lo.get(computer.dn)
                check_secret_is_readable(account.binddn, use_master, attrs)
                check_virtual_server(account.binddn, use_master, attrs)

                print(f'*** testing {computer.dn} account against {target_server}')
                lo = univention.admin.uldap.access(
                    host=target_server,
                    port=int(ucr.get('ldap/master/port', '7389')),
                    base=ucr.get('ldap/base'),
                    binddn=computer.dn,
                    bindpw=computer.password)
                attrs = lo.get(computer.dn)
                check_secret_is_unreadable(account.binddn, use_master, attrs)
                check_virtual_server(account.binddn, use_master, attrs)

                print(f'*** testing {user.dn} account against {target_server}')
                lo = univention.admin.uldap.access(
                    host=target_server,
                    port=int(ucr.get('ldap/master/port', '7389')),
                    base=ucr.get('ldap/base'),
                    binddn=user.dn,
                    bindpw='univention')
                attrs = lo.get(computer.dn)
                check_secret_is_unreadable(user.dn, use_master, attrs)
                check_virtual_server(user.dn, use_master, attrs)


if __name__ == '__main__':
    main()
