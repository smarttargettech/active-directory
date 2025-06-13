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

"""UCR module for autostart handling."""

from logging import getLogger
from subprocess import PIPE, Popen

from univention.service_info import ServiceInfo


def ctl(cmd, service):
    log = getLogger(__name__).getChild('cmd')

    cmd = ('systemctl', cmd, service)
    log.debug('Calling %r...', cmd)
    proc = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)
    out, err = proc.communicate()
    rv = proc.wait()
    if rv:
        log.error('Failed %d (%s)[%s]', rv, out.decode('UTF-8', 'replace'), err.decode('UTF-8', 'replace'))


def handler(configRegistry, changes):
    log = getLogger(__name__)

    log.debug('Loading service information...')
    si = ServiceInfo()
    for name in si.get_services():
        service = si.get_service(name)
        if not service:
            log.debug('Service not found: %s', name)
            continue

        try:
            var = service['start_type']
            unit = service.get('systemd', '%s.service' % (name,))
        except KeyError:
            log.debug('Incomplete service information: %s', service)
            continue

        if var not in changes:
            log.debug('Not changed: %s', name)
            continue

        if configRegistry.is_false(var, False):
            log.info('Disabling %s...', unit)
            ctl('disable', unit)
            ctl('mask', unit)
        elif configRegistry.get(var, '').lower() == 'manually':
            log.info('Manual %s...', unit)
            ctl('unmask', unit)
            ctl('disable', unit)
        else:
            log.info('Enabling %s...', unit)
            ctl('unmask', unit)
            ctl('enable', unit)
