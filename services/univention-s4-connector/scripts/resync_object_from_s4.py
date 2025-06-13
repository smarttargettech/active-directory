#!/usr/bin/python3
#
# Univention S4 Connector
#  Resync object from S4 to OpenLDAP
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


import os
import sqlite3
import sys
from argparse import ArgumentParser

import ldb
from samba.auth import system_session
from samba.credentials import Credentials
from samba.dcerpc import misc
from samba.ndr import ndr_unpack
from samba.param import LoadParm
from samba.samdb import SamDB

from univention.config_registry import ConfigRegistry


class GuidNotFound(BaseException):
    pass


class S4Resync:

    def __init__(self):
        self.configRegistry = ConfigRegistry()
        self.configRegistry.load()

        lp = LoadParm()
        creds = Credentials()
        creds.guess(lp)
        self.samdb = SamDB(url='/var/lib/samba/private/sam.ldb', session_info=system_session(), credentials=creds, lp=lp)

    def _remove_cache_entries(self, guid):
        db_cache_file = '/etc/univention/connector/s4cache.sqlite'
        cache_db = sqlite3.connect(db_cache_file)
        c = cache_db.cursor()
        c.execute("SELECT id FROM GUIDS WHERE guid=?", (str(guid),))
        guid_ids = c.fetchone()
        if guid_ids:
            guid_id = guid_ids[0]
            c.execute("DELETE from DATA where guid_id = ?", (guid_id,))
            c.execute("DELETE from GUIDS where id = ?", (guid_id,))
            cache_db.commit()
        cache_db.close()
        os.chmod(db_cache_file, 640)

    def _add_object_to_rejected(self, s4_dn, usn):
        db_internal_file = '/etc/univention/connector/s4internal.sqlite'
        db = sqlite3.connect(db_internal_file)
        c = db.cursor()
        c.execute("INSERT OR REPLACE INTO 'S4 rejected' (key, value) VALUES (?, ?);", (usn, s4_dn))
        db.commit()
        db.close()
        os.chmod(db_internal_file, 640)

    def resync(self, s4_dns=None, ldapfilter=None):
        treated_dns = []
        for s4_dn, guid, usn in self.search_samdb(s4_dns, ldapfilter):
            self._remove_cache_entries(guid)
            self._add_object_to_rejected(s4_dn, usn)
            treated_dns.append(s4_dn)

        return treated_dns

    def search_samdb(self, s4_dns=None, ldapfilter=None):
        search_result = []
        if s4_dns:
            if not ldapfilter:
                ldapfilter = '(objectClass=*)'

            error_dns = []
            missing_dns = []
            for targetdn in s4_dns:
                guid = None
                try:
                    res = self.samdb.search(targetdn, scope=ldb.SCOPE_BASE, expression=ldapfilter, attrs=["objectGuid", "uSNChanged"])

                    for msg in res:
                        guid_blob = msg.get("objectGuid", idx=0)
                        guid = ndr_unpack(misc.GUID, guid_blob)
                        usn = msg.get("uSNChanged", idx=0).decode('ASCII')
                        search_result.append((targetdn, guid, usn))
                    if not guid:
                        missing_dns.append(targetdn)
                except ldb.LdbError as ex:
                    error_dns.append((targetdn, ex.args[1]))
            if error_dns:
                raise ldb.LdbError(1, error_dns, [r[0] for r in search_result])
            if missing_dns:
                raise GuidNotFound(1, missing_dns, [r[0] for r in search_result])
        else:
            guid = None
            res = self.samdb.search(expression=ldapfilter, attrs=["objectGuid", "uSNChanged"])

            for msg in res:
                guid_blob = msg.get("objectGuid", idx=0)
                guid = ndr_unpack(misc.GUID, guid_blob)
                usn = msg.get("uSNChanged", idx=0).decode('ASCII')
                search_result.append((str(msg.dn), guid, usn))

            if not guid:
                raise GuidNotFound(2, "No match")

        return search_result


if __name__ == '__main__':
    parser = ArgumentParser(usage='resync_object_from_s4.py [--filter <LDAP filter>] [dn]')
    parser.add_argument("--filter", dest="ldapfilter", help="LDAP Filter")
    parser.add_argument('dn', nargs='?', default=None)
    options = parser.parse_args()

    if not options.dn and not options.ldapfilter:
        parser.print_help()
        sys.exit(2)

    s4_dns = list(filter(None, [options.dn]))

    treated_dns = []
    try:
        resync = S4Resync()
        treated_dns = resync.resync(s4_dns, options.ldapfilter)
    except ldb.LdbError as ex:
        print('ERROR: The S4 object was not found: %s' % (ex.args[1],))
        if len(ex.args) == 3:
            treated_dns = ex.args[2]
        sys.exit(1)
    except GuidNotFound as ex:
        print('ERROR: The S4 search for objectGUID failed: %s' % (ex.args[1],))
        if len(ex.args) == 3:
            treated_dns = ex.args[2]
        sys.exit(1)
    finally:
        for dn in treated_dns:
            print('resync triggered for %s' % dn)

    if treated_dns:
        estimated_delay = 60
        try:
            estimated_delay = int(resync.configRegistry.get('connector/s4/retryrejected', 10)) * int(resync.configRegistry.get('connector/s4/poll/sleep', 5))
        except ValueError:
            pass

        print('Estimated sync in %s seconds.' % (estimated_delay,))
    else:
        print('No matching objects.')

    sys.exit(0)
