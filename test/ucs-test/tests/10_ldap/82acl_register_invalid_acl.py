#!/usr/share/ucs-test/runner python3
## desc: Test registration of invalid ACL
## tags:
##  - ldapextensions
##  - apptest
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
## exposure: dangerous

from time import sleep

import ldap
from ldap_extension_utils import (
    call_join_script, call_unjoin_script, get_acl_name, get_container_name, get_ldap_master_connection,
    get_package_name, set_container_description,
)

from univention.config_registry import ConfigRegistry
from univention.testing.debian_package import DebianPackage
from univention.testing.udm import UCSTestUDM
from univention.testing.utils import fail


ucr = ConfigRegistry()
ucr.load()

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
access to ="%(container)s" attrs="description"
    by * +0 break
''' % {'container': container}

    package = DebianPackage(name=package_name)
    package.create_join_script_from_buffer(join_script_name, joinscript_buffer)
    package.create_unjoin_script_from_buffer(unjoin_script_name, unjoinscript_buffer)
    package.create_usr_share_file_from_buffer(acl_name, acl_buffer)
    package.build()
    package.install()

    call_join_script(join_script_name)

    # The ldap server needs a few seconds
    print('sleep 5')
    sleep(5)

    lo = get_ldap_master_connection(user_dn)
    lo.search(filter='uid=%s' % _username)

    call_unjoin_script(unjoin_script_name)
    package.uninstall()
    package.remove()

# vim: set ft=python :
