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

from subprocess import PIPE, Popen

from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import Critical, Instance, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Package status corrupt')
description = '\n'.join([
    _('The package status of %s packages is corrupt.'),
    _('You may log in to the system as root via ssh and run the command "dpkg --configure -a" as an attempt to correct the packages status.'),
    _('More information about the cause can be gained by executing "dpkg --audit".'),
])

run_descr = ['This can be checked by running: dpkg --audit']


def run(_umc_instance: Instance) -> None:
    proccess = Popen(['dpkg', '--audit'], stdout=PIPE, env={'LANG': 'C'})
    stdout_, _stderr = proccess.communicate()
    stdout = stdout_.decode('UTF-8', 'replace')

    if 'The following packages' in stdout:
        num = len([line for line in stdout.splitlines() if line.startswith(' ')])
        raise Warning(description % num)

    if proccess.returncode:
        raise Critical(description % _('some'))


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
