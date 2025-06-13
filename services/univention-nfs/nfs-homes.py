#!/usr/bin/python3
#
# Univention NFS
#  listener module: create users home share path on share
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2012-2025 Univention GmbH
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

from __future__ import annotations

import os
import stat

import univention.debug as ud

import listener


hostname = listener.configRegistry["hostname"]
domainname = listener.configRegistry["domainname"]
fqdn = "%s.%s" % (hostname, domainname)

name = "nfs-homes"
description = "Create user home dirs on nfs share host"
filter = "(&(objectClass=posixAccount)(automountInformation=*))"
attributes = ["uid", "automountInformation", "gidNumber", "uidNumber"]


def handler(dn: str, new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> None:
    if not listener.configRegistry.is_true("nfs/create/homesharepath"):
        return

    # new and modify
    if new and new.get("uid"):
        uid = new.get("uid")
        uidNumber = new.get("uidNumber")
        gidNumber = new.get("gidNumber")
        automountInformation = new.get("automountInformation")

        if not uidNumber or len(uidNumber) != 1:
            return
        if not gidNumber or len(gidNumber) != 1:
            return
        if not uid or len(uid) != 1:
            return
        if not automountInformation or len(automountInformation) != 1:
            return

        uid = uid[0].decode('UTF-8')
        automountInformation = automountInformation[0].decode('ASCII')
        gidNumber = gidNumber[0].decode('ASCII')
        uidNumber = uidNumber[0].decode('ASCII')

        try:
            gidNumber = int(gidNumber)
            uidNumber = int(uidNumber)
        except ValueError:
            return

        unc = automountInformation
        if " " in automountInformation:
            _flags, unc = automountInformation.split(" ", 1)
        if ":" in unc:
            host, path = unc.split(':', 1)
            if host and host == fqdn and not os.path.exists(path):
                ud.debug(ud.LISTENER, ud.INFO, "%s: creating share path %s for user %s" % (name, path, uid))
                listener.setuid(0)
                try:
                    os.makedirs(path)
                    os.chmod(path, stat.S_IRWXU | stat.S_IXGRP | stat.S_IXOTH)
                    os.chown(path, uidNumber, gidNumber)
                except Exception as exc:
                    ud.debug(ud.LISTENER, ud.ERROR, "%s: failed to create home path %s for user %s (%s)" % (name, path, uid, exc))
                finally:
                    listener.unsetuid()
