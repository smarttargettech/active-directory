#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2017-2025 Univention GmbH
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

import itertools as it
import socket
from collections.abc import Iterator
from typing import Any

import ldap.filter

import univention.admin.modules as udm_modules
import univention.admin.objects as udm_objects
import univention.admin.uldap
from univention.admin.handlers import simpleLdap
from univention.config_registry import ucr_live as ucr
from univention.lib.i18n import Translation
from univention.management.console.log import MODULE
from univention.management.console.modules.diagnostic import Instance, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Check nameserver entries on DNS zones')
description = ['All nameserver entries are ok.']
links = [{
    'name': 'sdb',
    'href': _('http://sdb.univention.de/1273'),
    'label': _('Univention Support Database - Bind: zone transfer failed'),
}]
run_descr = ['Checks nameserver entries on DNS zones']


class RecordNotFound(Exception):
    pass


class ZoneError(Exception):
    def __init__(self, nameserver: "NameServer") -> None:
        self.nameserver = nameserver

    @property
    def zone(self) -> "Zone":
        return self.nameserver.zone


class NoHostRecord(ZoneError):
    def __str__(self) -> str:
        msg = _('Found no host record (A/AAAA record) for nameserver {ns}.')
        return msg.format(ns=self.nameserver.nameserver())


class CnameAsNameServer(ZoneError):
    def __str__(self) -> str:
        msg = _('Found illegal alias record (CNAME record) for nameserver {ns}.')
        return msg.format(ns=self.nameserver.nameserver())


class Zone:
    def __init__(self, udm_zone: simpleLdap, domainname: str) -> None:
        self.udm_zone = udm_zone
        self.domainname = domainname

    @property
    def kind(self) -> str:
        return self.udm_zone.module

    @property
    def zone(self):
        if self.kind == 'dns/forward_zone':
            return self.udm_zone.get('zone')
        return self.udm_zone.get('subnet')

    def base(self) -> str:
        if self.kind == 'dns/forward_zone':
            return self.zone
        return f'{self.zone}.in-addr.arpa'

    def nameserver(self) -> Iterator:
        for nameserver in self.udm_zone.get('nameserver'):
            yield NameServer(self, nameserver)

    def umc_link(self) -> tuple[str, dict[str, Any]]:
        text = 'udm:dns/dns'
        link = {
            'module': 'udm',
            'flavor': 'dns/dns',
            'props': {
                'openObject': {
                    'objectDN': self.udm_zone.dn,
                    'objectType': self.kind,
                },
            },
        }
        return (text, link)


class NameServer:
    def __init__(self, zone: Zone, nameserver: str) -> None:
        self.zone = zone
        self._nameserver = nameserver

    def is_qualified(self) -> bool:
        return self._nameserver.endswith('.')

    def nameserver(self) -> str:
        return self._nameserver.rstrip('.')

    def fqdn(self) -> str:
        if self.is_qualified():
            return self.nameserver()
        return f'{self.nameserver()}.{self.zone.base()}'

    def is_in_zone(self) -> bool:
        return not self.is_qualified() or \
            self.nameserver().endswith(self.zone.domainname)

    def _generate_splits(self, fqdn: str) -> Iterator[tuple[str, str]]:
        zn = fqdn
        while '.' in zn and zn != self.zone.domainname:
            (rdn, zn) = zn.split('.', 1)
            if rdn and zn:
                yield (rdn, zn)

    def build_filter(self) -> str:
        template = '(&(relativeDomainName=%s)(zoneName=%s))'
        expressions = (ldap.filter.filter_format(template, (rdn, zn)) for (rdn, zn) in self._generate_splits(self.fqdn()))
        return '(|{})'.format(''.join(expressions))


class UDM:

    def __init__(self) -> None:
        univention.admin.modules.update()
        (self.ldap_connection, self.position) = univention.admin.uldap.getMachineConnection()

    def lookup(self, module_name: str, filter_expression: str = '') -> Iterator[simpleLdap]:
        module = udm_modules.get(module_name)
        for instance in module.lookup(None, self.ldap_connection, filter_expression):
            instance.open()
            yield instance

    def find(self, nameserver: NameServer) -> simpleLdap:
        filter_expression = nameserver.build_filter()
        MODULE.process("Trying to find nameserver %s in UDM/LDAP" % (nameserver.fqdn()))
        MODULE.process("Similar to running: univention-ldapsearch '%s'" % (filter_expression))
        for (dn, attr) in self.ldap_connection.search(filter_expression):
            if dn:
                for module in udm_modules.identify(dn, attr):
                    record = udm_objects.get(module, None, self.ldap_connection, self.position, dn, attr=attr, attributes=attr)
                    record.open()
                    return record
        raise RecordNotFound()

    def all_zones(self) -> Iterator[Zone]:
        domainname = ucr.get('domainname')
        for zone in self.lookup('dns/forward_zone'):
            yield Zone(zone, domainname)
        for zone in self.lookup('dns/reverse_zone'):
            yield Zone(zone, domainname)

    def check_zone(self, zone: Zone) -> Iterator[ZoneError]:
        for nameserver in zone.nameserver():
            try:
                record = self.find(nameserver)
            except RecordNotFound:
                if not nameserver.is_in_zone():
                    try:
                        socket.getaddrinfo(nameserver.fqdn(), None)
                    except socket.gaierror:
                        yield NoHostRecord(nameserver)
                else:
                    yield NoHostRecord(nameserver)

            else:
                if record.module == 'dns/alias':
                    yield CnameAsNameServer(nameserver)
                elif record.module != 'dns/host_record':
                    yield NoHostRecord(nameserver)


def find_all_zone_problems() -> Iterator[ZoneError]:
    udm = UDM()
    for zone in udm.all_zones():
        for error in udm.check_zone(zone):
            MODULE.process('Found error %s in %s' % (error, udm.check_zone(zone)))
            yield error


def run(_umc_instance: Instance) -> None:
    ed = [' '.join([
        _('Found errors in the nameserver entries of the following zones.'),
        _('Please refer to {sdb} for further information.'),
    ])]
    modules = []
    tmpl_forward = _('In forward zone {name} (see {{{link}}}):')
    tmpl_reverse = _('In reverse zone {name} (see {{{link}}}):')
    for (zone, group) in it.groupby(find_all_zone_problems(), lambda error: error.zone):
        (text, link) = zone.umc_link()
        ed.append('')
        if zone.kind == 'dns/forward_zone':
            ed.append(tmpl_forward.format(kind=zone.kind, name=zone.zone, link=text))
        elif zone.kind == 'dns/reverse_zone':
            ed.append(tmpl_reverse.format(kind=zone.kind, name=zone.zone, link=text))
        ed.extend(str(error) for error in group)
        modules.append(link)

    if modules:
        raise Warning(description='\n'.join(ed), umc_modules=modules)


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
