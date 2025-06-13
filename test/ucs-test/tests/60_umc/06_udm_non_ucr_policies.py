#!/usr/share/ucs-test/runner python3
## desc: Test UMC object policies with non-UCR-policies
## bugs: [35314]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## exposure: dangerous

from sys import exit

from univention.testing import utils
from univention.testing.strings import random_username
from univention.testing.udm import UCSTestUDM

from umc import UMCBase


class TestUMCnonUCRpolicies(UMCBase):

    def __init__(self):
        super().__init__()
        self.UDM = None

        self.base_container_dn = ''
        self.intermediate_container_dn = ''

        self.base_policy_dn = ''
        self.intermediate_policy_dn = ''
        self.user_policy_dn = ''

        # self.test_user_dn = ''
        self.test_user_2_dn = ''

    def get_user_policy(self, user_dn, policy_dn=None, flavor="navigation"):
        """Makes a 'udm/object/policies' request and returns result"""
        options = [{
            "objectType": "users/user",
            "policies": [policy_dn],
            "policyType": "policies/pwhistory",
            "objectDN": user_dn,
            "container": None,
        }]
        request_result = self.client.umc_command('udm/object/policies', options, flavor).result
        if not request_result:
            utils.fail("The object policy response result should not be empty")
        return request_result

    def create_test_containers_in_ldap(self):
        """
        Creates a 'base_test_container' (in the ldap/base) and another
        'intermediate_test_container' inside the 'base_test_container'
        for the test.
        """
        print("\nCreating a 'base_test_container' in the 'ldap_base':\n")
        self.base_container_dn = self.UDM.create_object('container/cn', name='base_test_container', position=self.ldap_base)

        print("\nCreating an 'intermediate_test_container' inside the 'base_test_container':\n")
        self.intermediate_container_dn = self.UDM.create_object('container/cn', name='intermediate_test_container', position=self.base_container_dn)

    def create_test_policies(self):
        """
        Creates three policies: for the 'base_test_container',
        'intermediate_test_container', and for one of the test users.
        In all cases the 'policies/pwhistory' is being used with the
        following settings:

        For the 'base_test_container': length=5; pwLength=5.
        For the 'intermediate_test_container': length=4; pwLength=4.
        For the 'umc_test_user_policy': length=3; pwLength=3.
        """
        print("\nCreating a policy for the 'base_test_container':\n")
        self.base_policy_dn = self.UDM.create_object(
            'policies/pwhistory',
            position="cn=policies," + self.ldap_base,
            name='umc_test_policy_base',
            **{
                "length": "5",
                "pwQualityCheck": False,
                "pwLength": "5",
                "$policies$": {},
            },
        )

        print("\nCreating a policy for the 'intermediate_test_container':\n")
        self.intermediate_policy_dn = self.UDM.create_object(
            'policies/pwhistory',
            position="cn=policies," + self.ldap_base,
            name='umc_test_policy_intermediate',
            **{
                "length": "4",
                "pwQualityCheck": False,
                "pwLength": "4",
                "$policies$": {},
            },
        )

        print("\nCreating a policy to be used by one of the 'umc_test_user's:\n")
        self.user_policy_dn = self.UDM.create_object(
            'policies/pwhistory',
            position="cn=policies," + self.ldap_base,
            name='umc_test_user_policy',
            **{
                "length": "3",
                "pwQualityCheck": False,
                "pwLength": "3",
                "$policies$": {},
            },
        )

    def create_test_users(self):
        """
        Creates two users inside the 'intermediate_test_container':
        first has own 'umc_test_user_policy' and is not a Samba user;
        second has no own user policy, but being a Samba user.
        """
        # print("\nCreating a test user with no samba inside the 'intermediate_test_container' with the 'umc_test_user_policy' applied:\n")
        # self.test_user_dn = self.UDM.create_user(**{
        #     'position': self.intermediate_container_dn,
        #     'username': 'umc_test_user_' + random_username(),
        #     'policy-reference': self.user_policy_dn,
        #     'options': ['kerberos', 'posix', 'person', 'mail'],  # no Samba
        # })[0]

        print("\nCreating a second test user with samba and without user policy applied inside the 'intermediate_test_container':\n")
        self.test_user_2_dn = self.UDM.create_user(
            position=self.intermediate_container_dn,
            username='umc_test_user_' + random_username(),
        )[0]

    def check_single_and_multiple_policies(self):
        """
        Check the handling of basic single and multiple (inherited)
        policies
        """
        print("\nChecking handling of single and multiple (inherited) policies:")

        print("\nApplying a 'umc_test_policy_base' to the 'base_test_container', checking correct inheritance:\n")
        self.UDM.modify_object('container/cn', **{'dn': self.base_container_dn, 'policy_reference': self.base_policy_dn})  # noqa: PIE804

        # Second user should have inherited policy from the base container:
        self.check_policies('5', '5', self.test_user_2_dn)

        # First user with own 'umc_test_user_policy' winning over container
        # policies as the closest policy:
        # self.check_policies('3', '3', self.test_user_dn, self.user_policy_dn)

        print("\nApplying a 'umc_test_policy_intermediate' to the 'intermediate_test_container', checking correct inheritance:\n")
        self.UDM.modify_object('container/cn', **{'dn': self.intermediate_container_dn, 'policy_reference': self.intermediate_policy_dn})  # noqa: PIE804

        # Second user should have inherited policy from the intermediate
        # container winning as the closest policy:
        self.check_policies('4', '4', self.test_user_2_dn)

        # First user with own 'umc_test_user_policy' winning over container
        # policies as the closest policy:
        # self.check_policies('3', '3', self.test_user_dn, self.user_policy_dn)

    def check_fixed_and_empty_attributes(self):
        """
        Checks if policies with fixed and empty attributes are inherited
        correctly.
        """
        print("\nAdding a Fixed attribute 'univentionPWLength' to the 'umc_test_policy_base' and checking correct inheritance:\n")
        self.UDM.modify_object('policies/pwhistory', **{'dn': self.base_policy_dn, 'fixedAttributes': ['univentionPWLength']})  # noqa: PIE804

        # Both users should have pwLength=5 (Fixed attribute from the
        # base container) and Length=4 (inherited from intermediate container)
        self.check_policies('4', '5', self.test_user_2_dn)
        # self.check_policies('4', '5', self.test_user_dn)

        print("\nAdding an Empty attribute 'univentionPWLength' to the 'umc_test_policy_intermediate' and checking correct inheritance:\n")
        self.UDM.modify_object('policies/pwhistory', **{'dn': self.intermediate_policy_dn, 'emptyAttributes': ['univentionPWLength']})  # noqa: PIE804

        # Both users should have pwLength=5 (Even with empty attribute in
        # intermediate container due to Fixed attribute on the base container)
        self.check_policies('4', '5', self.test_user_2_dn)
        # self.check_policies('4', '5', self.test_user_dn)

        print("\nRemoving Fixed attribute from the 'umc_test_policy_base':\n")
        self.UDM.modify_object('policies/pwhistory', **{'dn': self.base_policy_dn, 'set': {'fixedAttributes': ""}})  # noqa: PIE804

        # Both users should have an empty pwLength (due to empty attribute
        # on the intermediate container):
        self.check_policies('4', '', self.test_user_2_dn)
        # self.check_policies('4', '', self.test_user_dn)

    def check_required_excluded_object_classes(self):
        """
        Checks if policies with a required or excluded object class are
        inherited correctly.
        """
        print("\nAdding a 'sambaSamAccount' as a required object class to the 'umc_test_policy_intermediate' and checking correct inheritance:\n")
        self.UDM.modify_object('policies/pwhistory', **{'dn': self.intermediate_policy_dn, 'requiredObjectClasses': ["sambaSamAccount"]})  # noqa: PIE804

        # Second user (with Samba) should have an intermediate container policy
        # (Length=4 and empty pwLength), first user (without Samba) should have
        # own 'umc_test_user_policy' winning (Length=pwLength=3):
        self.check_policies('4', '', self.test_user_2_dn)
        # self.check_policies('3', '3', self.test_user_dn, self.user_policy_dn)

        print("\nAdding 'sambaSamAccount' to the excluded object class of the 'umc_test_policy_base' and checking correct inheritance:\n")
        self.UDM.modify_object('policies/pwhistory', **{'dn': self.base_policy_dn, 'prohibitedObjectClasses': ["sambaSamAccount"]})  # noqa: PIE804

        # Second user (with Samba) should have an intertmediate container
        # policy (Length=4 and an empty pwLength), first user (without Samba)
        # should have base container policy inherited (Length=pwLength=5):
        self.check_policies('4', '', self.test_user_2_dn)
        # self.check_policies('5', '5', self.test_user_dn)

    def assert_policies(self, should_be, in_fact):
        """Asserts that 'in_fact' equals 'should_be'."""
        if in_fact != should_be:
            utils.fail(f"The user object policy was reported as '{in_fact}', while should be '{should_be}'")

    def check_policies(self, length, pw_length, user_dn, user_policy_dn=None):
        """
        Creates a 'should_be' set with the given 'length' and 'pw_length'
        values; Makes a 'udm/object/policy' UMC request for a given
        'user_dn' and 'user_policy_dn' and creates a set out of it:
        (('length', value), ('pwLength', value)) named 'in_fact'.
        Calls assertion method with 'should_be' and 'in_fact' sets.
        """
        should_be = {('length', length), ('pwLength', pw_length)}
        obj_policy = self.get_user_policy(user_dn, user_policy_dn)

        in_fact = set()
        in_fact.add(('length', obj_policy[0].get('length').get('value')))
        in_fact.add(('pwLength', obj_policy[0].get('pwLength').get('value')))

        self.assert_policies(should_be, in_fact)

    def main(self):
        """A test to check non-UCR policies handling by the UMC"""
        self.create_connection_authenticate()

        with UCSTestUDM() as self.UDM:
            self.create_test_containers_in_ldap()
            self.create_test_policies()
            self.create_test_users()

            self.check_single_and_multiple_policies()
            self.check_fixed_and_empty_attributes()
            self.check_required_excluded_object_classes()


if __name__ == '__main__':
    TestUMC = TestUMCnonUCRpolicies()
    exit(TestUMC.main())
