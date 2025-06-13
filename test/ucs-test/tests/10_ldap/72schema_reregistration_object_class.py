#!/usr/share/ucs-test/runner python3
## desc: Test the schema reregistration of a known objectClass
## tags:
##  - ldapextensions
##  - apptest
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
## exposure: dangerous

from time import sleep

from ldap_extension_utils import call_join_script, call_unjoin_script, get_package_name, get_schema_name

from univention.config_registry import ConfigRegistry
from univention.testing.debian_package import DebianPackage
from univention.testing.utils import verify_ldap_object


ucr = ConfigRegistry()
ucr.load()

package_name = get_package_name()
schema_name = get_schema_name()
join_script_name = '66%s.inst' % package_name
unjoin_script_name = '66%s.uinst' % package_name

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
objectclass ( 1.3.6.1.4.1.7165.2.2.11 NAME 'sambaShare' SUP top STRUCTURAL
    DESC 'Samba Share Section'
    MUST ( sambaShareName )
    MAY ( description ) )

objectclass ( 1.3.6.1.4.1.7165.2.2.12 NAME 'sambaConfigOption' SUP top STRUCTURAL
    DESC 'Samba Configuration Option'
    MUST ( sambaOptionName )
    MAY ( sambaBoolOption $ sambaIntegerOption $ sambaStringOption $
          sambaStringListoption $ description ) )
'''

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

    expected_dn = 'cn=%s,cn=ldapschema,cn=univention,%s' % (schema_name, ucr.get('ldap/base'))
    verify_ldap_object(expected_dn, {'univentionLDAPSchemaActive': ['FALSE']})
finally:
    call_unjoin_script(unjoin_script_name)
    package.remove()
    package.uninstall()

# vim: set ft=python :
