#!/usr/share/ucs-test/runner python3
## desc: Test the UMC modules access for restricted users
## bugs: [34621]
## exposure: dangerous

import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.strings import random_username
from univention.testing.umc import Client

from umc import UMCBase


class TestUMCUserModules(UMCBase):

    def main(self):
        """Method to test the UMC modules access restrictions for regular users"""
        ldap_base = self.ucr.get('ldap/base')

        test_username = 'umc_test_user_' + random_username(6)
        test_password = 'univention'
        test_groupname = 'umc_test_group_' + random_username(6)
        test_policyname = 'umc_test_policy_' + random_username(6)
        test_operation_set = ["cn=ucr-all,cn=operations,cn=UMC,cn=univention," + ldap_base]

        with udm_test.UCSTestUDM() as udm:
            print("Creating a test group and a user in it for the test")
            test_group_dn = udm.create_group(name=test_groupname)[0]
            utils.verify_ldap_object(test_group_dn)

            test_user_dn = udm.create_user(password=test_password, username=test_username, primaryGroup=test_group_dn)[0]
            utils.verify_ldap_object(test_user_dn)

            # case 1: there is no group policy and thus no modules
            # should be available to the user:
            print("Checking if user '%s' has no access to umc modules" % test_username)
            user_modules = self.list_umc_modules(test_username, test_password)
            assert len(user_modules) == 0, f"The newly created test user '{test_username}' in test group '{test_groupname}' has access to the following modules '{user_modules}', when should not have access to any"

            # case 2: create custom policy and add it to the test group,
            # check available modules for the user:
            print(f"Checking if user '{test_username}' has access to only one module with custom test policy '{test_policyname}' applied to group '{test_groupname}'")
            test_policy_dn = udm.create_object('policies/umc', name=test_policyname, allow=test_operation_set)
            utils.verify_ldap_object(test_policy_dn)

            udm.modify_object('groups/group', **{'dn': test_group_dn, 'policy_reference': test_policy_dn})  # noqa: PIE804

            user_modules = self.list_umc_modules(test_username, test_password)
            assert len(user_modules) == 1, "Expected only the UCR module"

            assert user_modules[0].get('id') == 'ucr', f'Wrong module returned, expected ID==ucr: {user_modules!r}'

    def list_umc_modules(self, username, password):
        client = Client(None, username, password)
        modules = client.umc_get('modules').data.get('modules')
        modules = [mod for mod in modules if mod['id'] not in ('passwordreset',)]  # self-service might be installed, which offers a anonymous module
        return modules


if __name__ == '__main__':
    TestUMCUserModules().main()
