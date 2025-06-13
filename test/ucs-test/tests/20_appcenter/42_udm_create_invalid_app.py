#!/usr/share/ucs-test/runner python3
## desc: Try to create invalid appcenter/app objects
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
        serverRole = ['invalid_role']
        try:
            app = udm.create_object('appcenter/app', id=id, name=name, version=version, serverRole=serverRole)
        except udm_test.UCSTestUDM_CreateUDMObjectFailed:
            pass
        else:
            utils.fail('appcenter/app object with an invalid serverRole could be created')

        try:
            app = udm.create_object('appcenter/app', id=id, name=name)
        except udm_test.UCSTestUDM_CreateUDMObjectFailed:
            pass
        else:
            utils.fail('appcenter/app object without version could be created')

        try:
            app = udm.create_object('appcenter/app', id=id, version=version)
        except udm_test.UCSTestUDM_CreateUDMObjectFailed:
            pass
        else:
            utils.fail('appcenter/app object without name could be created')

        try:
            app = udm.create_object('appcenter/app', name=name, version=version)
        except udm_test.UCSTestUDM_CreateUDMObjectFailed:
            pass
        else:
            utils.fail('appcenter/app object without name could be created')
