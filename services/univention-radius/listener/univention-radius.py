#!/usr/bin/python3
#
# Univention RADIUS
#  Listener integration
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2019-2025 Univention GmbH
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
#

import subprocess

from univention.listener.handler import ListenerModuleHandler


class AppListener(ListenerModuleHandler):
    run_update = False

    class Configuration(ListenerModuleHandler.Configuration):
        description = 'Listener module for univention-radius'
        ldap_filter = '(objectClass=univentionHost)'

    def create(self, dn: str, new: dict[str, list[bytes]]) -> None:
        if b'univentionRadiusClient' in new.get('objectClass', []):
            self.run_update = True
            self.logger.info('config update triggered')

    def modify(self, dn: str, old: dict[str, list[bytes]], new: dict[str, list[bytes]], old_dn: str | None) -> None:
        # only update the file, if relevant
        if old_dn:
            self.run_update = True
            self.logger.info('config update triggered (move)')
        elif (b'univentionRadiusClient' in old.get('objectClass', []) or b'univentionRadiusClient' in new.get('objectClass', [])) and (  # noqa: PLR0916
            set(old.get('univentionRadiusClientSharedSecret', [])) != set(new.get('univentionRadiusClientSharedSecret', []))
            or set(old.get('univentionRadiusClientType', [])) != set(new.get('univentionRadiusClientType', []))
            or set(old.get('univentionRadiusClientVirtualServer', [])) != set(new.get('univentionRadiusClientVirtualServer', []))
            or set(old.get('aRecord', [])) != set(new.get('aRecord', []))
            or set(old.get('aAAARecord', [])) != set(new.get('aAAARecord', []))
        ):
            self.run_update = True
            self.logger.info('config update triggered')

    def remove(self, dn: str, old: dict[str, list[bytes]]) -> None:
        if b'univentionRadiusClient' in old.get('objectClass', []):
            self.run_update = True
            self.logger.info('config update triggered')

    def post_run(self) -> None:
        if self.run_update:
            self.run_update = False
            with self.as_root():
                self.logger.info('Updating clients.univention.conf')
                subprocess.call(['/usr/sbin/univention-radius-update-clients-conf'])
                self.logger.info('Restarting freeradius')
                subprocess.call(['systemctl', 'try-restart', 'freeradius'])
