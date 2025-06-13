#!/usr/share/ucs-test/runner python3
## desc: Test basic ACL unregistration
## tags: [ldapextensions, apptest]
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
## exposure: dangerous

import time

import ldap
from ldap_extension_utils import (
    call_join_script, call_unjoin_script, get_acl_name, get_container_name, get_package_name, set_container_description,
    wait_for_ldap,
)

from univention.testing.debian_package import DebianPackage
from univention.testing.udm import UCSTestUDM
from univention.testing.utils import fail, wait_for_replication_and_postrun


def main():
    with UCSTestUDM() as udm:
        package_name = get_package_name()
        acl_name = get_acl_name()
        container_name = get_container_name()
        join_script_name = '66%s.inst' % package_name
        unjoin_script_name = '66%s.uinst' % package_name

        user_dn, _username = udm.create_user(password='univention')
        container = udm.create_object('container/cn', name=container_name)
        try:
            set_container_description(user_dn, container)
        except ldap.INSUFFICIENT_ACCESS:
            pass
        else:
            fail('New user was able to modify %s' % container)

        joinscript_buffer = '''#!/bin/sh
VERSION=1
. /usr/share/univention-join/joinscripthelper.lib
joinscript_init
UNIVENTION_APP_IDENTIFIER="%(package_name)s-1.0"
. /usr/share/univention-lib/ldap.sh
ucs_registerLDAPExtension "$@" --acl /usr/share/%(package_name)s/%(acl_name)s || die
joinscript_save_current_version
exit 0
''' % {'package_name': package_name, 'acl_name': acl_name}

        unjoinscript_buffer = '''#!/bin/sh
VERSION=1
. /usr/share/univention-join/joinscripthelper.lib
. /usr/share/univention-lib/ldap.sh
ucs_unregisterLDAPExtension "$@" --acl %(acl_name)s || die
exit 0
''' % {'acl_name': acl_name}

        acl_buffer = '''
access to dn.base="%(container)s" attrs="description"
    by dn.base="%(user_dn)s" write
    by * +0 break
''' % {'container': container, 'user_dn': user_dn}

        package = DebianPackage(name=package_name)
        package.create_join_script_from_buffer(join_script_name, joinscript_buffer)
        package.create_unjoin_script_from_buffer(unjoin_script_name, unjoinscript_buffer)
        package.create_usr_share_file_from_buffer(acl_name, acl_buffer)
        package.build()
        package.install()

        call_join_script(join_script_name)

        # Waiting for the ldap server
        wait_for_ldap()

        set_container_description(user_dn, container)

        call_unjoin_script(unjoin_script_name)

        # Waiting for the postrun
        wait_for_replication_and_postrun()

        # TODO: remove when bug #37516 is fixed
        time.sleep(60)

        try:
            set_container_description(user_dn, container)
        except ldap.INSUFFICIENT_ACCESS:
            pass
        else:
            fail('New user was able to modify %s' % container)

        package.uninstall()
        package.remove()


if __name__ == '__main__':
    main()
