# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2004-2025 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.

"""Univention Setup: network configuration conditions"""

import os
from abc import ABCMeta
from collections.abc import Iterator

from ldap import LDAPError
from ldap.filter import filter_format

from univention.config_registry.interfaces import Interfaces
from univention.management.console.modules.setup.netconf import Phase, SkipPhase
from univention.uldap import getMachineConnection


class AddressChange(Phase, metaclass=ABCMeta):
    """Check for at least one removed or added address."""

    def check(self) -> None:
        super().check()
        old_ipv4s = {_.ip for _ in self.changeset.old_ipv4s}
        new_ipv4s = {_.ip for _ in self.changeset.new_ipv4s}
        old_ipv6s = {_.ip for _ in self.changeset.old_ipv6s}
        new_ipv6s = {_.ip for _ in self.changeset.new_ipv6s}
        if old_ipv4s == new_ipv4s and old_ipv6s == new_ipv6s:
            raise SkipPhase("No address change")


class Server(Phase, metaclass=ABCMeta):
    """Check server role for being a UCS server."""

    def check(self) -> None:
        super().check()
        role = self.changeset.ucr.get("server/role")
        if role not in (
                "domaincontroller_master",
                "domaincontroller_backup",
                "domaincontroller_slave",
                "memberserver",
        ):
            raise SkipPhase("Wrong server/role")


class Executable(Phase, metaclass=ABCMeta):
    """Check executable exists."""

    executable = ""

    def check(self) -> None:
        super().check()
        if not os.path.exists(self.executable):
            raise SkipPhase("Missing executable %s" % (self.executable,))


class Dhcp(Phase, metaclass=ABCMeta):
    """Check for interfaces using DHCP."""

    @property
    def old_dhcps(self) -> set[str]:
        return set(self._find_dhcp_interfaces(self.changeset.old_interfaces))

    @property
    def new_dhcps(self) -> set[str]:
        return set(self._find_dhcp_interfaces(self.changeset.new_interfaces))

    @staticmethod
    def _find_dhcp_interfaces(interfaces: Interfaces) -> Iterator[str]:
        for name, iface in interfaces.ipv4_interfaces:
            if iface.type in ("dhcp", "dynamic"):
                yield name


class NotNetworkOnly(Phase, metaclass=ABCMeta):
    """Skip when not in network only mode."""

    def check(self) -> None:
        super().check()
        if self.changeset.options.network_only:
            raise SkipPhase("Network only mode")


class Ldap(Phase, metaclass=ABCMeta):
    """Check LDAP server is available."""

    binddn = None
    bindpwd = None
    available = None

    def check(self) -> None:
        super().check()
        if self.available is None:
            self.load_state()
        if not self.available:
            raise SkipPhase("Missing LDAP")

    def load_state(self) -> None:
        self.check_available()
        if self.available:
            self.load_credentials()

    def check_available(self) -> None:
        self.available = not os.path.exists("/var/run/univention-system-setup.ldap")

    def load_credentials(self) -> None:
        if self.is_master_or_backup():
            self.load_admin_credentials()
        else:
            self.load_remote_credentials()

    def is_master(self) -> bool:
        role = self.changeset.ucr.get("server/role")
        return role == "domaincontroller_master"

    def is_master_or_backup(self) -> bool:
        role = self.changeset.ucr.get("server/role")
        return role in (
            "domaincontroller_master",
            "domaincontroller_backup",
        )

    def load_admin_credentials(self) -> None:
        self.binddn = "cn=admin,%(ldap/base)s" % self.changeset.ucr
        try:
            self.bindpwd = open("/etc/ldap.secret").read()
        except OSError:
            self.available = False

    def load_remote_credentials(self) -> None:
        try:
            username = self.changeset.profile["ldap_username"]
            self.bindpwd = self.changeset.profile["ldap_password"]
            self.lookup_user(username)
        except KeyError:
            self.available = False

    def lookup_user(self, username: str) -> None:
        try:
            ldap = getMachineConnection(ldap_master=True)
            ldap_filter = filter_format(
                "(&(objectClass=person)(uid=%s))",
                (username,),
            )
            result = ldap.searchDn(ldap_filter)
            self.binddn = result[0]
        except LDAPError as ex:
            self.logger.warning("Failed LDAP search for '%s': %s", username, ex)
            self.available = False
