#!/usr/share/ucs-test/runner python3
## desc: univention-admingrp-user-passwordreset-ldapdiff
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## packages:
##  - univention-admingrp-user-passwordreset
## exposure: dangerous

import re
import time

import univention.config_registry
import univention.testing.udm as udm_test
from univention import uldap
from univention.testing import utils
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.utils import fail


ucstest_errorcode = 140
default_password = 'univention'


class Account:
    def __init__(self, description, dn, name, password=default_password):
        self.description = description
        self.dn = dn
        self.name = name
        self.password = password

    def __str__(self):
        return f'{self.description} "{self.name}"'


try:
    with udm_test.UCSTestUDM() as udm, UCSTestConfigRegistry() as ucr:

        # create helpdesk group
        try:
            what = 'Helpdesk group'
            hdgroup_dn, hdgroup_name = udm.create_group()
            helpdesk_group = Account(what, hdgroup_dn, hdgroup_name)
        except Exception as exc:
            fail(f'Creating {what} failed: {exc}', ucstest_errorcode)

        # create new user
        try:
            what = 'Helpdesk user'
            hduser_dn, hduser_name = udm.create_user()
            helpdesk_user = Account(what, hduser_dn, hduser_name)
        except Exception as exc:
            fail(f'Creating {what} failed: {exc}', ucstest_errorcode)

        # add user to corresponding group
        udm.modify_object(
            'groups/group',
            dn=helpdesk_group.dn,
            append={
                'users': [helpdesk_user.dn],
            },
        )

        # create new protected test user
        try:
            what = 'Protected user'
            prot_user_dn, prot_user_name = udm.create_user()
            prot_user = Account(what, prot_user_dn, prot_user_name)
        except Exception as exc:
            fail(f'Creating {what} failed: {exc}', ucstest_errorcode)

        # Deactivate LDAP ACL
        pattern = re.compile(r'^ldap\/acl\/user\/passwordreset\/accesslist\/groups.[^:]+')
        aclkey = ''
        aclvalue = ''
        for item in ucr.items():
            key, value = item
            match = re.search(pattern, key)
            if match:
                aclkey, aclvalue = key, value
                break
        univention.config_registry.handler_unset([key])
        utils.restart_slapd()

        lo_machine = uldap.getMachineConnection()
        lo_admin = uldap.getAdminConnection()
        print('==> Dumping LDAP without active ACL')
        ldif_anon_a = lo_machine.search()
        ldif_admin_a = lo_admin.search()

        # Activate passwordreset ACLs:
        univention.config_registry.handler_set([
            f'ldap/acl/user/passwordreset/accesslist/groups/dn={helpdesk_group.dn}',
            f'ldap/acl/user/passwordreset/protected/uid="Administrator,{prot_user.name}"',
        ])
        utils.restart_slapd()
        time.sleep(5)

        print('==> Dumping LDAP with active ACL')
        ldif_anon_b = lo_machine.search()
        ldif_admin_b = lo_admin.search()

        print('==> Comparing output')
        if ldif_anon_a != ldif_anon_b:
            fail('anonymous LDAP dump differs')
        if ldif_admin_a != ldif_admin_b:
            fail('admin LDAP dump differs')
finally:
    # Important: deactivate LDAP ACLs again
    utils.restart_slapd()
