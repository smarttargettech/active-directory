#!/usr/share/ucs-test/runner python3
## desc: Test unsetting userexpiry attribute via UMC
## bugs: [25279]
## roles:
##  - domaincontroller_master
## exposure: dangerous

import sys

from univention.testing import utils
from univention.testing.strings import random_username
from univention.testing.udm import UCSTestUDM

from umc import UMCBase


class TestUMCUserAuthentication(UMCBase):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()

        self.UDM = None

        self.test_user_dn = ''
        self.test_username = ''
        self.test_password = ''

    def create_user(self):
        """Creates a group and a user in it for the test."""
        print("\nCreating a user '%s'" % (self.test_username,))

        self.test_user_dn = self.UDM.create_user(
            password=self.test_password,
            username=self.test_username,
            policy_reference='cn=default-umc-all,cn=UMC,cn=policies,%s' % self.ucr['ldap/base'],
        )[0]
        utils.verify_ldap_object(self.test_user_dn)

    def set_userexpiry_None(self):
        """Queries UDM's users/user from UMC"""
        return self.modify_object([{"object": {"userexpiry": None, "$dn$": self.test_user_dn}, "options": {"objectType": "users/user"}}], 'users/user')

    def set_userexpiry_testval(self):
        """Queries UDM's users/user from UMC"""
        return self.modify_object([{"object": {"userexpiry": "2015-02-02", "$dn$": self.test_user_dn}, "options": {"objectType": "users/user"}}], 'users/user')

    def set_userexpiry_empty(self):
        """Queries UDM's users/user from UMC"""
        return self.modify_object([{"object": {"userexpiry": "", "$dn$": self.test_user_dn}, "options": {"objectType": "users/user"}}], 'users/user')

    def main(self):
        """Tests the UMC user authentication and various password change cases."""
        self.test_username = 'umc_test_user_' + random_username(6)
        self.test_password = 'univention'

        with UCSTestUDM() as self.UDM:
            self.create_user()
            self.create_connection_authenticate()

            prior_testval = utils.get_ldap_connection().get(self.test_user_dn)
            self.set_userexpiry_testval()
            response = self.get_object([self.test_user_dn], 'users/user')
            try:
                assert response[0]["userexpiry"] == "2015-02-02", "userexpiry not initialized properly: %s" % (response[0]["userexpiry"],)
            except KeyError:  # Bug #37924
                print('FAIL! https://forge.univention.org/bugzilla/show_bug.cgi?id=37924')
                print('PRIOR=%r' % (prior_testval,))
                after_testval = utils.get_ldap_connection().get(self.test_user_dn)
                print('AFTER=%r' % (after_testval,))
                print('Equal=%s' % (prior_testval == after_testval,))
                raise

            self.set_userexpiry_empty()
            response = self.get_object([self.test_user_dn], 'users/user')
            assert not response[0].get('userexpiry'), "unset of userexpiry via empty string failed"
            print("OK: unset of userexpiry via empty string succeeded")

            self.set_userexpiry_testval()
            response = self.get_object([self.test_user_dn], 'users/user')
            assert response[0]["userexpiry"] == "2015-02-02", "userexpiry not initialized properly"

            self.set_userexpiry_None()
            response = self.get_object([self.test_user_dn], 'users/user')
            assert not response[0].get('userexpiry'), "unset of userexpiry via None failed"
            print("OK: unset of userexpiry via None succeeded")


if __name__ == '__main__':
    TestUMC = TestUMCUserAuthentication()
    sys.exit(TestUMC.main())
