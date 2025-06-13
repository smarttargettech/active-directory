#!/usr/share/ucs-test/runner python3
## desc: Test the UMC extended attributes
## bugs: [34623]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## exposure: dangerous

import sys

import atexit

import univention.testing.udm as udm_test
from univention.testing import utils
from univention.testing.strings import random_username

from umc import UDMModule


class TestUMCExtendedAttributes(UDMModule):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()
        self.ldap_base = ''

    def modify_check_user_attribute(self, user_dn, attribute_key,
                                    old_value, new_value):
        """
        Checks if the 'user_dn' has the correct 'attribute_key': 'old_value'.
        Modifies given 'user_dn' 'attribute_key' to a 'new_value'.
        Checks if the user object has the correct value after the modfication.
        """
        try:
            user = self.get_object([user_dn], "users/user")[0]
            if user[attribute_key] not in old_value:
                utils.fail("The test user (dn='%s') custom attribute '%s' "
                           "value was incorrect after user object creation, "
                           "should be '%s', but in fact '%s'"
                           % (user_dn, attribute_key, old_value,
                              user[attribute_key]))

            options = [{"object": {attribute_key: new_value, "$dn$": user_dn}, "options": None}]
            self.modify_object(options, "users/user")

            user = self.get_object([user_dn], "users/user")[0]
            assert user[attribute_key] in new_value
        except KeyError as exc:
            utils.fail(f"A KeyError exception while trying to check and modify the user attribute '{attribute_key}' value: '{exc}'")

    def modify_check_extended_attribute(self, attribute_name,
                                        attribute_key, new_value):
        """
        Modifies the extended attribute 'attribute_name' with
        'attribute_key' = 'new_value' and checks if the modification
        of the custom attribute was done correctly.
        """
        dn = ("cn=" + attribute_name + ",cn=custom attributes,cn=univention," + self.ldap_base)
        options = [{"object": {attribute_key: new_value, "$dn$": dn}, "options": None}]
        self.modify_object(options, "navigation")

        attribute = self.get_object([dn], "navigation")[0]
        try:
            if attribute[attribute_key] not in new_value:
                utils.fail("The test '%s' attribute '%s' was not modified "
                           "to '%s' after the modification request was "
                           "done, attribute state is '%s'"
                           % (attribute_name,
                              attribute_key,
                              new_value,
                              attribute))
        except KeyError as exc:
            utils.fail("A KeyError exception while trying to modify and check "
                       "the extended attribute '%s' itself: '%s'"
                       % (attribute_name, exc))

    def is_attribute_syntax_valid(self, attribute_name, obj_type, test_value):
        """
        Makes a 'udm/validate' UMC request for a given 'attribute_name',
        'obj_type' and a 'test_value' and returns the value of the 'valid'
        field.
        """
        options = {"objectType": obj_type,
                   "properties": {attribute_name: test_value}}
        try:
            for prop in self.request('udm/validate', options, obj_type):
                if prop["property"] in attribute_name:
                    return prop["valid"]
        except KeyError as exc:
            utils.fail("A KeyError exception while getting the attribute "
                       "'valid' field value '%s'" % exc)

    def check_attribute_in_module_properties(self, attribute_module,
                                             attribute_name,
                                             attribute_syntax):
        """
        Checks if the 'attribute_name' is in given 'attribute_module'
        properties and that the 'attribute_syntax' is correct,
        returns True when so. Makes a request for module properties inside.
        """
        for prop in self.request('udm/properties', flavor=attribute_module):
            if prop.get('id') == attribute_name:
                if prop.get('syntax') == attribute_syntax:
                    return True
                utils.fail("The '%s' module property '%s' exists, but does "
                           "not have the proper syntax '%s'"
                           % (attribute_module, attribute_name,
                              attribute_syntax))

    def check_attributes_query_structure(self):
        """
        Makes a query for attributes request and checks it
        for the default fields
        """
        for attribute in self.query_extended_attributes():
            if '$dn$' not in attribute:
                utils.fail("The field '$dn$' was not found in "
                           "attributes_query '%s'" % attribute)
            if 'name' not in attribute:
                utils.fail("The field 'name' was not found in "
                           "attributes_query '%s'" % attribute)
            if '$childs$' not in attribute:
                utils.fail("The field '$childs$' was not found in "
                           "attributes_query '%s'" % attribute)
            if 'labelObjectType' not in attribute:
                utils.fail("The field 'labelObjectType' was not found in "
                           "attributes_query '%s'" % attribute)
            if 'path' not in attribute:
                utils.fail("The field 'path' was not found in "
                           "attributes_query '%s'" % attribute)
            if 'objectType' not in attribute:
                utils.fail("The field 'objectType' was not found in "
                           "attributes_query '%s'" % attribute)

    def query_extended_attributes(self):
        """
        Returns a result of the 'udm/nav/object/query' UMC request
        made with respective options and 'navigation' flavor
        """
        options = {
            "objectType": "settings/extended_attribute",
            "objectProperty": "None",
            "objectPropertyValue": "",
            "container": "cn=custom attributes,cn=univention," + self.ldap_base,
            "hidden": True,
        }
        return self.request('udm/nav/object/query', options, "navigation")

    def create_check_extended_attribute(self, attribute_name,
                                        attribute_modules,
                                        attribute_syntax='string',
                                        attribute_default='',
                                        obj_class="univentionFreeAttributes",
                                        ldap_map="univentionFreeAttribute10"):
        """
        Creates an extended attribute via 'udm/add' UMC request with
        the given arguments and checks if the respective module (-s)
        properties include the created attribute
        """
        options = [{"object": {"objectClass": obj_class,
                               "module": attribute_modules,
                               "overwriteTab": False,
                               "shortDescription": "An original description",
                               "valueRequired": False,
                               "CLIName": attribute_name,
                               "fullWidth": False,
                               "doNotSearch": False,
                               "syntax": attribute_syntax,
                               "tabAdvanced": False,
                               "name": attribute_name,
                               "default": attribute_default,
                               "mayChange": True,
                               "multivalue": False,
                               "ldapMapping": ldap_map,
                               "deleteObjectClass": False,
                               "notEditable": False,
                               "disableUDMWeb": False,
                               "$policies$": {}},
                    "options": {"container": "cn=custom attributes,cn=univention," + self.ldap_base,
                                "objectType": "settings/extended_attribute",
                                "objectTemplate": "None"}}]
        try:
            request_result = self.client.umc_command('udm/add', options, "navigation").result
            if not request_result:
                utils.fail("Request 'udm/add' failed. Response: %r\nRequest options: %r\n"
                           "hostname: %r" % (request_result, options, self.hostname))
            if not request_result[0].get('success'):
                utils.fail("Request 'udm/add' not successful. Response: %r\nRequest options: %r\n"
                           "hostname: %r" % (request_result, options, self.hostname))
        except Exception as exc:
            utils.fail("Exception while making 'udm/add' request with "
                       "options '%s': '%s'" % (options, exc))

        if not self.check_attribute_exists(attribute_name):
            utils.fail("The extended attribute '%s' does not exist, after the "
                       "creation request was made" % attribute_name)

        for module in attribute_modules:
            print("Checking test module '%s' properties for the correctness "
                  "of a test attribute '%s'" % (module, attribute_name))
            if not self.check_attribute_in_module_properties(module,
                                                             attribute_name,
                                                             attribute_syntax):
                utils.fail("The test attribute '%s' was not found in the test "
                           "module '%s' properties"
                           % (attribute_name, module))

    def check_attribute_exists(self, attribute_name):
        """
        Makes a query request for all extended attributes and returns True,
        in case an attribute with a given 'attribute_name' is found.
        """
        for attribute in self.query_extended_attributes():
            if attribute.get('name') == attribute_name:
                return True

    def remove_attribute_if_exists(self, attribute_name):
        """
        Checks if attribute with a given 'attribute_name' exists
        and deletes it when exists
        """
        if self.check_attribute_exists(attribute_name):
            self.delete_obj(attribute_name, 'custom attributes', 'navigation')

    def main(self):
        """
        A method to test the UMC extended attributes creation, modification
        and module integration
        """
        self.create_connection_authenticate()
        self.ldap_base = self.ucr.get('ldap/base')

        test_username = 'umc_test_user_' + random_username(6)
        test_attribute_name = 'umc_test_attribute_' + random_username(6)
        test_attribute_module = ["users/user"]

        try:
            print("Querying extended attributes and checking the "
                  "response structure")
            self.check_attributes_query_structure()

            if self.check_attribute_exists(test_attribute_name):
                utils.fail("The extended attribute '%s' exists, before the "
                           "creation request was made" % test_attribute_name)

            print("\nCreating a test extended attribute '%s' for the module "
                  "'%s' with the default 'string' syntax"
                  % (test_attribute_name, test_attribute_module))
            self.create_check_extended_attribute(test_attribute_name,
                                                 test_attribute_module)

            print("\nCreating a test extended attribute '%s' for the module "
                  "'%s' with 'integer' syntax"
                  % (test_attribute_name + '_int', test_attribute_module))
            self.create_check_extended_attribute(test_attribute_name + '_int',
                                                 test_attribute_module,
                                                 'integer',
                                                 '1',
                                                 ldap_map="univentionFreeAttribute11")

            print("\nCreating a test extended attribute '%s' for the module "
                  "'%s' with 'TrueFalse' syntax"
                  % (test_attribute_name + '_tf', test_attribute_module))
            self.create_check_extended_attribute(test_attribute_name + '_tf',
                                                 test_attribute_module,
                                                 'TrueFalse',
                                                 'true',
                                                 ldap_map="univentionFreeAttribute12")

            print("\nCreating a test extended attribute '%s' for the module "
                  "'%s' with 'string' syntax and randomly named object class"
                  % (test_attribute_name + '_rand', test_attribute_module))
            self.create_check_extended_attribute(test_attribute_name + '_rand',
                                                 test_attribute_module,
                                                 obj_class=random_username(10),
                                                 ldap_map="univentionFreeAttribute13")

            print("\nCreating a test extended attribute '%s' for the module "
                  "'%s' with a custom syntax: 'ExampleSyntax'"
                  % (test_attribute_name + '_cust', test_attribute_module))
            self.create_check_extended_attribute(test_attribute_name + '_cust',
                                                 test_attribute_module,
                                                 "ExampleSyntax",
                                                 'value2',
                                                 ldap_map="univentionFreeAttribute14")

            test_attribute_module = ["users/user", "groups/group"]
            print("\nCreating a test extended attribute '%s' for a list of "
                  "modules '%s' at a time and with the default 'string' "
                  "syntax" % (test_attribute_name + '_multi',
                              test_attribute_module))
            self.create_check_extended_attribute(test_attribute_name + '_multi', test_attribute_module, ldap_map="univentionFreeAttribute15")

            print("\nChecking extended attribute '%s' syntax validation "
                  "with an integer value" % (test_attribute_name + '_int'))
            if not self.is_attribute_syntax_valid(test_attribute_name + '_int',
                                                  test_attribute_module[0],
                                                  "1234"):
                utils.fail("The extended attribute '%s' syntax check "
                           "with a given integer value reported '1234' as a "
                           "non-valid value" % (test_attribute_name + '_int'))

            print("\nChecking extended attribute '%s' syntax validation "
                  "with a non-integer value" % (test_attribute_name + '_int'))
            if self.is_attribute_syntax_valid(test_attribute_name + '_int',
                                              test_attribute_module[0],
                                              "This is not an Integer!"):
                utils.fail("The extended attribute '%s' syntax check "
                           "with a given non-integer value reported string "
                           "'This is not an Integer!' as a valid value"
                           % (test_attribute_name + '_int'))

            # The validation of the TrueFalse/ExampleSyntax/etc is not done,
            # since the 'udm/validate' always reports that syntax is correct
            # for any values given (Bug #35023)

            print("\nModifing and checking extended attribute '%s' short "
                  "description" % test_attribute_name)
            self.modify_check_extended_attribute(test_attribute_name,
                                                 "shortDescription",
                                                 "A modified short desc")

            with udm_test.UCSTestUDM() as UDM:
                print("\nCreating a test user '%s', modifying its custom "
                      "attribute '%s' value, checking the value before "
                      "and after the modification"
                      % (test_username, test_attribute_name + '_cust'))
                test_user_dn = UDM.create_user(password='univention',
                                               username=test_username,
                                               check_for_drs_replication=False)[0]
                utils.verify_ldap_object(test_user_dn)

                self.modify_check_user_attribute(test_user_dn,
                                                 test_attribute_name + '_cust',
                                                 'value2',
                                                 'value3')
        finally:
            print("\nRemoving created test extended attributes (if any):")
            self.remove_attribute_if_exists(test_attribute_name + '_multi')
            self.remove_attribute_if_exists(test_attribute_name + '_cust')
            self.remove_attribute_if_exists(test_attribute_name + '_rand')
            self.remove_attribute_if_exists(test_attribute_name + '_tf')
            self.remove_attribute_if_exists(test_attribute_name + '_int')
            self.remove_attribute_if_exists(test_attribute_name)


if __name__ == '__main__':
    # Since the S4 connector uses a object based synchronization,
    # it is a problem to change the same object in short intervals,
    # see https://forge.univention.org/bugzilla/show_bug.cgi?id=35336
    if utils.s4connector_present():
        atexit.register(utils.start_s4connector)
        utils.stop_s4connector()

    TestUMC = TestUMCExtendedAttributes()
    sys.exit(TestUMC.main())
