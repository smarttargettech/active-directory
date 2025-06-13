#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2016-2025 Univention GmbH
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

from collections.abc import Iterator

import univention.uldap
from univention.config_registry import ucr_live as configRegistry
from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import MODULE, Critical, Instance, Warning, util  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('S4 Connector rejects')
description = _('No S4 Connector rejects were found.')
links = [{
    'name': 'sdb',
    'href': 'https://help.univention.com/t/how-to-deal-with-s4-connector-rejects/33',
    'label': _('Univention Support Database - How to deal with s4-connector rejects'),
}]
run_descr = ['Checking S4-Connector rejects. Similar to running: univention-s4connector-list-rejected']


class MissingConfigurationKey(KeyError):
    @property
    def variable(self) -> str:
        return self.args[0]

    def __str__(self) -> str:
        return f'{self.__class__.__name__}: {super().__str__()}'


def get_s4_connector(configbasename: str = 'connector'):
    try:
        s4 = univention.s4connector.s4.s4.main(configRegistry, configbasename)
    except SystemExit as error:
        MODULE.error('Missing Configuration key %s' % (error,))
        raise MissingConfigurationKey(error.code)
    else:
        s4.init_ldap_connections()
        return s4


def get_ucs_rejected(s4) -> Iterator[tuple[str, str, str]]:
    for (filename, dn) in s4.list_rejected_ucs():
        s4_dn = s4.get_dn_by_ucs(dn)
        yield (filename, dn.strip(), s4_dn.strip())


def get_s4_rejected(s4) -> Iterator[tuple[object, str, str]]:
    for (s4_id, dn) in s4.list_rejected():
        ucs_dn = s4.get_dn_by_con(dn)
        yield (s4_id, dn.strip(), ucs_dn.strip())


def run(_umc_instance: Instance) -> None:
    if not util.is_service_active('S4 Connector'):
        return

    try:
        import univention.s4connector
        import univention.s4connector.s4  # noqa: F401
    except ImportError:
        error_description = _('Univention S4 Connector is not installed.')
        raise Critical(description=error_description)

    try:
        s4 = get_s4_connector()
    except MissingConfigurationKey as error:
        error_description = _('The UCR variable {variable!r} is unset, but necessary for the S4 Connector.').format(variable=error.variable)
        MODULE.error(error_description)
        raise Critical(description=error_description)

    ucs_rejects = list(get_ucs_rejected(s4))
    s4_rejects = list(get_s4_rejected(s4))

    if ucs_rejects or s4_rejects:
        error_description = _('Found {ucs} UCS rejects and {s4} S4 rejects. See {{sdb}} for more information.')
        error_description = error_description.format(ucs=len(ucs_rejects), s4=len(s4_rejects))
        error_descriptions = [error_description]
        if ucs_rejects:
            error_descriptions.append(_('UCS rejected:'))
            for (filename, ucs_dn, s4_dn) in ucs_rejects:
                s4_dn = s4_dn or _('not found')
                line = _('UCS DN: {ucs}, S4 DN: {s4}, Filename: {fn}')
                line = line.format(ucs=ucs_dn, s4=s4_dn, fn=filename)
                error_descriptions.append(line)
        if s4_rejects:
            error_descriptions.append(_('S4 rejected:'))
            for (_s4_id, s4_dn, ucs_dn) in s4_rejects:
                ucs_dn = ucs_dn or _('not found')
                line = _('S4 DN: {s4}, UCS DN: {ucs}')
                line = line.format(s4=s4_dn, ucs=ucs_dn)
                error_descriptions.append(line)
        MODULE.error('\n'.join(error_descriptions))
        raise Warning(description='\n'.join(error_descriptions))


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
