#!/usr/share/ucs-test/runner python3
## desc: S4-connector check the mapping for single-value Samba4 attributes
## exposure: safe
## roles:
## - domaincontroller_master
## packages:
##   - univention-config
##   - univention-s4-connector
## bugs:
##   - 37259
##   - 38813

import ldap.filter

import univention.s4connector.s4
from univention.testing import utils


class S4ConnectorWrapper(univention.s4connector.s4.s4):

    def single_value_mapping_is_ok_for_s4_connector_attributes(self):
        result = True
        for key in self.property.keys():
            attributes = self.property[key].attributes
            post_attributes = self.property[key].post_attributes
            for mapping_attributes in (attributes, post_attributes):
                if not mapping_attributes:
                    continue
                for attr_key in mapping_attributes.keys():
                    con_attribute = mapping_attributes[attr_key].con_attribute

                    if con_attribute in ('description', 'ou'):
                        # These are known exceptions
                        continue

                    if self.is_single_value_in_s4(con_attribute):
                        if not mapping_attributes[attr_key].single_value and not mapping_attributes[attr_key].con_other_attribute:
                            print(f'ERROR: "{con_attribute}": Mapping for Samba4 attribute should be adjusted to single_value=True!')
                            result = False
                    else:
                        if mapping_attributes[attr_key].single_value:
                            print(f'WARN: "{con_attribute}": Mapping for Samba4 attribute should be adjusted to single_value=False.')
        return result

    def is_single_value_in_s4(self, s4_attribute):
        ldap_filter = ldap.filter.filter_format('lDAPDisplayName=%s', (s4_attribute,))
        resultlist = self._s4__search_s4(base=f'CN=Schema,CN=Configuration,{self.lo_s4.base}', scope=ldap.SCOPE_SUBTREE, filter=ldap_filter, attrlist=['isSingleValued'], show_deleted=False)
        if not resultlist:
            print("WARN: con_attribute %s not found in Samba4 schema")
            return

        if resultlist[0][1]['isSingleValued'][0] == b'TRUE':
            return True


def connect():
    s4 = S4ConnectorWrapper.main()
    s4.init_ldap_connections()

    return s4


if __name__ == '__main__':
    print("INFO: Checking if all Samba4 attributes in the S4-Connector mapping are properly declared as Single-Value")
    s4c = connect()
    if not s4c.single_value_mapping_is_ok_for_s4_connector_attributes():
        utils.fail("ERROR: Some single valued Samba4 attributes are not configured properly in the S4-Connector mapping.")
