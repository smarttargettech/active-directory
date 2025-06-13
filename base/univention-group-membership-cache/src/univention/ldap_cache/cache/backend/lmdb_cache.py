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

import os
from collections.abc import Iterator  # noqa: F401
from contextlib import contextmanager
from pwd import getpwnam

import lmdb

from univention.ldap_cache.cache.backend import Caches, LdapCache, Shard


class LmdbCaches(Caches):
    def __init__(self, *args, **kwargs):
        # type: (*Any, **Any) -> None
        super().__init__(*args, **kwargs)
        self.env = lmdb.open(self._directory, 2 ** 32 - 1, max_dbs=128)
        self._fix_permissions(self._directory)

    def _fix_permissions(self, db_directory):
        # type: (str) -> None
        listener_uid = getpwnam('listener').pw_uid
        os.chown(os.path.join(db_directory, 'data.mdb'), listener_uid, -1)
        os.chown(os.path.join(db_directory, 'lock.mdb'), listener_uid, -1)
        os.chmod(os.path.join(db_directory, 'data.mdb'), 0o640)
        os.chmod(os.path.join(db_directory, 'lock.mdb'), 0o640)

    def _add_sub_cache(self, name, single_value, reverse):
        # type: (str, bool, bool) -> LmdbCache
        sub_db = self.env.open_db(name, dupsort=not single_value)
        cache = LmdbCache(name, single_value, reverse)
        cache.env = self.env
        cache.sub_db = sub_db
        self._caches[name] = cache
        return cache


class LmdbCache(LdapCache):
    @contextmanager
    def writing(self, writer=None):
        # type: (Optional[Any]) -> Iterator[Any]
        if writer is not None:
            yield writer
        else:
            with self.env.begin(self.sub_db, write=True) as writer:
                yield writer

    def save(self, key, values):
        # type: (str, List[str]) -> None
        with self.writing() as writer:
            self.delete(key, writer)
            for value in values:
                writer.put(key, value)

    def clear(self):
        # type: () -> None
        with self.env.begin(write=True) as writer:
            writer.drop(self.sub_db, delete=False)

    def cleanup(self):
        # type: () -> None
        pass

    def delete(self, key, writer=None):
        # type: (str, Any) -> None
        with self.writing(writer) as writer:
            writer.delete(key)

    @contextmanager
    def reading(self):
        # type: () -> Iterator[Any]
        with self.env.begin(self.sub_db) as txn, txn.cursor() as cursor:
            yield cursor

    def __iter__(self):
        # type: () -> Iterator[Tuple[str, Any]]
        with self.reading() as reader:
            yield from reader

    def get(self, key):
        # type: (str) -> Any
        with self.reading() as reader:
            if self.single_value:
                return reader.get(key)
            else:
                reader.set_key(key)
                return list(reader.iternext_dup())

    def load(self):
        # type: () -> Dict[str, Any]
        ret = {}  # type: Dict[str, Any]
        with self._load_key_translations() as translations, self.reading() as reader:
            for key in reader.iternext_nodup():
                translated = translations.get(key)
                if translated is None:
                    continue
                ret[translated] = self.get(key)
        return ret

    @contextmanager
    def _load_key_translations(self):
        # type: () -> Iterator[Any]
        entry_uuid_db = self.env.open_db('EntryUUID', dupsort=False)
        with self.env.begin(entry_uuid_db) as txn:
            yield txn


class LmdbShard(Shard):
    key = 'entryUUID'
