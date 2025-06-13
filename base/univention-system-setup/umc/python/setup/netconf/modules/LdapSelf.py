#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import os
from collections.abc import Iterable
from ipaddress import IPv4Interface, IPv6Interface

from ldap import LDAPError
from ldap.filter import escape_filter_chars

import univention.admin.objects
from univention.admin import modules
from univention.admin.handlers import simpleComputer
from univention.admin.uexceptions import base as UniventionBaseException
from univention.management.console.modules.setup.netconf import ChangeSet
from univention.management.console.modules.setup.netconf.common import (
    AddressMap, LdapChange, convert_udm_subnet_to_network,
)
from univention.management.console.modules.setup.netconf.conditions import Executable


class PhaseLdapSelf(AddressMap, LdapChange, Executable):
    """Rewrite IP configuration in self LDAP object."""

    priority = 40
    executable = "/usr/share/univention-directory-manager-tools/univention-dnsedit"

    def __init__(self, changeset: ChangeSet) -> None:
        super().__init__(changeset)
        self.module = None

    def post(self) -> None:
        try:
            self.open_ldap()
            self._get_module()
            for func in (self._find_computer_by_dn, self._find_computer_by_ipv4, self._find_computer_by_ipv6):
                try:
                    computer = func()
                    break
                except KeyError:
                    continue
            else:
                self.logger.warning("Failed to find self in LDAP")
                return
            self._update(computer)
        except (LDAPError, UniventionBaseException) as ex:
            self.logger.warning("Failed LDAP: %s", ex, exc_info=True)

    def _get_module(self) -> None:
        modules.update()
        module_name = "computers/%(server/role)s" % self.changeset.ucr
        self.module = modules.get(module_name)
        modules.init(self.ldap, self.position, self.module)

    def _find_computer_by_dn(self) -> simpleComputer:
        self_dn = self.changeset.ucr["ldap/hostdn"]
        return self._get_computer_at_dn(self_dn)

    def _find_computer_by_ipv4(self) -> simpleComputer:
        ldap_filter = self._build_address_filter("aRecord", self.changeset.old_ipv4s)
        return self._search_computer(ldap_filter)

    def _find_computer_by_ipv6(self) -> simpleComputer:
        ldap_filter = self._build_address_filter("aAARecord", self.changeset.old_ipv6s)
        return self._search_computer(ldap_filter)

    def _build_address_filter(self, key: str, addresses: Iterable[IPv4Interface | IPv6Interface]) -> str:
        hostname = self.changeset.ucr["hostname"]
        addr = [
            "(%s=%s)" % (key, escape_filter_chars(str(address.ip)))
            for address in addresses
        ]
        ldap_filter = "(&(cn=%s)(|%s))" % (
            escape_filter_chars(hostname),
            "".join(addr),
        )
        return ldap_filter

    def _search_computer(self, ldap_filter: str) -> simpleComputer:
        self.logger.debug("Searching '%s'...", ldap_filter)
        result = self.ldap.searchDn(ldap_filter)
        try:
            self_dn, = result
        except ValueError:
            raise KeyError(ldap_filter)
        return self._get_computer_at_dn(self_dn)

    def _get_computer_at_dn(self, dn: str) -> simpleComputer:
        computer = univention.admin.objects.get(self.module, None, self.ldap, self.position, dn)
        computer.open()
        return computer

    def _update(self, computer: simpleComputer) -> None:
        self._update_ips(computer)
        self._update_reverse_zones(computer)
        self._update_mac(computer)
        self.logger.info("Updating '%s' with '%r'...", computer.dn, computer.diff())
        if not self.changeset.no_act:
            computer.modify()

    def _update_ips(self, computer: simpleComputer) -> None:
        all_addr = [str(addr.ip) for addr in (self.changeset.new_ipv4s + self.changeset.new_ipv6s)]
        computer["ip"] = list(set(all_addr))

    def _update_reverse_zones(self, computer: simpleComputer) -> None:
        reverse_module = modules.get("dns/reverse_zone")
        modules.init(self.ldap, self.position, reverse_module)
        reverse_zones = reverse_module.lookup(None, self.ldap, None)
        for zone in reverse_zones:
            zone.open()  # may be unneeded

        computer["dnsEntryZoneReverse"] = [
                [zone.dn, str(addr.ip)]
            for zone in reverse_zones
            for addr in (self.changeset.new_ipv4s + self.changeset.new_ipv6s)
            if addr.ip in convert_udm_subnet_to_network(zone.info["subnet"])
        ]

    def _update_mac(self, computer: simpleComputer) -> None:
        macs = set()
        for name in self.changeset.new_names:
            filename = os.path.join("/sys/class/net", name, "address")
            try:
                with open(filename) as address_file:
                    mac = address_file.read().strip()
                    macs.add(mac)
            except OSError as ex:
                self.logger.warning("Could not read '%s': %s", filename, ex)
        computer["mac"] = list(macs)
