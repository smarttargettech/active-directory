#!/usr/share/ucs-test/runner python3
## desc: Create a valid appcenter/app object
## tags: [udm-ldapextensions,apptest]
## roles: [domaincontroller_master]
## exposure: dangerous
## packages:
##   - univention-management-console-module-appcenter

import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.testing import utils


if __name__ == '__main__':
    with udm_test.UCSTestUDM() as udm:
        id = uts.random_name()
        name = uts.random_name()
        version = uts.random_name()
        app = udm.create_object('appcenter/app', position=udm.UNIVENTION_CONTAINER, id=id, name=name, version=version)
        utils.verify_ldap_object(app, {
            'univentionAppName': [name],
            'univentionAppID': [id],
            'univentionAppVersion': [version],
        })

        udm.remove_object('appcenter/app', dn=app)
        utils.verify_ldap_object(app, {
            'univentionAppName': [name],
        }, should_exist=False)
