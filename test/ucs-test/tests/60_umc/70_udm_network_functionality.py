#!/usr/share/ucs-test/runner python3
## desc: Test the UMC network functionality
## bugs: [34622]
## roles:
##  - domaincontroller_master
##  - domaincontroller_backup
## exposure: dangerous

import sys

import pytest

from univention.lib.umc import BadRequest
from univention.testing import utils
from univention.testing.strings import random_username

from umc import UDMModule


class TestUMCNetworkFunctionality(UDMModule):

    def __init__(self):
        """Test Class constructor"""
        super().__init__()
        self.ldap_base = ''
        self.test_network = ''
        self.test_network_dn = ''
        self.test_network_name = ''
        self.test_network_subnet = ''
        self.test_ip_range = []
        self.test_computer_name = ''

    def create_network(self, netmask="24", dns_forward="", dns_reverse="",
                       dhcp_entry=""):
        """
        Makes a 'udm/add' request to create a network with a
        number of given options
        """
        options = [{"object": {"dnsEntryZoneReverse": dns_reverse,
                               "netmask": netmask,
                               "dhcpEntryZone": dhcp_entry,
                               "name": self.test_network_name,
                               "dnsEntryZoneForward": dns_forward,
                               "ipRange": [self.test_ip_range],
                               "network": self.test_network,
                               "$policies$": {}},
                    "options": {"container": "cn=networks," + self.ldap_base,
                                "objectType": "networks/network"}}]

        request_result = self.request("udm/add", options, "networks/network")
        if not request_result[0].get("success"):
            utils.fail("Creation of network named %r not successful. Response: %r\nRequest options: %r"
                       % (self.test_network_name, request_result, options))
        self.test_network_dn = request_result[0].get('$dn$')

    def query_dhcp_services(self):
        """Makes a 'udm/query' request to get the DHCP services available"""
        options = {"superordinate": "None",
                   "objectType": "dhcp/dhcp",
                   "objectProperty": "None",
                   "objectPropertyValue": "",
                   "hidden": True}
        return self.request('udm/query', options, "dhcp/dhcp")

    def get_network_config(self, increase_counter=True):
        """
        Makes a 'udm/network' request to get the network configuration
        with the next free IP address
        """
        options = {"networkDN": self.test_network_dn,
                   "increaseCounter": increase_counter}
        return self.request("udm/network", options)

    def get_network_choices(self, syntax):
        """Returns result of 'udm/syntax/choices' for a given 'syntax' request."""
        options = {"syntax": syntax}
        return self.request("udm/syntax/choices", options, "computers/computer")

    def check_network_in_choices(self):
        """
        Makes a 'udm/syntax/choices' request with 'network' syntax options
        to get the networks available and returns True when network with
        a 'self.test_network_name' is found among them.
        """
        try:
            for network in self.get_network_choices("network"):
                if self.test_network_name in network['id']:
                    return True
        except KeyError as exc:
            utils.fail("KeyError exception while parsing the network "
                       "'%s' for 'id' field: '%s'" % (network, exc))

    def check_dns_dhcp_in_choices(self, syntax, name):
        """
        Makes a 'udm/syntax/chioces' request with given 'syntax'
        options to get the dns or dhcp available and returns True when
        dns/dhcp with a given 'name' is found among them.
        """
        try:
            for choice in self.get_network_choices(syntax):
                if name in choice['label']:
                    return True
        except KeyError as exc:
            utils.fail("KeyError exception while parsing the choice "
                       "'%s' for 'id' field: '%s'" % (choice, exc))

    def check_network_ip_modification(self):
        """
        Checks if the 'self.test_network_dn' has the 'self.test_ip_ranage',
        returns True in case it has.
        """
        network = self.get_object([self.test_network_dn], "networks/network")
        try:
            if self.test_ip_range in network[0]["ipRange"]:
                return True
        except KeyError as exc:
            utils.fail("KeyError exception while parsing the network for "
                       "'ipRange' field: '%s'" % exc)

    def modify_network_ip_range(self):
        """Makes a 'udm/put' request to modify network ipRange"""
        options = [{"object": {"dnsEntryZoneReverse": "",
                               "dhcpEntryZone": "",
                               "dnsEntryZoneForward": "",
                               "ipRange": [self.test_ip_range],
                               "$dn$": self.test_network_dn},
                    "options": None}]
        self.modify_object(options, "networks/network")

    def check_syntax_validation(self, netmask, ip_range, network):
        """
        Makes a 'udm/validate' request with non-valid values and
        checks if they were reported as 'valid'==false
        """
        options = {"objectType": "networks/network",
                   "properties": {"netmask": netmask,
                                  "ipRange": [ip_range],
                                  "network": network}}

        for prop in self.request('udm/validate', options, "networks/network"):
            # Workaround for answers that have lists inside:
            try:
                if True in prop.get('valid'):
                    utils.fail("The 'udm/validate' request with options '%s' "
                               "reported property '%s' as valid, when "
                               "should not" % (options, prop))
            except TypeError:
                if prop.get('valid'):
                    utils.fail("The 'udm/validate' request with options '%s' "
                               "reported property '%s' as valid, when "
                               "should not" % (options, prop))

    def check_networks_query_structure(self):
        """
        Makes a network query request and checks it for all
        default fields presence
        """
        for network in self.query_networks():
            if '$dn$' not in network:
                utils.fail("The field '$dn$' was not found in the "
                           "networks query, '%s'" % network)
            if 'name' not in network:
                utils.fail("The field 'name' was not found in the "
                           "networks query, '%s'" % network)
            if '$childs$' not in network:
                utils.fail("The field '$childs$' was not found in the "
                           "networks query, '%s'" % network)
            if 'labelObjectType' not in network:
                utils.fail("The field 'labelObjectType' was not found in the "
                           "networks query, '%s'" % network)
            if 'objectType' not in network:
                utils.fail("The field 'objectType' was not found in the "
                           "networks query, '%s'" % network)
            if 'path' not in network:
                utils.fail("The field 'path' was not found in the "
                           "networks query, '%s'" % network)

    def query_networks(self):
        """Makes a 'udm/query' request for networks and returns result"""
        options = {"container": "all",
                   "objectType": "networks/network",
                   "objectProperty": "None",
                   "objectPropertyValue": "",
                   "hidden": True}
        return self.request('udm/query', options, 'networks/network')

    def run_dns_dhcp_choices_checks(self):
        """
        Checks if the correct options are reported for 'DNS_ForwardZone'
        and 'dhcpService' configurations
        """
        domain_name = self.ucr.get('domainname')
        print("\nChecking if DNS forward zone '%s' is reported "
              "in choices for '%s' computer"
              % (domain_name, self.test_computer_name))
        if not self.check_dns_dhcp_in_choices("DNS_ForwardZone",
                                              domain_name):
            utils.fail("The '%s' was not reported as an option for DNS "
                       "forward zones for '%s' computer" % (domain_name, self.test_computer_name))

        print("\nChecking if a DHCP service is reported "
              "in choices for '%s' computer" % self.test_computer_name)
        dhcp_services = self.query_dhcp_services()
        if dhcp_services:
            dhcp_service_name = dhcp_services[0].get('name')
            if not self.check_dns_dhcp_in_choices("dhcpService",
                                                  dhcp_service_name):
                utils.fail("The '%s' was not reported as an option for DHCP "
                           "service for '%s' computer" % (dhcp_service_name, self.test_computer_name))
        else:
            print("\nCheck skipped, since no DHCP services in the "
                  "domain were found...")

    def run_address_reservation_checks(self):
        """
        Checks if ip addresses ending with .0, .1 and .254 are not
        returned as an option for computer network configuration
        """
        self.test_ip_range = [self.test_network_subnet + '.1',
                              self.test_network_subnet + '.254']
        print("\nChecking that '*.0' and '*.1' addresses are not "
              "retrieved as an option for network configuration after "
              "changing '%s' network ip range to '%s'"
              % (self.test_network_name, self.test_ip_range))
        self.modify_network_ip_range()
        network_config = self.get_network_config()
        if network_config.get('ip') in (self.test_network_subnet + '.0',
                                        self.test_network_subnet + '.1'):
            utils.fail("The '%s' network configuration reported IP: '%s' "
                       "as an option" % (self.test_network_name, network_config.get('ip')))

        self.test_ip_range = [self.test_network_subnet + '.254',
                              self.test_network_subnet + '.254']
        print("\nChecking that '*.254' address is not retrieved "
              "as an option for network configuration after "
              "changing '%s' network ip range to '%s'"
              % (self.test_network_name, self.test_ip_range))
        self.modify_network_ip_range()
        options = {"networkDN": self.test_network_dn,
                   "increaseCounter": True}
        with pytest.raises(BadRequest) as network_config:
            self.client.umc_command('udm/network', options)
        network_config = network_config.value

        error_messages = ("Fehler bei der automatischen IP Adresszuweisung",
                          "Failed to automatically assign an IP address")

        if not any(msg in network_config.message for msg in error_messages):
            utils.fail("The response message '%s' does not include any of "
                       "'%s' messages, possibly another error with the "
                       "status code 400 " % (network_config.message, error_messages))

    def run_checks_with_computers(self):
        """
        Creates a computer in a test network and after tries to create
        one more computer in the same network where no more free ip
        addresses are left
        """
        print("\nCreating a test computer '%s' in the test network '%s'"
              % (self.test_computer_name, self.test_network_name))
        if not self.check_network_in_choices():
            utils.fail("The test network '%s' was not reported as a "
                       "choice for a test computer '%s'"
                       % (self.test_network_name, self.test_computer_name))
        network_config = self.get_network_config()
        creation_result = self.create_computer(
            self.test_computer_name,
            [network_config.get('ip')],
            network_config.get('dnsEntryZoneForward'),
            network_config.get('dnsEntryZoneReverse'))
        if not creation_result[0].get("success"):
            utils.fail("Creation of a computer with a name '%s' failed, "
                       "when should not fail, no 'success'=True "
                       "in response: '%s'"
                       % (self.test_computer_name, creation_result))

        print("\nAttempting to create another test computer '%s' in the "
              "test network '%s' where no more free ip addresses are left"
              % ((self.test_computer_name + '_2'), self.test_network_name))
        creation_result = self.create_computer(
            self.test_computer_name + '_2',
            [network_config.get('ip')],
            network_config.get('dnsEntryZoneForward'),
            network_config.get('dnsEntryZoneReverse'))
        if creation_result[0].get("success"):
            utils.fail("Creation of a computer with a name '%s' "
                       "succeeded, when should not, there is "
                       "'success'=True in the response: '%s'"
                       % ((self.test_computer_name + '_2'), creation_result))
        if self.check_obj_exists(self.test_computer_name + '_2',
                                 "computers/computer"):
            utils.fail("The '%s' computer was created, while should "
                       "have not been, since there were no free ip addresses "
                       "in the '%s' network"
                       % ((self.test_computer_name + '_2'),
                          self.test_network_name))

    def run_modification_checks(self):
        """
        Creates a network for the test, modifies it and
        checks if the modification was done correctly
        """
        print("\nCreating a network for the test with a name '%s' and "
              "ip range '%s'" % (self.test_network_name, self.test_ip_range))
        self.create_network()
        if not self.check_obj_exists(self.test_network_name,
                                     "networks/network"):
            utils.fail("The test network '%s' was not created after the "
                       "creation request was made" % self.test_network_name)

        self.test_ip_range = [self.test_network_subnet + '.70',
                              self.test_network_subnet + '.70']
        print("\nModifing and checking test network '%s' ip range to '%s'"
              % (self.test_network_name, self.test_ip_range))
        self.modify_network_ip_range()
        if not self.check_network_ip_modification():
            utils.fail("The test network '%s' does not have the correct "
                       "ip range '%s' after the modification was done"
                       % (self.test_network_name, self.test_ip_range))

    def run_basic_checks(self):
        """Checks the network query structure and that syntax validation works"""
        print("Querying the networks and checking the response structure")
        self.check_networks_query_structure()

        print("\nChecking the syntax validation of network parameters")
        self.check_syntax_validation("foo", ["foo", "bar"], "foo")
        self.check_syntax_validation("12345",
                                     ["10.20.25.256", "10.20.25.257"],
                                     "12345")
        self.check_syntax_validation("256",
                                     ["10.20.256.2", "10.20.25.2"],
                                     "10.20.25.")

    def main(self):
        """A method to test the UMC network functionality"""
        self.create_connection_authenticate()
        self.ldap_base = self.ucr.get('ldap/base')

        self.test_computer_name = 'umc_test_computer_' + random_username(6)
        self.test_network_name = 'umc_test_network_' + random_username(6)
        self.test_network = self.ucr.get('interfaces/%s/network' % self.ucr.get('interfaces/primary', 'eth0'))
        self.test_network_subnet = self.test_network[:self.test_network.rfind('.')]
        self.test_ip_range = [self.test_network_subnet + '.50',
                              self.test_network_subnet + '.70']

        try:
            self.run_basic_checks()
            self.run_modification_checks()
            self.run_checks_with_computers()
            self.run_address_reservation_checks()
            self.run_dns_dhcp_choices_checks()
        finally:
            print("\nRemoving created test objects (if any):")
            if self.check_obj_exists(self.test_computer_name + '_2',
                                     "computers/computer"):
                self.delete_obj(self.test_computer_name + '_2',
                                "computers",
                                "computers/computer")
            if self.check_obj_exists(self.test_computer_name,
                                     "computers/computer"):
                self.delete_obj(self.test_computer_name,
                                "computers",
                                "computers/computer")
            if self.check_obj_exists(self.test_network_name,
                                     "networks/network"):
                self.delete_obj(self.test_network_name,
                                "networks",
                                "networks/network")


if __name__ == '__main__':
    TestUMC = TestUMCNetworkFunctionality()
    sys.exit(TestUMC.main())
