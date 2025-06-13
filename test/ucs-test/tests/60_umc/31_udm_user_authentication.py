#!/usr/share/ucs-test/runner python3
## desc: Test the UMC user authentication and password change
## bugs: [34369, 36901]
## roles:
##  - domaincontroller_master
## tags: [skip_admember]
## exposure: dangerous

import sys
from time import localtime, sleep, strftime, time

from ldap.filter import filter_format

from univention.lib.umc import Unauthorized
from univention.testing import utils
from univention.testing.strings import random_username
from univention.testing.ucs_samba import wait_for_drs_replication
from univention.testing.udm import UCSTestUDM
from univention.testing.umc import Client

from umc import UDMModule


class TestUMCUserAuthentication(UDMModule):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()

        self.UDM = None

        self.test_user_dn = ''
        self.test_username = ''
        self.test_password = ''
        self.test_password_unicode = ''

    def create_user_and_group(self):
        """Creates a group and a user in it for the test."""
        test_groupname = 'umc_test_group_' + random_username(6)

        print("\nCreating a group '%s' and a user '%s' in it for the test:\n" % (test_groupname, self.test_username))
        test_group_dn = self.UDM.create_group(name=test_groupname)[0]
        utils.verify_ldap_object(test_group_dn)

        self.test_user_dn = self.UDM.create_user(password=self.test_password, username=self.test_username, primaryGroup=test_group_dn)[0]
        utils.verify_ldap_object(self.test_user_dn)

    def authenticate_to_umc(self, username, password):
        """
        Authenticates to UMC using 'self.client' and given
        'password' with 'username'. Updates the cookie.
        Returns 'True' on success and 'False' in any other case.
        """
        try:
            client = Client()
            response = client.authenticate(username, password)
            assert response.status == 200
            return True
        except Unauthorized:
            return False

    def change_user_password(self, user_dn, new_password):
        """
        Makes a 'udm/put' UMC request with a 'new_password' and
        a 'user_dn' in options to change the password.
        """
        print("\nChanging '%s' user password to '%s'" % (user_dn, new_password))
        options = [{"object": {"password": new_password, "$dn$": user_dn}, "options": {"objectType": "users/user"}}]

        request_result = self.request("udm/put", options, "users/user")
        if not request_result[0].get('success'):
            print("Change password UMC response: '%s'" % request_result)
            utils.fail("The UMC request to change 'user'=%s password to '%s' failed, as there are no 'success'=True in response" % (user_dn, new_password))
        sleep(30)  # wait for new password to sync

    def check_random_and_valid_passwords(self):
        """
        Tries to authenticate to UMC with a random password
        and with a valid password.
        """
        print("\nTrying to authenticate to UMC with username '%s' and "
              "a random password:" % self.test_username)
        if self.authenticate_to_umc(self.test_username, self.test_password + random_username(4)):
            utils.fail("Authentication with a valid 'username'=%s and random password succeeded." % self.test_username)

        print("\nTrying to authenticate to UMC with username '%s' and a valid initial password '%s':" % (self.test_username, self.test_password))
        if not self.authenticate_to_umc(self.test_username, self.test_password):
            utils.fail("Authentication with a valid 'username'=%s and 'password'=%s failed." % (self.test_username, self.test_password))

    def check_change_old_new_unicode_passwords(self):
        """
        Changes test user password and tries to authenticate to UMC with
        old and new passwords. After adds unicode chars to user password
        and tries to authenticate with it.
        """
        self.change_user_password(self.test_user_dn, self.test_password + '1')

        print("\nTrying to authenticate to UMC with username '%s' and an old password '%s':" % (self.test_username, self.test_password))
        if self.authenticate_to_umc(self.test_username, self.test_password):
            utils.fail("Authentication with old password '%s' succeeded after password change." % self.test_password)

        print("\nTrying to authenticate to UMC with username '%s' and a new valid password '%s':"
              % (self.test_username, self.test_password + '1'))
        if not self.authenticate_to_umc(self.test_username, self.test_password + '1'):
            utils.fail("Authentication with a 'username'=%s and a new 'password'=%s failed." % (self.test_username, self.test_password + '1'))

        # New password with (Latin-1 Latin-A Latin-B unicode chars)
        self.test_password_unicode = self.test_password + '_ÃŎǦ'
        self.change_user_password(self.test_user_dn, self.test_password_unicode)

        print("\nTrying to authenticate to UMC with username '%s' and a new valid unicode password '%s':" % (self.test_username, self.test_password_unicode))
        if not self.authenticate_to_umc(self.test_username, self.test_password_unicode):
            utils.fail("Authentication with a new unicode password '%s' did not succeeded." % self.test_password_unicode)

    def generate_expiry_date(self, time_seconds):
        """
        Returns the account expiry date in a format: 'YYYY-MM-DD'
        by adding the given 'time_seconds' to the current time.
        """
        expiry_date = time()
        expiry_date += time_seconds
        return strftime('%Y-%m-%d', localtime(expiry_date))

    def check_expired_deactivated_removed_account(self):
        """
        Sets test user account a past expiry date and tries to authenticate.
        Re-sets the expiry date back to the future.
        Deactivates user account and tries to authenticate.
        Removes user account and tries to authenticate.
        """
        # approx. amount of seconds in 1 month is 2630000
        expiry_date = self.generate_expiry_date(-2630000)

        print("\nSetting an expiry date in the past for the test user '%s' account and trying to authenticate:\n" % self.test_username)
        self.UDM.modify_object('users/user', dn=self.test_user_dn, userexpiry=expiry_date)
        utils.wait_for_connector_replication()
        wait_for_drs_replication(filter_format('(sAMAccountName=%s)', (self.test_username,)))
        if self.authenticate_to_umc(self.test_username, self.test_password_unicode):
            utils.fail("Authentication with an expired user account succeeded.")

        # approx. amount of seconds in 1 month is 2630000
        expiry_date = self.generate_expiry_date(2630000)
        self.UDM.modify_object('users/user', dn=self.test_user_dn, userexpiry=expiry_date)
        utils.wait_for_connector_replication()
        sleep(30)  # wait for sync

        print("\nDeactivating the test user '%s' account and trying to authenticate:\n" % self.test_username)
        # user modified two times as disabling account and
        # changing expiry date at the same time does not work:
        self.UDM.modify_object('users/user', dn=self.test_user_dn, disabled="1")

        wait_for_drs_replication(filter_format('(sAMAccountName=%s)', (self.test_username,)))
        utils.wait_for_connector_replication()
        if self.authenticate_to_umc(self.test_username, self.test_password_unicode):
            utils.fail("Authentication with a deactivated user account succeeded.")

        print("\nRemoving the test user '%s' account and trying to authenticate:\n" % self.test_username)
        self.UDM.remove_object('users/user', dn=self.test_user_dn)
        utils.wait_for_connector_replication()
        if self.authenticate_to_umc(self.test_username, self.test_password_unicode):
            utils.fail("Authentication with a removed user account succeeded.")

    def main(self):
        """Tests the UMC user authentication and various password change cases."""
        self.test_username = 'umc_test_user_' + random_username(6)
        self.test_password = 'univention'

        with UCSTestUDM() as self.UDM:
            self.create_user_and_group()
            self.create_connection_authenticate()
            self.check_random_and_valid_passwords()
            self.check_change_old_new_unicode_passwords()
            self.check_expired_deactivated_removed_account()


if __name__ == '__main__':
    TestUMC = TestUMCUserAuthentication()
    sys.exit(TestUMC.main())
