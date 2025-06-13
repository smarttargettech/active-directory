#!/usr/share/ucs-test/runner python3
## desc: Test the UMC group creation, modification and deletion
## bugs: [34792]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## exposure: dangerous

import sys

from univention.testing import utils
from univention.testing.strings import random_username

from umc import UMCBase


class TestUMCGroupsCreation(UMCBase):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()
        self.ldap_base = None

    def create_group(self, groupname, policynames={}):
        """
        Creates a group with a provided 'groupname' and provided
        'policynames' if any for the test by making a UMC-request 'udm/add'.
        """
        options = [{
            "object": {
                "sambaGroupType": "2",
                "name": groupname,
                "adGroupType": "-2147483646",
                "$options$": {"samba": True, "posix": True},
                "$policies$": policynames,
            },
            "options": {"container": "cn=groups," + self.ldap_base, "objectType": "groups/group"}},
        ]

        try:
            request_result = self.client.umc_command('udm/add', options, 'groups/group').result
            if not request_result:
                utils.fail("Request 'udm/add' group failed. Response: %r\nRequest options: %r\n"
                           "hostname: %r" % (request_result, options, self.hostname))
            if not request_result[0].get('success'):
                utils.fail("Request 'udm/add' group not successful. Response: %r\nRequest options: %r\n"
                           "hostname: %r" % (request_result, options, self.hostname))
        except Exception as exc:
            utils.fail("Exception while making 'udm/add' group request: %s" %
                       exc)

    def add_group_policy(self, groupname, policyname):
        """
        Adds the provided 'policyname' to the provided 'groupname'
        by making a UMC 'udm/put' request with respective options.
        """
        options = [{"object": {"$policies$": {"policies/umc": ["cn=" + policyname + ",cn=UMC,cn=policies," + self.ldap_base]}, "$dn$": "cn=" + groupname + ",cn=groups," + self.ldap_base}, "options": {}}]
        try:
            request_result = self.client.umc_command('udm/put', options, 'groups/group').result
            if not request_result:
                utils.fail(f"Request 'udm/put' to add policy to a group with options '{options}' failed, hostname {self.hostname}")
            if not request_result[0].get('success'):
                utils.fail(f"Request 'udm/put' to add policy to a group with options '{options}' failed, no success = True in response, hostname {self.hostname}")
        except Exception as exc:
            utils.fail("Exception while making 'udm/put' request: %s" % exc)

    def get_group_by_name(self, groupname):
        """
        Returns the group data with 'groupname' by making a 'udm/get'
        UMC request.
        """
        options = ["cn=" + groupname + ",cn=groups," + self.ldap_base]
        try:
            request_result = self.client.umc_command('udm/get', options, 'groups/group').result
            if not request_result:
                utils.fail(f"Request 'udm/get' with options '{options}' failed, hostname '{self.hostname}'")
            return request_result
        except Exception as exc:
            utils.fail("Exception while making 'udm/get' request: %s" % exc)

    def main(self):
        """Method to test the UMC group creation, modification and deletion"""
        self.create_connection_authenticate()
        self.ldap_base = self.ucr.get('ldap/base')

        test_groupname = 'umc_test_group_' + random_username(6)
        policyname = "default-udm-self"

        try:
            print("Creating a test group with a name '%s'" % test_groupname)
            self.create_group(test_groupname)
            if not self.check_obj_exists(test_groupname, "groups/group"):
                utils.fail("Failed to query the newly created group '%s'" % test_groupname)

            print(f"Adding a '{policyname}' policy to a test group '{test_groupname}'")
            self.add_group_policy(test_groupname, policyname)

            print(f"Checking test group '{test_groupname}' policies for '{policyname}'")
            group_policies = self.get_group_by_name(test_groupname)[0].get('$policies$')
            if not group_policies:
                utils.fail(f"The group policies for '{test_groupname}' are empty or not present after '{policyname}' policy was applied to group")

            group_policies = group_policies.get('policies/umc')
            if not group_policies:
                utils.fail(f"The group 'policies/umc' field for '{test_groupname}' is empty or not present after '{policyname}' policy was applied to group")
            if "cn=" + policyname + ",cn=UMC,cn=policies," + self.ldap_base not in group_policies:
                utils.fail(f"The policy '{policyname}' is not in a group '{test_groupname}' policies '{group_policies}'")
        finally:
            print("Removing created test group if it exists")
            if self.check_obj_exists(test_groupname, "groups/group"):
                self.delete_obj(test_groupname, "groups", "groups/group")


if __name__ == '__main__':
    TestUMC = TestUMCGroupsCreation()
    sys.exit(TestUMC.main())
