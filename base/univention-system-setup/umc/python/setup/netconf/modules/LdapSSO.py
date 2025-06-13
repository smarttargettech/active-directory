#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from urllib.parse import urlparse

from ldap import LDAPError
from ldap.filter import filter_format

from univention.admin import modules
from univention.admin.handlers import simpleLdap
from univention.admin.uexceptions import base as UniventionBaseException
from univention.management.console.modules.setup.netconf import ChangeSet
from univention.management.console.modules.setup.netconf.common import AddressMap, LdapChange


class PhaseLdapSSO(AddressMap, LdapChange):
    """Rewrite UCS SSO host address."""

    priority = 49

    def __init__(self, changeset: ChangeSet) -> None:
        super().__init__(changeset)
        modules.update()

    def post(self) -> None:
        try:
            if self.changeset.ucr.is_true('ucs/server/sso/autoregistraton', True):
                self.open_ldap()
                self._update_sso()
        except (LDAPError, UniventionBaseException) as ex:
            self.logger.warning("Failed LDAP: %s", ex)

    def _update_sso(self) -> None:
        forward_module = modules.get("dns/forward_zone")
        modules.init(self.ldap, self.position, forward_module)

        host_module = modules.get("dns/host_record")
        modules.init(self.ldap, self.position, host_module)

        sso_uri = self.changeset.ucr.get('ucs/server/sso/uri')
        sso_fqdn = urlparse(sso_uri).netloc
        forward_zones = forward_module.lookup(None, self.ldap, None)
        for forward_zone in forward_zones:
            zone = forward_zone.get('zone')
            if not sso_fqdn.endswith(zone):
                continue
            sso_name = sso_fqdn[:-(len(zone) + 1)]
            hosts = host_module.lookup(None, self.ldap, filter_format("relativeDomainName=%s", (sso_name,)), superordinate=forward_zone)
            for host in hosts:
                self._update_host(host)

    def _update_host(self, obj: simpleLdap) -> None:
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
