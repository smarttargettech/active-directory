#!/usr/bin/python3
#
# Univention Directory Listener
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2004-2025 Univention GmbH
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

"""Read the notifier id from the Primary Directory Node"""


import argparse
import socket
import sys


def parse_args():
    # type: () -> argparse.Namespace
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('-m', '--master', help='LDAP Server address')
    parser.add_argument(
        '-s', '--schema',
        dest='cmd',
        action='store_const',
        const='GET_SCHEMA_ID',
        default='GET_ID',
        help='Fetch LDAP Schema ID')
    parser.add_argument('arg', nargs='?', help=argparse.SUPPRESS)
    options = parser.parse_args()

    if not options.master:
        if options.arg:
            options.master = options.arg
        else:
            from univention.config_registry import ConfigRegistry
            configRegistry = ConfigRegistry()
            configRegistry.load()
            options.master = configRegistry.get('ldap/master')

    if not options.master:
        parser.error('ldap/master or --master not set')

    return options


def main():
    # type: () -> None
    """Retrieve current Univention Directory Notifier transaction ID."""
    options = parse_args()
    try:
        sock = socket.create_connection((options.master, 6669), 60.0)

        sock.send(b'Version: 3\nCapabilities: \n\n')
        sock.recv(100)

        sock.send(b'MSGID: 1\n%s\n\n' % (options.cmd.encode('UTF-8'),))
        notifier_result = sock.recv(100)

        if notifier_result:
            print("%s" % notifier_result.decode('UTF-8', 'replace').splitlines()[1])
    except OSError as ex:
        print('Error: %s' % (ex,), file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
