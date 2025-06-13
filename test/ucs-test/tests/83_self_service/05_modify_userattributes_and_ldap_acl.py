#!/usr/share/ucs-test/runner python3
## desc: Self service user attributes ACL generation and enforcement
## tags: [apptest]
## roles:
##  - domaincontroller_master
## exposure: dangerous
## packages:
##  - univention-self-service-master

import pytest

import univention.admin.uexceptions
import univention.admin.uldap
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.config_registry import handler_set
from univention.testing import utils


if __name__ == '__main__':
    with udm_test.UCSTestUDM() as udm, ucr_test.UCSTestConfigRegistry() as ucr:

        handler_set(['umc/self-service/profiledata/enabled=true'])

        if 'l' not in ucr.get('self-service/ldap_attributes', '').split(','):
            handler_set(["self-service/ldap_attributes=%s,l" % ucr.get('self-service/ldap_attributes', '')])
        user = udm.create_user(password='univention')[0]
        utils.verify_ldap_object(user)

        lo = univention.admin.uldap.access(binddn=user, bindpw='univention')
        lo.modify(user, [('l', '', [b'Bremen'])])
        utils.verify_ldap_object(user, {'l': ['Bremen']})

        with pytest.raises(univention.admin.uexceptions.permissionDenied):
            lo.modify(user, [('sn', '', [b'mustfail'])])
