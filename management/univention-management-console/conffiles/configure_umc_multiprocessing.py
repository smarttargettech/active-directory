#!/usr/bin/python3
#
# Univention Management Console
# Univention Configuration Registry Module to create systemd services for multiprocessing
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2020-2025 Univention GmbH
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
import subprocess


def handler(ucr, changes):
    processes = ucr.get_int('umc/http/processes', 1)
    if processes == 0:
        processes = os.cpu_count()

    start_port = 18200
    try:
        start_port = int(ucr.get('umc/http/processes/start-port', start_port))
    except ValueError:
        pass

    systemd_target_dir = '/etc/systemd/system/univention-management-console-server-multiprocessing.target.wants/'

    if os.path.isdir(systemd_target_dir):
        for service in os.listdir(systemd_target_dir):
            subprocess.call(['systemctl', 'disable', service])

    if processes > 1:
        for i in range(processes):
            subprocess.call(['systemctl', 'enable', f'univention-management-console-server@{i + start_port}'])
