#!/usr/bin/python3
#
# Univention Management Console
#  module: software management
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2024-2025 Univention GmbH
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

import json

from univention.appcenter.actions import UniventionAppAction, get_action


class UmcGenerateAppCache(UniventionAppAction):

    help = 'Generates the app cache /var/cache/univention-appcenter/umc-query.json'
    CACHE_FILE = '/var/cache/univention-appcenter/umc-query.json'

    def main(self, args=None):
        self.generate()

    @classmethod
    def generate(cls):
        list_apps = get_action('list')
        domain = get_action('domain')
        apps = list_apps.get_apps()
        info = domain.to_dict(apps)
        with open(cls.CACHE_FILE, 'w') as fd:
            json.dump(info, fd)
        return info

    @classmethod
    def load(cls):
        try:
            with open(cls.CACHE_FILE) as fd:
                return json.load(fd)
        except (OSError, ValueError) as exc:
            cls.warn('Error returning cached query: %s' % exc)
            return []
