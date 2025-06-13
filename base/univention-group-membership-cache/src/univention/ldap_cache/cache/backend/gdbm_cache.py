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
import os
from collections.abc import Iterator  # noqa: F401
from contextlib import contextmanager
from dbm import gnu as gdbm
from pwd import getpwnam

from univention.ldap_cache.cache.backend import Caches, LdapCache, Shard, _s
from univention.ldap_cache.log import debug, log


MAX_FAIL_COUNT = 5


class GdbmCaches(Caches):
    def _add_sub_cache(self, name, single_value, reverse):
        # type: (str, bool, bool) -> GdbmCache
        db_file = os.path.join(self._directory, '%s.db' % name)
        debug('Using GDBM %s', name)
        cache = GdbmCache(name, single_value, reverse)
        cache.db_file = db_file
        self._caches[name] = cache
        return cache


class GdbmCache(LdapCache):
    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        self.fail_count = 0
        super().__init__(*args, **kwargs)
        log('%s - Recreating!', self.name)

    def _fix_permissions(self):
        # type: () -> None
        listener_uid = getpwnam('listener').pw_uid
        os.chown(self.db_file, listener_uid, -1)
        os.chmod(self.db_file, 0o640)

    @contextmanager
    def writing(self, writer=None):
        # type: (Optional[Any]) -> Iterator[Any]
        if writer is not None:
            yield writer
        else:
            if not os.path.exists(self.db_file):
                self.clear()
            writer = gdbm.open(self.db_file, 'csu')
            try:
                yield writer
            finally:
                writer.close()

    reading = writing

    def save(self, key, values):
        # type: (str, List[str]) -> None
        with self.writing() as writer:
            if self.reverse:
                for value in values:
                    current = self.get(value, writer) or []
                    if key in current:
                        continue
                    debug('%s - Adding %s %r', self.name, value, key)
                    current.append(key)
                    writer[value] = json.dumps(current)
            else:
                self.delete(key, values, writer)
                if not values:
                    return
                debug('%s - Saving %s %r', self.name, key, values)
                if self.single_value:
                    writer[key] = values[0]
                else:
                    writer[key] = json.dumps(values)

    def clear(self):
        # type: () -> None
        log('%s - Clearing whole DB!', self.name)
        gdbm.open(self.db_file, 'nu').close()
        self._fix_permissions()

    def cleanup(self):
        # type: () -> None
        with self.writing() as db:
            try:
                db.reorganize()
            except gdbm.error:
                if self.fail_count > MAX_FAIL_COUNT:
                    raise
                self.fail_count += 1
                log('%s - Cleaning up DB FAILED %s times', self.name, self.fail_count)
            else:
                log('%s - Cleaning up DB WORKED', self.name)
                self.fail_count = 0
        self._fix_permissions()

    def delete(self, key, values, writer=None):
        # type: (str, List[str], Any) -> None
        debug('%s - Delete %s', self.name, key)
        with self.writing(writer) as writer:
            if self.reverse:
                for value in values:
                    current = self.get(value, writer) or []
                    try:
                        current.remove(key)
                    except ValueError:
                        continue
                    writer[value] = json.dumps(current)
            else:
                try:
                    del writer[key]
                except KeyError:
                    pass

    def keys(self):
        # type: () -> Iterator[str]
        with self.reading() as reader:
            key = _s(reader.firstkey())
            while key is not None:
                yield key
                key = _s(reader.nextkey(key))

    def __iter__(self):
        # type: () -> Iterator[Tuple[str, Any]]
        with self.reading() as reader:
            for key in self.keys():
                yield key, self.get(key, reader)

    def get(self, key, reader=None):
        # type: (str, Any) -> Any
        with self.reading(reader) as reader:
            try:
                value = reader[key]
            except KeyError:
                if self.single_value:
                    return None
                return []
            if self.single_value:
                return _s(value)
            elif value:
                return _s(json.loads(value))

    def load(self):
        # type: () -> Dict[str, Any]
        debug('%s - Loading', self.name)
        return dict(list(self))


class GdbmShard(Shard):
    key = 'dn'
