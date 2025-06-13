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

import glob
import re
import subprocess
from collections.abc import Iterator

from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import MODULE, Instance, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Check errors in sources.list files')
description = _('All files ok.')
run_descr = ['Looking for Python exceptions in /etc/apt/sources.list.d/*']

TRACEBACK_REGEX = re.compile(
    r'(?P<start>#\s+)Traceback \(most recent call last\):\n'  # start of exception
    '(?:(?P=start).*\n)+?'  # irrelevant lines of detail
    r'(?P=start)(?P<exception>[^\s].*)\n')  # extract exception


def run_ucr_commit(umc_instance: Instance) -> None:
    cmd = [
        'ucr', 'commit',
        '/etc/apt/sources.list.d/15_ucs-online-version.list',
        '/etc/apt/sources.list.d/20_ucs-online-component.list',
    ]
    subprocess.call(cmd)
    run(umc_instance, rerun=True)


actions = {
    'run_ucr_commit': run_ucr_commit,
}


class TracebackFound(Exception):
    def __init__(self, path: str, exception: str) -> None:
        super().__init__(path, exception)
        self.path = path
        self.exception = exception

    def __str__(self) -> str:
        msg = _('Found exception in {path!r}: {exception}')
        return msg.format(path=self.path, exception=self.exception)


def find_tracebacks(path: str) -> Iterator[str]:
    with open(path) as fob:
        content = fob.read()
        for match in TRACEBACK_REGEX.finditer(content):
            yield match.group('exception')


def check_for_tracebacks() -> Iterator[TracebackFound]:
    for path in glob.glob('/etc/apt/sources.list.d/*'):
        for exception in find_tracebacks(path):
            yield TracebackFound(path, exception)


def run(_umc_instance: Instance, rerun: bool = False) -> None:
    error_descriptions = [str(exc) for exc in check_for_tracebacks()]

    buttons = [{
        'action': 'run_ucr_commit',
        'label': _('Regenerate sources.list'),
    }]

    if error_descriptions:
        error_descriptions.append(_('Please check the files for more details.'))
        if not rerun:
            error_descriptions.append(_('The error might be fixable by regenerating the sources.list.'))
            MODULE.error('\n'.join(error_descriptions))
            raise Warning(description='\n'.join(error_descriptions), buttons=buttons)
        raise Warning(description='\n'.join(error_descriptions))


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
