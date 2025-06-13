#!/usr/share/ucs-test/runner python3
## desc: Test ACL registration for different UCS versions
## tags:
##  - ldapextensions
##  - apptest
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
## exposure: dangerous

import sys
from time import sleep

import ldap
from ldap_extension_utils import (
    call_join_script, get_acl_name, get_container_name, get_package_name, set_container_description,
)

from univention.config_registry import ConfigRegistry
from univention.testing.debian_package import DebianPackage
from univention.testing.udm import UCSTestUDM
from univention.testing.utils import fail


ucr = ConfigRegistry()
ucr.load()

currentversion = '%s-%s' % (ucr.get('version/version'), ucr.get('version/patchlevel'))
nextversion = '%s-%s' % (ucr.get('version/version'), int(ucr.get('version/patchlevel')) + 1)
futureversion = '%s-%s' % (ucr.get('version/version'), int(ucr.get('version/patchlevel')) + 99)

with UCSTestUDM() as udm:
    package_name = get_package_name()
    acl_name_current = get_acl_name()
    acl_name_new = get_acl_name()
    container_name_current = get_container_name()
    container_name_new = get_container_name()
    join_script_name = '66%s.inst' % package_name

    user_dn, _username = udm.create_user(password='univention')
    container_current = udm.create_object('container/cn', name=container_name_current)
    container_new = udm.create_object('container/cn', name=container_name_new)
    try:
        set_container_description(user_dn, container_current)
    except ldap.INSUFFICIENT_ACCESS:
        pass
    else:
        fail('New user was able to modify %s' % container_current)

    try:
        set_container_description(user_dn, container_new)
    except ldap.INSUFFICIENT_ACCESS:
        pass
    else:
        fail('New user was able to modify %s' % container_new)

    joinscript_buffer = '''#!/bin/sh
VERSION=1
. /usr/share/univention-join/joinscripthelper.lib
joinscript_init
UNIVENTION_APP_IDENTIFIER="%(package_name)s-1.0"
. /usr/share/univention-lib/ldap.sh
ucs_registerLDAPExtension "$@" --ucsversionstart 1.0-0 --ucsversionend %(currentversion)s --acl /usr/share/%(package_name)s/%(acl_name_current)s || die
ucs_registerLDAPExtension "$@" --ucsversionstart %(nextversion)s --ucsversionend %(futureversion)s --acl /usr/share/%(package_name)s/%(acl_name_new)s || die
joinscript_save_current_version
exit 0
''' % {
        'package_name': package_name,
        'acl_name_current': acl_name_current,
        'acl_name_new': acl_name_new,
        'currentversion': currentversion,
        'nextversion': nextversion,
        'futureversion': futureversion,
    }

    acl_buffer_current = '''
access to dn.base="%(container)s" attrs="description"
    by dn.base="%(user_dn)s" write
    by * +0 break
''' % {'container': container_current, 'user_dn': user_dn}

    acl_buffer_new = '''
access to dn.base="%(container)s" attrs="description"
    by dn.base="%(user_dn)s" write
    by * +0 break
''' % {'container': container_new, 'user_dn': user_dn}

    package = DebianPackage(name=package_name)
    package.create_join_script_from_buffer(join_script_name, joinscript_buffer)
    package.create_usr_share_file_from_buffer(acl_name_current, acl_buffer_current)
    package.create_usr_share_file_from_buffer(acl_name_new, acl_buffer_new)
    package.build()
    package.install()

    call_join_script(join_script_name)

    # The ldap server needs a few seconds
    sleep(5)

    set_container_description(user_dn, container_current)

    try:
        set_container_description(user_dn, container_new)
    except ldap.INSUFFICIENT_ACCESS:
        pass
    else:
        fail('User was able to modify %s which should not be possible.' % container_new)
        sys.exit(100)

    package.uninstall()
    package.remove()

# vim: set ft=python :
