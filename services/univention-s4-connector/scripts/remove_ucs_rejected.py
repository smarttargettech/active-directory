#!/usr/bin/python3
#
# Univention S4 Connector
#  Remove rejected UCS object
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
import sys
from argparse import ArgumentParser

import univention.s4connector
import univention.uldap


class ObjectNotFound(BaseException):
    pass


def remove_ucs_rejected(ucs_dn):
    db_internal_file = '/etc/univention/connector/s4internal.sqlite'
    config = univention.s4connector.configdb(db_internal_file)
    found = False
    for filename, rejected_dn in config.items('UCS rejected'):
        if univention.s4connector.RE_NO_RESYNC.match(rejected_dn):
            if ucs_dn != rejected_dn:
                continue
        elif not univention.uldap.access.compare_dn(ucs_dn, rejected_dn):
            continue

        if os.path.exists(filename):
            os.remove(filename)
        config.remove_option('UCS rejected', filename)
        found = True
    os.chmod(db_internal_file, 640)
    if not found:
        raise ObjectNotFound()


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('dn')
    args = parser.parse_args()

    ucs_dn = args.dn

    try:
        remove_ucs_rejected(ucs_dn)
    except ObjectNotFound:
        print('ERROR: The object %s was not found.' % ucs_dn)
        sys.exit(1)

    print('The rejected UCS object %s has been removed.' % ucs_dn)
    sys.exit(0)
