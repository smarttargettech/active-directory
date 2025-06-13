#!/usr/bin/python3
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

"""Univention Common Python Library"""

import subprocess
from typing import Optional  # noqa: F401

from univention.config_registry import ConfigRegistry
from univention.lib.ucs import UCS_Version
from univention.uldap import getMachineConnection


def primaryVersionGreaterEqual(version):
    # type: (str) -> bool
    """
    Returns True if UCS_Version of primary is greater or equal to given version.

    :param UCS_Version version: the UCS version to check
    :returns: True if UCS version of primary is greater or equal version
    :rtype: bool
    """
    version = UCS_Version(version)
    lo = getMachineConnection()
    # TODO: is this enough to search for the primary, or do we need cn=ucr[ldap/master]?
    res = lo.search('univentionObjectType=computers/domaincontroller_master')
    if len(res) != 1:
        return False
    primary_version = res[0][1].get('univentionOperatingSystemVersion')
    if not primary_version:
        return False
    primary_version = UCS_Version(primary_version[0].decode('UTF-8'))
    return primary_version >= version


def createMachinePassword():
    # type: () -> str
    """
    Returns a $(pwgen) generated password according to the
    requirements in |UCR| variables
    `machine/password/length` and `machine/password/complexity`.

    :returns: A password.
    :rtype: str
    """
    ucr = ConfigRegistry()
    ucr.load()
    length = ucr.get('machine/password/length', '20')
    compl = ucr.get('machine/password/complexity', 'scn')
    p = subprocess.Popen(["pwgen", "-1", "-" + compl, length], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    (stdout, _stderr) = p.communicate()
    if not isinstance(stdout, str):  # Python 3
        return stdout.decode('ASCII', 'replace').strip()
    return stdout.strip()


def getLDAPURIs(ucr=None, sep=' '):
    # type: (Optional[ConfigRegistry], str) -> str
    """
    Returns a space separated list of all configured |LDAP| servers, according to |UCR| variables
    `ldap/server/name` and `ldap/server/addition`.

    :param ConfigRegistry ucr: An optional |UCR| instance.
    :returns: A space separated list of |LDAP| |URI|.
    :rtype: str
    """
    if ucr is None:
        ucr = ConfigRegistry()
        ucr.load()

    uri_string = ''
    ldaphosts = []
    port = ucr.get('ldap/server/port', '7389')
    ldap_server_name = ucr.get('ldap/server/name')
    ldap_server_addition = ucr.get('ldap/server/addition')

    if ldap_server_name:
        ldaphosts.append(ldap_server_name)
    if ldap_server_addition:
        ldaphosts.extend(ldap_server_addition.split())
    if ldaphosts:
        urilist = ["ldap://%s:%s" % (host, port) for host in ldaphosts]
        uri_string = sep.join(urilist)

    return uri_string


def getLDAPServersCommaList(ucr=None):
    # type: (Optional[ConfigRegistry]) -> str
    """
    Returns a comma-separated string with all configured |LDAP| servers,
    `ldap/server/name` and `ldap/server/addition`.

    :param ConfigRegistry ucr: An optional |UCR| instance.
    :returns: A space separated list of |LDAP| host names.
    :rtype: str
    """
    if ucr is None:
        ucr = ConfigRegistry()
        ucr.load()

    ldap_servers = ''
    ldaphosts = []
    ldap_server_name = ucr.get('ldap/server/name')
    ldap_server_addition = ucr.get('ldap/server/addition')

    if ldap_server_name:
        ldaphosts.append(ldap_server_name)
    if ldap_server_addition:
        ldaphosts.extend(ldap_server_addition.split())
    if ldaphosts:
        ldap_servers = ','.join(ldaphosts)

    return ldap_servers


def custom_username(name, ucr=None):
    # type: (str, Optional[ConfigRegistry]) -> str
    """
    Returns the customized user name configured via |UCR| `users/default/*`.

    :param str name: A user name.
    :param ConfigRegistry ucr: An optional |UCR| instance.
    :returns: The translated user name.
    :rtype: str
    :raises ValueError: if no name is given.
    """
    if not name:
        raise ValueError()

    if ucr is None:
        ucr = ConfigRegistry()
        ucr.load()

    return ucr.get("users/default/" + name.lower().replace(" ", ""), name)


def custom_groupname(name, ucr=None):
    # type: (str, Optional[ConfigRegistry]) -> str
    """
    Returns the customized group name configured via |UCR| `groups/default/*`.

    :param str name: A group name.
    :param ConfigRegistry ucr: An optional |UCR| instance.
    :returns: The translated group name.
    :rtype: str
    :raises ValueError: if no name is given.
    """
    if not name:
        raise ValueError()

    if ucr is None:
        ucr = ConfigRegistry()
        ucr.load()

    return ucr.get("groups/default/" + name.lower().replace(" ", ""), name)
