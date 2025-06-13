#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from typing import Any

from ldap import LDAPError

from univention.admin import modules
from univention.admin.uexceptions import base as UniventionBaseException
from univention.management.console.modules.setup.netconf import ChangeSet
from univention.management.console.modules.setup.netconf.common import AddressMap, LdapChange


class PhaseLdapSamba(AddressMap, LdapChange):
    """Rewrite Samba gc._msdcs host address."""

    priority = 44

    def __init__(self, changeset: ChangeSet) -> None:
        super().__init__(changeset)
        modules.update()

    def post(self) -> None:
        try:
            self.open_ldap()
            self._update_samba()
        except (LDAPError, UniventionBaseException) as ex:
            self.logger.warning("Failed LDAP: %s", ex)

    def _update_samba(self) -> None:
        forward_module = modules.get("dns/forward_zone")
        modules.init(self.ldap, self.position, forward_module)

        host_module = modules.get("dns/host_record")
        modules.init(self.ldap, self.position, host_module)

        forward_zones = forward_module.lookup(None, self.ldap, None)
        for zone in forward_zones:
            hosts = host_module.lookup(None, self.ldap, "name=gc._msdcs", superordinate=zone)
            for host in hosts:
                self._update_host(host)

    def _update_host(self, obj: Any) -> None:
        obj.open()
        try:
            old_values = set(obj.info["a"])
            new_values = {
                self.ip_mapping.get(value, value)
                for value in old_values
            }
            new_values.discard(None)
            if old_values == new_values:
                return
            obj["a"] = list(new_values)
            self.logger.info("Updating '%s' with '%r'...", obj.dn, obj.diff())
            if not self.changeset.no_act:
                obj.modify()
        except KeyError:
            pass
