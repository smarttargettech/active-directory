#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2021-2025 Univention GmbH
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
from collections.abc import Iterator  # noqa: F401
from contextlib import contextmanager

from univention.ldap_cache.cache import Shard
from univention.ldap_cache.log import log


CONFIG_FILE = '/usr/share/univention-group-membership-cache/shards.json'


def shards_from_config():
    # type: () -> List[Type[Shard]]
    ret = []  # type: List[Type[Shard]]
    try:
        with open(CONFIG_FILE) as fd:
            config = json.load(fd)
    except (OSError, ValueError) as exc:
        log('Could not load CONFIG_FILE: %s', exc)
    else:
        for data in config:
            try:
                class FromConfig(Shard):
                    db_name = data['db_name']
                    single_value = data['single_value']
                    reverse = data.get('reverse', False)
                    key = data['key']
                    value = data['value']
                    ldap_filter = data['ldap_filter']
                ret.append(FromConfig)
            except (TypeError, KeyError) as exc:
                log('JSON wrong: %s', exc)
    return ret


@contextmanager
def _writing_config():
    # type: () -> Iterator[Any]
    try:
        with open(CONFIG_FILE) as fd:
            shards = json.load(fd)
    except OSError:
        shards = []
    yield shards
    with open(CONFIG_FILE, 'w') as fd:
        json.dump(shards, fd, sort_keys=True, indent=4)


def add_shard_to_config(db_name, single_value, reverse, key, value, ldap_filter):
    # type: (str, bool, bool, str, str, str) -> None
    with _writing_config() as shards:
        shard_config = {
            'db_name': db_name,
            'single_value': single_value and not reverse,
            'reverse': reverse,
            'key': key,
            'value': value,
            'ldap_filter': ldap_filter,
        }
        if shard_config not in shards:
            shards.append(shard_config)


def rm_shard_from_config(db_name, single_value, reverse, key, value, ldap_filter):
    # type: (str, bool, bool, str, str, str) -> None
    with _writing_config() as shards:
        try:
            shards.remove({
                'db_name': db_name,
                'single_value': single_value and not reverse,
                'reverse': reverse,
                'key': key,
                'value': value,
                'ldap_filter': ldap_filter,
            })
        except ValueError:
            pass
