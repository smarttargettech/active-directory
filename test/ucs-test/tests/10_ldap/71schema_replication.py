#!/usr/share/ucs-test/runner python3
## desc: Test schema replication
## tags:
##  - ldapextensions
##  - apptest
##  - replication
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
##  - domaincontroller_slave
## packages:
##  - python3-univention-lib
## exposure: dangerous

from time import sleep

from ldap_extension_utils import (
    call_join_script, call_unjoin_script, get_package_name, get_schema_attribute_id, get_schema_name,
)

import univention.testing.udm as udm_test
import univention.uldap
from univention.config_registry import ConfigRegistry
from univention.testing.debian_package import DebianPackage
from univention.testing.strings import random_name, random_string
from univention.testing.utils import fail, wait_for_replication


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
attributetype ( 1.3.6.1.4.1.10176.200.10999.1.%(attribute_id)s NAME 'univentionTestAttribute%(attribute_id)s'
    DESC ' unused custom attribute %(attribute_id)s '
    EQUALITY caseExactMatch
    SUBSTR caseIgnoreSubstringsMatch
    SYNTAX 1.3.6.1.4.1.1466.115.121.1.15 )

objectclass ( 1.3.6.1.4.1.10176.200.10999.1.%(attribute_id)s
    NAME 'univentionTestAttributes%(attribute_id)s'
        DESC ' Test Attribute objectclass '
        SUP top AUXILIARY
        MAY ( univentionTestAttribute%(attribute_id)s
            )
    )

''' % {'attribute_id': attribute_id}

udm = udm_test.UCSTestUDM()
properties = {
    'name': random_name(),
    'shortDescription': random_string(),
    'CLIName': random_name(),
    'module': 'container/cn',
    'objectClass': 'univentionTestAttributes%(attribute_id)s' % {'attribute_id': attribute_id},
    'ldapMapping': 'univentionTestAttribute%(attribute_id)s' % {
        'attribute_id': attribute_id,
    },
}
extended_attribute = udm.create_object('settings/extended_attribute', **properties)

wait_for_replication()

package = DebianPackage(name=package_name)
package.create_join_script_from_buffer(join_script_name, joinscript_buffer)
package.create_unjoin_script_from_buffer(unjoin_script_name, unjoinscript_buffer)
package.create_usr_share_file_from_buffer(schema_name, schema_buffer)
package.build()

package.install()
try:
    call_join_script(join_script_name)

    # The ldap server needs a few seconds
    sleep(5)

    properties = {
        'name': random_name(),
        'univentionTestAttribute%(attribute_id)s' % {'attribute_id': attribute_id}: random_name(),
        'position': 'cn=custom attributes,cn=univention,%s' % ucr.get('ldap/base'),
    }
    container = udm.create_object('container/cn', **properties)

    wait_for_replication()

    lo = univention.uldap.getMachineConnection()
    try:
        lo.search(base=container)
    except Exception:
        fail()
finally:
    call_unjoin_script(unjoin_script_name)
    package.remove()
    package.uninstall()

    udm.cleanup()
    wait_for_replication()

# vim: set ft=python :
