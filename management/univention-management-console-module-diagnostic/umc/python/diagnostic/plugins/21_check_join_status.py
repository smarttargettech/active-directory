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

from subprocess import PIPE, STDOUT, Popen

from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import MODULE, Critical, Instance


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Check join status')
description = _('The check for the join status was succsesful.')
links = [{
    'name': 'erroranalysis',
    'href': _('https://docs.software-univention.de/manual-5.2.html#domain:listenernotifier:erroranalysis'),
    'label': _('Manual: Analysis of listener/notifier problems'),
}]
umc_modules = [{'module': 'join'}]
run_descr = ['This can be checked by running: univention-check-join-status']


def run(_umc_instance: Instance) -> None:
    process = Popen(['univention-check-join-status'], stdout=PIPE, stderr=STDOUT)
    (stdout, stderr) = process.communicate()
    if process.returncode != 0:
        errors = [_('"univention-check-join-status" returned a problem with the domain join.')]
        if stdout:
            errors.append("\nSTDOUT:\n{}".format(stdout.decode('UTF-8', 'replace')))
        if stderr:
            errors.append("\nSTDERR:\n{}".format(stderr.decode('UTF-8', 'replace')))
        errors.append(_('See {erroranalysis} or run the join-scripts via {join}.'))
        MODULE.error('\n'.join(errors))
        raise Critical(description='\n'.join(errors))


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
