#!/usr/share/ucs-test/runner python3
## desc: Test the UMC file quota module
## bugs: [34625]
## exposure: dangerous
## versions:
##  3.0-0: skip
##  3.2-3: fixed

import sys

import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.strings import random_username

from umc import UMCBase


class TestUMCQuotasManagement(UMCBase):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()
        self.quota_was_in_use = None
        self.test_mount_point = '/'
        self.partition_dev = ''

    def check_quotas_query(self, quotas_query):
        """Checks if 'quotas_query' has all default fields"""
        for quota in quotas_query:
            assert 'partitionSize' in quota
            assert 'mountPoint' in quota
            assert 'partitionDevice' in quota
            assert 'freeSpace' in quota
            assert 'inUse' in quota

    def choose_partition_device(self, quotas_query):
        """
        Looks through the provided 'quotas_query' for a
        'self.test_mount_point', saves respective partition device
        to use for the test. Also saves initial quota state 'inUse'
        into the global var. Returns code 77 (RESULT_SKIP) in case
        'self.test_mount_point' was not found.
        """
        for quota in quotas_query:
            if quota['mountPoint'] == self.test_mount_point:
                self.quota_was_in_use = quota['inUse']
                self.partition_dev = quota['partitionDevice']
                return
        print("Failed to select a partition for the test, skipping")
        return self.return_code_result_skip()

    def is_dev_quota_active(self):
        """
        Returns the 'inUse' field value of the quota with a
        mount point 'self.test_mount_point' and 'self.partition_dev'.
        Makes a query for 'quota/partitions' request.
        """
        for quota in self.request('quota/partitions/query'):
            if ((quota['partitionDevice'] == self.partition_dev) and (quota['mountPoint'] == self.test_mount_point)):
                return quota['inUse']

    def is_user_quota_active(self, username):
        """
        Makes a query request for user quotas and returns True when
        quota is found for a user with provided 'username'.
        """
        options = {"filter": username, "partitionDevice": self.partition_dev}

        user_quotas = self.client.umc_command('quota/users/query', options).result
        return any(quota['user'] == username for quota in user_quotas)

    def activate_deactivate_quota(self, command):
        """
        Depending on a given 'command' activates or deactvates a
        'self.partition_dev' quota by making a UMC request 'quota/partitions/'
        """
        options = {"partitionDevice": self.partition_dev}
        assert self.client.umc_command('quota/partitions/' + command, options).result.get('objects')

    def set_remove_user_quota(self, command, username, size_limit_soft=10, size_limit_hard=10, file_limit_soft=0, file_limit_hard=0):
        """
        Sets or removes the quota for a provided 'username' and
        'self.partition_dev' depending on a given 'command'
        """
        if command == 'set':
            options = {
                "user": username,
                "partitionDevice": self.partition_dev,
                "sizeLimitSoft": size_limit_soft,
                "sizeLimitHard": size_limit_hard,
                "fileLimitSoft": file_limit_soft,
                "fileLimitHard": file_limit_hard,
            }
        elif command == 'remove':
            options = [{"object": username + "@" + self.partition_dev, "options": None}]
        self.client.umc_command('quota/users/' + command, options).result  # noqa: B018

    def main(self):
        """A method to test the filesystem quota management through UMC"""
        self.create_connection_authenticate()

        test_username = 'umc_test_user_' + random_username(6)

        with udm_test.UCSTestUDM() as UDM:
            print("Creating a test user for testing user-specific quotas setup through UMC")
            test_user_dn = UDM.create_user(password='univention', username=test_username)[0]
            utils.verify_ldap_object(test_user_dn)
            try:
                print("Making 'quota/partitions' query request and checking response structure")
                quotas_query = self.request('quota/partitions/query')
                self.check_quotas_query(quotas_query)

                print("Choosing partition device for the test (with '%s' mount point)" % self.test_mount_point)
                self.choose_partition_device(quotas_query)

                print("Deactivating quotas for partition device '%s'" % self.partition_dev)
                self.activate_deactivate_quota('deactivate')
                assert not self.is_dev_quota_active()

                print("Activating quotas for '%s' partition device" % self.partition_dev)
                self.activate_deactivate_quota('activate')
                assert self.is_dev_quota_active()

                print("Setting '%s' user quota for '%s' partition" % (test_username, self.partition_dev))
                self.set_remove_user_quota('set', test_username)
                assert self.is_user_quota_active(test_username)

                print("Removing '%s' user quota for '%s' partition" % (test_username, self.partition_dev))
                self.set_remove_user_quota('remove', test_username)
                assert not self.is_user_quota_active(test_username)

                print("Deactivating quotas for '%s' partition device" % self.partition_dev)
                self.activate_deactivate_quota('deactivate')
                assert not self.is_dev_quota_active()
            finally:
                print("Cleaning up created quotas and the test user "
                      "(if any), restoring initial partition quota "
                      "setting to 'inUse=%s'" % self.quota_was_in_use)
                if self.partition_dev:
                    # Make sure that quota is active to get the test user
                    # quota settings:
                    self.activate_deactivate_quota('activate')
                    # The test user quota is always removed to avoid
                    # 'hanging' of quotas (Bug #34879)
                    if self.is_user_quota_active(test_username):
                        self.set_remove_user_quota('remove', test_username)
                    if self.quota_was_in_use is False:
                        self.activate_deactivate_quota('deactivate')


if __name__ == '__main__':
    TestUMC = TestUMCQuotasManagement()
    sys.exit(TestUMC.main())
