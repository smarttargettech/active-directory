#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2022-2025 Univention GmbH
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

import os
from subprocess import PIPE, Popen

from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import Instance, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Validating the LDAP configuration and schema files.')
description = _('LDAP configuration files are valid.')


def run(_umc_instance: Instance) -> None:
    if not os.path.exists('/usr/sbin/slapschema'):
        return

    process = Popen(['/usr/sbin/slapschema', '-f', '/etc/ldap/slapd.conf'], stdout=PIPE, stderr=PIPE, env={'LANG': 'C'}, shell=True)
    _stdout, stderr_ = process.communicate()
    stderr = stderr_.decode('UTF-8', 'replace')

    if stderr:
        raise Warning(_('The LDAP schema validation failed with the following errors or warnings:\n') + stderr)


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main

    main()
