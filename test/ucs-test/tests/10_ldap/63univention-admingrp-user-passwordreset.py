#!/usr/share/ucs-test/runner python3
## desc: univention-admingrp-user-passwordreset
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## packages:
##  - univention-admingrp-user-passwordreset
## exposure: dangerous

import random
import string

import ldap

import univention.config_registry
import univention.testing.udm as udm_test
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
        return '%s "%s"' % (self.description, self.name)


try:
    with udm_test.UCSTestUDM() as udm, UCSTestConfigRegistry() as ucr:

        def has_write_access_for_password(account, target):
            passwd = ''.join([random.choice(string.ascii_letters) for n in range(12)])
            try:
                udm.modify_object('users/user', binddn=account.dn, bindpwd=account.password, dn=target.dn, set={
                    'password': passwd,
                    'overridePWHistory': 1,
                    'overridePWLength': 1,
                })
                target.password = passwd
            except Exception:
                return False
            return True

        def verify_no_write_access_for_password(account, target):
            if has_write_access_for_password(account, target):
                fail('%s can set password of %s' % (account, target))

        def verify_write_access_for_password(account, target):
            if not has_write_access_for_password(account, target):
                fail('%s cannot set password of %s' % (account, target))

        def has_write_access_for_descr(account, target):
            try:
                udm.modify_object('users/user', binddn=account.dn, bindpwd=account.password, dn=target.dn, set={
                    'description': 'foo bar',
                })
            except Exception:
                return False
            return True

        def verify_no_write_access_for_descr(account, target):
            if has_write_access_for_descr(account, target):
                fail('%s can set description of %s' % (account, target))

        def verify_write_access_for_descr(account, target):
            if not has_write_access_for_descr(account, target):
                fail('%s cannot set description of %s' % (account, target))

        admin_dn = ucr['tests/domainadmin/account']
        admin_name = ldap.dn.str2dn(admin_dn)[0][0][1]
        admin_pwd = ucr['tests/domainadmin/pwd']
        admin = Account("Administrator", admin_dn, admin_name, admin_pwd)

        # create helpdesk groups
        try:
            what = 'Helpdesk group'
            hdgroup_a_dn, hdgroup_a = udm.create_group()
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)

        try:
            what = 'Helpdesk group'
            hdgroup_b_dn, hdgroup_b = udm.create_group()
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)

        # create helpdesk users
        try:
            what = 'Helpdesk user'
            hduser_a_dn, hduser_a_name = udm.create_user()
            hduser_a = Account(what, hduser_a_dn, hduser_a_name)
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)
        else:
            print('Created %s' % (hduser_a,))

        try:
            what = 'Helpdesk user'
            hduser_b_dn, hduser_b_name = udm.create_user()
            hduser_b = Account(what, hduser_b_dn, hduser_b_name)
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)
        else:
            print('Created %s' % (hduser_b,))

        # add users to corresponding groups
        udm.modify_object('groups/group', dn=hdgroup_a_dn, append={
            'users': [hduser_a.dn],
        })

        udm.modify_object('groups/group', dn=hdgroup_b_dn, append={
            'users': [hduser_b.dn],
        })

        # create new test users
        try:
            what = 'Unprotected user'
            unprot_user_a_dn, unprot_user_a_name = udm.create_user()
            unprot_user_a = Account(what, unprot_user_a_dn, unprot_user_a_name)
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)
        else:
            print('Created %s' % (unprot_user_a,))

        try:
            what = 'Unprotected user'
            unprot_user_b_dn, unprot_user_b_name = udm.create_user()
            unprot_user_b = Account(what, unprot_user_b_dn, unprot_user_b_name)
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)
        else:
            print('Created %s' % (unprot_user_b,))

        # create new protected test user
        try:
            what = 'Protected user'
            prot_user_dn, prot_user_name = udm.create_user()
            prot_user = Account(what, prot_user_dn, prot_user_name)
        except Exception as exc:
            fail('Creating %s failed: %s' % (what, exc), ucstest_errorcode)
        else:
            print('Created %s' % (prot_user,))

        # configure group a
        univention.config_registry.handler_set([
            'ldap/acl/user/passwordreset/accesslist/groups/helpdesk-a=%s' % (hdgroup_a_dn,),
            'ldap/acl/user/passwordreset/protected/uid=Administrator,%s' % (prot_user.name,),
        ])

        # Activate passwordreset ACLs:
        utils.restart_slapd()

        # ========== TESTS ==========

        # test if Administrator can set passwords
        print('==> Test 1: can %s set passwords' % admin)
        for target in (unprot_user_a, prot_user):
            verify_write_access_for_password(admin, target)

        # test if helpdesk user can set passwords
        print('==> Test 2: can helpdesk user set passwords of unprotected users')
        verify_write_access_for_password(hduser_a, unprot_user_a)

        print('==> Test 3: can helpdesk user set passwords of protected users')
        for target in (admin, prot_user):
            verify_no_write_access_for_password(hduser_a, target)

        # do test with two helpdesk groups
        print('==> Testing with two helpdesk groups now.')
        univention.config_registry.handler_set([
            'ldap/acl/user/passwordreset/accesslist/groups/helpdesk-b=%s' % hdgroup_b_dn,
        ])

        # Activate passwordreset ACLs:
        utils.restart_slapd()

        # test if helpdesk user can set passwords
        print('==> Test 4: can helpdesk user set passwords of unprotected users')
        verify_write_access_for_password(hduser_a, unprot_user_a)

        print('==> Test 5: can helpdesk user set passwords of protected users')
        for target in (admin, prot_user):
            verify_no_write_access_for_password(hduser_a, target)

        # test if helpdesk user can set passwords
        print('==> Test 6: can helpdesk user set passwords of unprotected users')
        verify_write_access_for_password(hduser_b, unprot_user_b)

        print('==> Test 7: can helpdesk user set passwords of protected users')
        for target in (admin, prot_user):
            verify_no_write_access_for_password(hduser_b, target)

        # test if unprotected user with expired password can be reset
        print('==> Test 8: test if unprotected user with expired password can be reset')
        udm.modify_object('users/user', dn=unprot_user_b.dn, set={
            'password': default_password,
            'overridePWHistory': 1,
            'overridePWLength': 1,
            'pwdChangeNextLogin': 1,
        })
        verify_write_access_for_password(hduser_a, unprot_user_b)

        # test if unprotected user with pw expiry policy can be set
        print('==> Test 9: test if unprotected user with pw expiry policy can be set')
        polname = 'pwdpol-ucs-test'
        try:
            udm.create_object('policies/pwhistory', position='cn=policies,%(ldap/base)s' % ucr, set={
                'name': polname,
                'length': 5,
                'expiryInterval': 7,
                'pwLength': 8,
            })
        except Exception:
            fail('Creating policies/pwhistory failed', ucstest_errorcode)

        try:
            udm.modify_object('users/user', dn=unprot_user_b.dn, policy_reference='cn=%s,cn=policies,%s' % (polname, ucr['ldap/base']))
        except Exception:
            fail('Setting reference of policies/pwhistory object %s to %s failed' % (polname, unprot_user_b), ucstest_errorcode)
        verify_write_access_for_password(hduser_a, unprot_user_b)

        # do test with additional attributes
        # test if helpdesk user can set description BEFORE enabling it
        print('==> Test 10: can helpdesk user set description of unprotected user')
        verify_no_write_access_for_descr(hduser_a, unprot_user_a)

        # test if helpdesk user can set description AFTER enabling it
        passwordreset_attributes = ucr['ldap/acl/user/passwordreset/attributes']
        passwordreset_attributes += ',description'
        univention.config_registry.handler_set([
            'ldap/acl/user/passwordreset/attributes=%s' % (passwordreset_attributes,),
        ])

        # Activate passwordreset ACLs:
        utils.restart_slapd()

        verify_write_access_for_descr(hduser_a, unprot_user_a)

        # test if unprotected (simple) user can set description of other users
        print('==> Test 12: can unprotected (simple) user set description of other users')
        for target in (hduser_a, admin, hduser_b):
            verify_no_write_access_for_descr(unprot_user_a, target)

        # test if unprotected (simple) user can set password of other users
        print('==> Test 13: can unprotected (simple) user set password of other users')
        for target in (hduser_a, admin, hduser_b):
            verify_no_write_access_for_password(unprot_user_a, target)
finally:
    # Important: deactivate LDAP ACLs again
    utils.restart_slapd()
