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

import re
from collections.abc import Iterator

import univention.uldap
from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import MODULE, Instance, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Check hostname RFC compliance')
description = _('No non-compliant hostnames found.')
links = [{
    'name': 'rfc1123',
    'href': _('https://tools.ietf.org/html/rfc1123#section-2'),
    'label': _('RFC 1123 - 2.1 Host Names and Numbers'),
}]

VALID_HOSTNAME = re.compile(r"^(?!-)[A-Z0-9-]{1,63}(?<!-)$", re.IGNORECASE)
run_descr = ['Checks for non-compliant hostnames. Check https://tools.ietf.org/html/rfc1123#section-2 for the syntax of hostnames']


def univention_hostnames() -> Iterator[str]:
    lo = univention.uldap.getMachineConnection()
    for (dn, attr) in lo.search('(objectClass=univentionHost)', attr=['cn']):
        if dn is not None:
            for hostname in attr.get('cn'):
                yield hostname.decode('UTF-8')


def compliant_hostname(hostname: str) -> bool:
    return bool(VALID_HOSTNAME.match(hostname))


def non_compliant_hostnames() -> Iterator[str]:
    for hostname in univention_hostnames():
        if not compliant_hostname(hostname):
            yield hostname


def run(_umc_instance: Instance) -> None:
    hostnames = list(non_compliant_hostnames())
    if hostnames:
        invalid = _('The following non-compliant hostnames have been found: {hostnames}.')
        problem = _('This may lead to DNS problems.')
        specification = _('Please refer to {rfc1123} for the syntax of host names.')
        description = [invalid.format(hostnames=', '.join(hostnames)), problem, specification]
        MODULE.error('\n'.join(description))
        raise Warning(description='\n'.join(description))


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
