#!/usr/share/ucs-test/runner python3
## desc: check if RADIUS authenticator settings are written to clients.univention.conf
## tags: [radius]
## packages:
##   - univention-radius
## join: true
## exposure: dangerous

import random
import re

import univention.testing.strings as uts
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
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


nas_types = [
    'other',
    'cisco',
    'computone',
    'livingston',
    'juniper',
    'max40xx',
    'multitech',
    'netserver',
    'pathras',
    'patton',
    'portslave',
    'tc',
    'usrhiper',
]


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr:
        with udm_test.UCSTestUDM() as udm:
            print('*** create computer objects')
            computers = []
            for i, role in enumerate(udm_test.UCSTestUDM.COMPUTER_MODULES):
                if role == 'computers/domaincontroller_master':
                    #  Adding a new computers/domaincontroller_master breaks stuffs (e.g. ldap master connections)
                    continue
                name = uts.random_string()
                addr = uts.random_ip()
                secret = uts.random_string()
                virtual_server = uts.random_string() if random.randint(0, 1) else ''
                nas_type = nas_types[i]
                dn = udm.create_object(role, position='cn=computers,{}'.format(ucr.get('ldap/base')), name=name, ip=[addr], wait_for_replication=False)
                computers.append(Bunch(role=role, dn=dn, name=name, addr=addr, secret=secret, nas_type=nas_type, virtual_server=virtual_server, removed=False))
            utils.wait_for_replication()

            print('*** add RADIUS options')
            for computer in computers:
                udm.modify_object(
                    computer.role,
                    dn=computer.dn,
                    options=['kerberos', 'samba', 'posix', 'radiusAuthenticator'],
                    univentionRadiusClientSharedSecret=computer.secret,
                    univentionRadiusClientType=computer.nas_type,
                    univentionRadiusClientVirtualServer=computer.virtual_server,
                )
                utils.verify_ldap_object(
                    computer.dn,
                    expected_attr={
                        'univentionRadiusClientSharedSecret': [computer.secret],
                        'univentionRadiusClientType': [computer.nas_type],
                        'univentionRadiusClientVirtualServer': [computer.virtual_server] if computer.virtual_server else [],
                    })
            utils.wait_for_replication_and_postrun()

            def check_file_content(computers):
                print('*** checking /etc/freeradius/3.0/clients.univention.conf')
                with open('/etc/freeradius/3.0/clients.univention.conf') as fd:
                    content = fd.read()
                    print(
                        'Content of /etc/freeradius/3.0/clients.univention.conf\n'
                        '##############################\n'
                        f'{content}\n'
                        '##############################',
                    )
                    content = re.sub(r'\s+', ' ', content)

                def in_content(content, name, txt):
                    assert txt in content, f'cannot find "{txt}" for computer {name}'

                def not_in_content(content, name, txt):
                    assert txt not in content, f'unexpectedly found "{txt}" for computer {name}'

                for computer in computers:
                    func = not_in_content if computer.removed else in_content
                    func(content, computer.name, f'client {computer.name} {{')
                    func(content, computer.name, f'ipaddr = {computer.addr}')
                    func(content, computer.name, f'secret = {computer.secret}')
                    func(content, computer.name, f'nas_type = {computer.nas_type}')
                    if not computer.removed:
                        if computer.virtual_server:
                            func(content, computer.name, f'virtual_server = {computer.virtual_server}')
                        else:
                            func(content, computer.name, '# virtual_server = ...not specified...')

            utils.retry_on_error(
                lambda: check_file_content(computers),
                exceptions=AssertionError,
                retry_count=5,
                delay=2,
            )

            print('*** change RADIUS values')
            for computer in computers:
                computer.secret = uts.random_string()
                # nas_type is not changed on purpose (too less possible values available for current test mechanism)
                computer.virtual_server = uts.random_string()
                udm.modify_object(
                    computer.role,
                    dn=computer.dn,
                    options=['kerberos', 'samba', 'posix', 'radiusAuthenticator'],
                    univentionRadiusClientSharedSecret=computer.secret,
                    univentionRadiusClientType=computer.nas_type,
                    univentionRadiusClientVirtualServer=computer.virtual_server,
                )
            utils.wait_for_replication_and_postrun()
            utils.retry_on_error(
                lambda: check_file_content(computers),
                exceptions=AssertionError,
                retry_count=5,
                delay=2,
            )

            print('*** remove a computer')
            computer = computers[-1]
            udm.remove_object(computer.role, dn=computer.dn)
            computer.removed = True
            utils.wait_for_replication_and_postrun()
            utils.retry_on_error(
                lambda: check_file_content(computers),
                exceptions=AssertionError,
                retry_count=5,
                delay=2,
            )

            print('*** remove RADIUS settings')
            computer = computers[-2]
            udm.modify_object(
                computer.role,
                dn=computer.dn,
                options=['kerberos', 'samba', 'posix'],
                univentionRadiusClientSharedSecret='',
                univentionRadiusClientType='',
                univentionRadiusClientVirtualServer='',
            )
            computer.removed = True
            utils.wait_for_replication_and_postrun()
            utils.retry_on_error(
                lambda: check_file_content(computers),
                exceptions=AssertionError,
                retry_count=5,
                delay=2,
            )


if __name__ == '__main__':
    main()
