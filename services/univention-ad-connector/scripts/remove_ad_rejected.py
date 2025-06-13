#!/usr/bin/python3
#
# Univention AD Connector
#  Remove rejected AD object
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


import os
import sys
from argparse import ArgumentParser

import univention.connector
import univention.uldap


class ObjectNotFound(BaseException):
    pass


def remove_ad_rejected(ad_dn):
    db_internal_file = '/etc/univention/%s/internal.sqlite' % CONFIGBASENAME
    config = univention.connector.configdb(db_internal_file)
    found = False
    for usn, rejected_dn, _retry_count in config.items('AD rejected'):
        if univention.uldap.access.compare_dn(ad_dn, rejected_dn):
            config.remove_option('AD rejected', usn)
            found = True
    os.chmod(db_internal_file, 640)
    if not found:
        raise ObjectNotFound()


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument("-c", "--configbasename", help="", metavar="CONFIGBASENAME", default="connector")
    parser.add_argument('dn')
    options = parser.parse_args()

    CONFIGBASENAME = options.configbasename
    state_directory = '/etc/univention/%s' % CONFIGBASENAME
    if not os.path.exists(state_directory):
        parser.error("Invalid configbasename, directory %s does not exist" % state_directory)

    ad_dn = options.dn

    try:
        remove_ad_rejected(ad_dn)
    except ObjectNotFound:
        print('ERROR: The object %s was not found.' % (ad_dn,))
        sys.exit(1)

    print('The rejected AD object %s has been removed.' % (ad_dn,))
