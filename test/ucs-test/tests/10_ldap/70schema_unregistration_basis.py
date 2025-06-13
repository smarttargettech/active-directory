#!/usr/share/ucs-test/runner python3
## desc: Test schema unregistration
## tags:
##  - SKIP-UCSSCHOOL
##  - ldapextensions
##  - apptest
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
## exposure: dangerous

from time import sleep

from ldap_extension_utils import (
    call_join_script, call_unjoin_script, fetch_schema_from_ldap_master, get_package_name, get_schema_attribute_id,
    get_schema_name,
)

from univention.config_registry import ConfigRegistry
from univention.testing.debian_package import DebianPackage
from univention.testing.utils import fail, wait_for_replication_and_postrun


ucr = ConfigRegistry()
ucr.load()

package_name = get_package_name()
schema_name = get_schema_name()
join_script_name = '66%s.inst' % package_name
unjoin_script_name = '66%s.uinst' % package_name
attribute_id = get_schema_attribute_id()

joinscript_buffer = '''#!/bin/sh
VERSION=1
. /usr/share/univention-join/joinscripthelper.lib
joinscript_init
UNIVENTION_APP_IDENTIFIER="%(package_name)s-1.0"
. /usr/share/univention-lib/ldap.sh
ucs_registerLDAPExtension "$@" --schema /usr/share/%(package_name)s/%(schema_name)s || die
joinscript_save_current_version
exit 0
''' % {'package_name': package_name, 'schema_name': schema_name}

unjoinscript_buffer = '''#!/bin/sh
VERSION=1
. /usr/share/univention-join/joinscripthelper.lib
. /usr/share/univention-lib/ldap.sh
ucs_unregisterLDAPExtension "$@" --schema %(schema_name)s || die
exit 0
''' % {'schema_name': schema_name}

schema_buffer = '''
attributetype ( 1.3.6.1.4.1.10176.200.10999.%(attribute_id)s NAME 'univentionFreeAttribute%(attribute_id)s'
    DESC ' unused custom attribute %(attribute_id)s '
    EQUALITY caseExactMatch
    SUBSTR caseIgnoreSubstringsMatch
    SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )
''' % {'attribute_id': attribute_id}

package = DebianPackage(name=package_name)
package.create_join_script_from_buffer(join_script_name, joinscript_buffer)
package.create_unjoin_script_from_buffer(unjoin_script_name, unjoinscript_buffer)
package.create_usr_share_file_from_buffer(schema_name, schema_buffer)
package.build()

package.install()
try:
    call_join_script(join_script_name)
    try:
        # The ldap server needs a few seconds
        sleep(5)

        schema = fetch_schema_from_ldap_master()
        attribute_identifier = "( 1.3.6.1.4.1.10176.200.10999.%(attribute_id)s NAME 'univentionFreeAttribute%(attribute_id)s" % {'attribute_id': attribute_id}

        for attribute_entry in schema[1].ldap_entry().get('attributeTypes'):
            if attribute_entry.startswith(attribute_identifier):
                print('The schema entry was found: %s' % attribute_entry)
                break
        else:
            fail('The attribute was not found: univentionFreeAttribute%(attribute_id)s' % {'attribute_id': attribute_id})
    finally:
        call_unjoin_script(unjoin_script_name)
        wait_for_replication_and_postrun()

    for _i in range(20):
        schema = fetch_schema_from_ldap_master()
        attribute_identifier = "( 1.3.6.1.4.1.10176.200.10999.%(attribute_id)s NAME 'univentionFreeAttribute%(attribute_id)s" % {'attribute_id': attribute_id}

        for attribute_entry in schema[1].ldap_entry().get('attributeTypes'):
            if attribute_entry.startswith(attribute_identifier):
                print('The schema entry was found: %s' % attribute_entry)
                sleep(2)
                break
        else:
            break
    else:
        fail('The attribute was found: univentionFreeAttribute%(attribute_id)s' % {'attribute_id': attribute_id})
finally:
    package.remove()
    package.uninstall()

# vim: set ft=python :
