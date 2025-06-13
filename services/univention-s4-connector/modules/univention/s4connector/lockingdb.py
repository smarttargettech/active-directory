#!/usr/bin/python3
#
# Univention S4 Connector
#  LockingDB
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2014-2025 Univention GmbH
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


import sqlite3

import univention.debug2 as ud


class LockingDB:
    """
    A local database which includes the list of objects
    which are currently locked. That means the
    synchronisation of these objects has not been finished.
    https://forge.univention.org/bugzilla/show_bug.cgi?id=35391
    """

    def __init__(self, filename):
        self.filename = filename
        self._dbcon = sqlite3.connect(self.filename)
        self.s4cache = {}

        self.__create_tables()

    def lock_ucs(self, uuid):
        if not uuid:
            return

        # The SQLite Python module should do the escaping, that's
        # the reason why we use the tuple ? syntax.
        # I've chosen the str call because I want to make sure
        # that we use the same SQL value as before switching
        # to the tuple ? syntax
        sql_commands = [
            ("INSERT INTO UCS_LOCK(uuid) VALUES(?);", (str(uuid),)),
        ]

        self.__execute_sql_commands(sql_commands, fetch_result=False)

    def unlock_ucs(self, uuid):
        if not uuid:
            return

        sql_commands = [
            ("DELETE FROM UCS_LOCK WHERE uuid = ?;", (str(uuid),)),
        ]

        self.__execute_sql_commands(sql_commands, fetch_result=False)

    def lock_s4(self, guid):
        if not guid:
            return

        sql_commands = [
            ("INSERT INTO S4_LOCK(guid) VALUES(?);", (str(guid),)),
        ]

        self.__execute_sql_commands(sql_commands, fetch_result=False)

    def unlock_s4(self, guid):
        if not guid:
            return

        sql_commands = [
            ("DELETE FROM S4_LOCK WHERE guid = ?;", (str(guid),)),
        ]

        self.__execute_sql_commands(sql_commands, fetch_result=False)

    def is_ucs_locked(self, uuid):
        if not uuid:
            return False

        sql_commands = [
            ("SELECT id FROM UCS_LOCK WHERE uuid=?;", (str(uuid),)),
        ]

        rows = self.__execute_sql_commands(sql_commands, fetch_result=True)

        return bool(rows)

    def is_s4_locked(self, guid):
        if not guid:
            return False

        sql_commands = [
            ("SELECT id FROM S4_LOCK WHERE guid=?;", (str(guid),)),
        ]

        rows = self.__execute_sql_commands(sql_commands, fetch_result=True)

        return bool(rows)

    def __create_tables(self):
        sql_commands = [
            "CREATE TABLE IF NOT EXISTS S4_LOCK (id INTEGER PRIMARY KEY, guid TEXT);",
            "CREATE TABLE IF NOT EXISTS UCS_LOCK (id INTEGER PRIMARY KEY, uuid TEXT);",
            "CREATE INDEX IF NOT EXISTS s4_lock_guid ON s4_lock(guid);",
            "CREATE INDEX IF NOT EXISTS ucs_lock_uuid ON ucs_lock(uuid);",
        ]

        self.__execute_sql_commands(sql_commands, fetch_result=False)

    def __execute_sql_commands(self, sql_commands, fetch_result=False):
        for _i in [1, 2]:
            try:
                cur = self._dbcon.cursor()
                for sql_command in sql_commands:
                    if isinstance(sql_command, tuple):
                        ud.debug(ud.LDAP, ud.ALL, "LockingDB: Execute SQL command: %r, %r" % (sql_command[0], sql_command[1]))
                        cur.execute(sql_command[0], sql_command[1])
                    else:
                        ud.debug(ud.LDAP, ud.ALL, "LockingDB: Execute SQL command: %r" % (sql_command,))
                        cur.execute(sql_command)
                self._dbcon.commit()
                if fetch_result:
                    rows = cur.fetchall()
                cur.close()
                if fetch_result:
                    ud.debug(ud.LDAP, ud.ALL, "LockingDB: Return SQL result: %r" % (rows,))
                    return rows
                return None
            except sqlite3.Error as exp:
                ud.debug(ud.LDAP, ud.WARN, "LockingDB: sqlite: %r. SQL command was: %r" % (exp, sql_commands))
                if self._dbcon:
                    self._dbcon.close()
                self._dbcon = sqlite3.connect(self.filename)


if __name__ == '__main__':
    import random

    print('Starting LockingDB test example ')

    lock = LockingDB('lock.sqlite')

    uuid1 = random.random()
    guid1 = random.random()

    if lock.is_s4_locked(guid1):
        print('E: guid1 is locked for S4')
    if lock.is_s4_locked(uuid1):
        print('E: uuid1 is locked for S4')
    if lock.is_ucs_locked(guid1):
        print('E: guid1 is locked for UCS')
    if lock.is_ucs_locked(uuid1):
        print('E: uuid1 is locked for UCS')

    lock.lock_s4(guid1)

    if not lock.is_s4_locked(guid1):
        print('E: guid1 is not locked for S4')
    if lock.is_s4_locked(uuid1):
        print('E: uuid1 is locked for S4')
    if lock.is_ucs_locked(guid1):
        print('E: guid1 is locked for UCS')
    if lock.is_ucs_locked(uuid1):
        print('E: uuid1 is locked for UCS')

    lock.unlock_s4(guid1)

    if lock.is_s4_locked(guid1):
        print('E: guid1 is locked for S4')
    if lock.is_s4_locked(uuid1):
        print('E: uuid1 is locked for S4')
    if lock.is_ucs_locked(guid1):
        print('E: guid1 is locked for UCS')
    if lock.is_ucs_locked(uuid1):
        print('E: uuid1 is locked for UCS')

    lock.lock_ucs(uuid1)
    lock.lock_ucs(uuid1)
    lock.lock_ucs(uuid1)
    lock.lock_ucs(uuid1)
    lock.lock_ucs(uuid1)

    if lock.is_s4_locked(guid1):
        print('E: guid1 is locked for S4')
    if lock.is_s4_locked(uuid1):
        print('E: uuid1 is locked for S4')
    if lock.is_ucs_locked(guid1):
        print('E: guid1 is locked for UCS')
    if not lock.is_ucs_locked(uuid1):
        print('E: uuid1 is not locked for UCS')

    lock.unlock_ucs(uuid1)

    if lock.is_s4_locked(guid1):
        print('E: guid1 is locked for S4')
    if lock.is_s4_locked(uuid1):
        print('E: uuid1 is locked for S4')
    if lock.is_ucs_locked(guid1):
        print('E: guid1 is locked for UCS')
    if lock.is_ucs_locked(uuid1):
        print('E: uuid1 is locked for UCS')

    print('done')
