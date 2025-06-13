#!/usr/share/ucs-test/runner python3
# #!/usr/share/ucs-test/runner pytest-3 -s
## desc: Test to check custom mappings for the AD-Connector
## bugs: [49981]
## roles:
##  - domaincontroller_master
## exposure: dangerous
## packages:
##  - univention-ad-connector
## tags:
##  - skip_admember

import os
import sys
import unittest

import ldap

import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing.connector_common import NormalUser, create_udm_user
from univention.testing.strings import random_string

from adconnector import ADConnection, restart_adconnector, wait_for_sync


sys.path.append("$TESTLIBPATH")


class TestADCustomMappings(unittest.TestCase):
    def setUp(self):
        with ucr_test.UCSTestConfigRegistry() as ucr:
            ucr.load()
            self.ldap_base = ucr["ldap/base"]

        self.attribute = "univentionFreeAttribute20"
        self.target_attribute = "company"
        self.target_position = f"cn=groups,{ucr['connector/ad/ldap/base']}"
        self.mapping_file = "/etc/univention/connector/ad/localmapping.py"
        self.mapping_file_dir = os.path.dirname(self.mapping_file)

        TEST_MAPPING = (
            "import univention.connector\n"
            "def mapping_hook(ad_mapping):\n"
            "    ad_mapping['user'].post_attributes['organisation'] =\\\n"
            "        univention.connector.attribute(\n"
            "            ucs_attribute='{attribute}',\n"
            "            ldap_attribute='{attribute}',\n"
            "            con_attribute='{target_attribute}'\n"
            "        )\n"
            "    ad_mapping['user'].post_attributes['employeeNumber'] = \\\n"
            "        univention.connector.attribute(\n"
            "            ucs_attribute='employeeNumber',\n"
            "            ldap_attribute='employeeNumber',\n"
            "            con_attribute='employeeNumber'\n"
            "        )\n"
            "    ad_mapping['group'].attributes['displayName'] = \\\n"
            "        univention.connector.attribute(\n"
            "            ucs_attribute='DisplayName',\n"
            "            ldap_attribute='displayName',\n"
            "            con_attribute='displayName'\n"
            "        )\n"
            "    ad_mapping['user'].position_mapping=[('cn=users,{ldap_base}', '{target_position}')]\n"
            "    return ad_mapping\n".format(
                attribute=self.attribute, target_attribute=self.target_attribute, ldap_base=ucr["ldap/base"], target_position=self.target_position,
            )
        )

        print("Using as test-mapping:\n%s\n" % TEST_MAPPING, file=sys.stderr)

        try:
            os.mkdir(self.mapping_file_dir)
        except OSError:
            print(
                "Directory already exists: %s\n" % self.mapping_file_dir,
                file=sys.stderr,
            )

        with open(self.mapping_file, "w") as f:
            f.write(TEST_MAPPING)

        # activate mapping by restarting the ad-connector...
        restart_adconnector()

        self.udm = udm_test.UCSTestUDM()
        self.adc = ADConnection()

    def tearDown(self):
        try:
            self.udm.cleanup()
            os.remove(self.mapping_file)
            # deactivate mapping by restarting the ad-connector after file has
            # gone...
            restart_adconnector()

        except OSError:
            print(
                "Surprising, that there is nothing to remove from this test.\n",
                file=sys.stderr,
            )

    def create_extended_attribute(
        self, udm, ldapMapping, module, defaultValue="defaultValue-TestFailed",
    ):
        """
        Creates an extended attribute with a default value under module (e.g.
        under 'user/user')
        """
        print(
            "Creating extended attribute '%s' under '%s' with default value '%s'\n"
            % (ldapMapping, self.ldap_base, defaultValue),
            file=sys.stderr,
        )

        udm.create_object(
            "settings/extended_attribute",
            position="cn=custom attributes,cn=univention,%s" % self.ldap_base,
            name=ldapMapping, ldapMapping=ldapMapping, CLIName=ldapMapping, objectClass="univentionFreeAttributes", shortDescription="test value: %s" % defaultValue, valueRequired="1", module=[module], default=defaultValue,
        )

    def test_ldap_to_ad_with_mapping(self):
        """
        this test will create a user and set its extended attribute to a random
        value. It will then check if the random value appears in the 'company'
        field of the user in the active directory, because that is hard coded
        in the custom mapping.
        """
        test_string = random_string()
        self.create_extended_attribute(self.udm, self.attribute, "users/user")

        # create a random user
        udm_user = NormalUser(selection=("username", "lastname"))
        udm_user.basic["password"] = "univention"
        udm_user.basic["description"] = (
            "test value: '%s'" % test_string
        )  # useful as debugging hint

        # the 'o' field in ldap is usually mapped to company in AD's
        # but we have hardcoded in our mapping, that the company should
        # be overwritten by the value from the extended attribute
        udm_user.basic["organisation"] = "test failed"

        # write test_string into extended attribute...
        udm_user.basic[self.attribute] = test_string
        udm_user.basic["employeeNumber"] = "42"
        udm_user.basic["displayName"] = "test uuuuuuser"

        (udm_user_dn, ad_user_dn) = create_udm_user(self.udm, self.adc, udm_user, wait_for_sync, verify=False)

        ad_user_dn = f"{ldap.explode_dn(ad_user_dn)[0]},{self.target_position}"
        print(
            "Summary of users to be synchronized:\n\tudm_user_dn:\t%s,\n\ts4_user_dn:\t%s\n"
            % (udm_user_dn, ad_user_dn),
            file=sys.stderr,
        )

        # verify that the user exists on the 'ad-side'...
        assert self.adc.exists(ad_user_dn) is True

        # check the value from the mapping
        assert self.adc.get_attribute(ad_user_dn, self.target_attribute) == [test_string.encode("UTF-8")]
        assert self.adc.get_attribute(ad_user_dn, "employeeNumber") == [b"42"]
        assert self.adc.get_attribute(ad_user_dn, "displayName") == [b"test uuuuuuser"]


if __name__ == "__main__":
    unittest.main()
