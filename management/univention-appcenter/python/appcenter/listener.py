#!/usr/bin/python3
#
# Univention App Center
#  Listener integration
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2018-2025 Univention GmbH
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

import json
import os
import os.path
import shutil
from datetime import datetime

from ldap.filter import filter_format

from univention.appcenter.app_cache import Apps
from univention.listener.handler import ListenerModuleHandler


LISTENER_DUMP_DIR = '/var/lib/univention-appcenter/listener/'


class AppListener(ListenerModuleHandler):

    def _get_new_file_name(self):
        timestamp = datetime.now().strftime('%Y-%m-%d-%H-%M-%S-%f')
        return '%s/%s/%s.json' % (LISTENER_DUMP_DIR, self.config.get_name(), timestamp)

    def initialize(self):
        dirname = '%s/%s/' % (LISTENER_DUMP_DIR, self.config.get_name())
        try:
            with self.as_root():
                shutil.rmtree(dirname)
        except OSError:
            pass
        with self.as_root():
            os.makedirs(dirname)

    def _write_json(self, dn, obj, command, log_as=None):
        entry_uuid = obj.get('entryUUID', [None])[0]
        object_type = obj.get('univentionObjectType', [None])[0]
        attrs = {
            'entry_uuid': entry_uuid.decode('UTF-8') if entry_uuid is not None else entry_uuid,
            'dn': dn,
            'object_type': object_type.decode('UTF-8') if object_type is not None else object_type,
            'command': command,
        }
        with self.as_root():
            filename = self._get_new_file_name()
            with open(filename, 'w') as fd:
                json.dump(attrs, fd, sort_keys=True, indent=4)
            self.logger.info('%s of %s (id: %s, file: %s)' % (log_as or command, dn, entry_uuid, filename))

    def create(self, dn, new):
        self._write_json(dn, new, 'modify', log_as='create')

    def modify(self, dn, old, new, old_dn):
        self._write_json(dn, new, 'modify')

    def remove(self, dn, old):
        self._write_json(dn, old, 'delete')

    class Configuration(ListenerModuleHandler.Configuration):
        def get_description(self):
            return 'Listener module for App %s' % self.get_name()

        def get_ldap_filter(self):
            app = Apps().find(self.get_name())
            return '(|%s)' % ''.join(filter_format('(univentionObjectType=%s)', [udm_module]) for udm_module in app.listener_udm_modules)
