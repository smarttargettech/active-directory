#
# Univention RADIUS
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright (C) 2012-2025 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of the software contained in this package
# as well as the source package itself are made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this package provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use the software under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.

import codecs
import logging
import os

from ldap import SERVER_DOWN
from ldap.filter import filter_format

import univention.config_registry
import univention.uldap

from .utils import decode_stationId, parse_username


SAMBA_ACCOUNT_FLAG_DISABLED = 'D'
SAMBA_ACCOUNT_FLAG_LOCKED = 'L'
DISALLOWED_SAMBA_ACCOUNT_FLAGS = frozenset((SAMBA_ACCOUNT_FLAG_DISABLED, SAMBA_ACCOUNT_FLAG_LOCKED))


def convert_network_access_attr(attributes: dict[str, list[bytes]]) -> bool:
    return b'1' in attributes.get('univentionNetworkAccess', [])


def convert_ucs_debuglevel(ucs_debuglevel: int) -> int:
    logging_debuglevel = [logging.ERROR, logging.WARNING, logging.INFO, logging.INFO, logging.DEBUG][max(0, min(4, ucs_debuglevel))]
    return logging_debuglevel


def get_ldapConnection() -> univention.uldap.access:
    try:
        # try ldap/server/name, then each of ldap/server/addition
        return univention.uldap.getMachineConnection(ldap_master=False, reconnect=False, secret_file='/etc/freeradius.secret')
    except SERVER_DOWN:
        # then primary directory node
        return univention.uldap.getMachineConnection(secret_file='/etc/freeradius.secret')


class NetworkAccessError(Exception):

    def __init__(self, msg: str) -> None:
        self.msg = msg


class UserNotAllowedError(NetworkAccessError):
    pass


class MacNotAllowedError(NetworkAccessError):
    pass


class NoHashError(NetworkAccessError):
    pass


class UserDeactivatedError(NetworkAccessError):
    pass


class NetworkAccess:

    def __init__(self, username: str, stationId: str, loglevel: int | None = None, logfile: str | None = None) -> None:
        self.username = parse_username(username)
        self.mac_address = decode_stationId(stationId)
        self.ldapConnection = get_ldapConnection()
        self.configRegistry = univention.config_registry.ConfigRegistry()
        self.configRegistry.load()
        self.use_ssp = self.configRegistry.is_true('radius/use-service-specific-password')
        self.whitelisting = self.configRegistry.is_true('radius/mac/whitelisting')
        self._setup_logger(loglevel, logfile)
        self.logger.debug('Given username: %r', username)
        self.logger.debug('Given stationId: %r', stationId)

    def _setup_logger(self, loglevel: int | None, logfile: str | None) -> None:
        if loglevel is not None:
            ucs_debuglevel = loglevel
        else:
            try:
                ucs_debuglevel = int(self.configRegistry.get('freeradius/auth/helper/ntlm/debug', '2'))
            except ValueError:
                ucs_debuglevel = 2
        debuglevel = convert_ucs_debuglevel(ucs_debuglevel)
        self.logger = logging.getLogger('radius-ntlm')
        self.logger.setLevel(debuglevel)
        if logfile is not None:
            log_handler: logging.Handler = logging.FileHandler(logfile)
            log_formatter = logging.Formatter(f'%(asctime)s - %(name)s - %(levelname)10s: [pid={os.getpid()}; user={self.username}; mac={self.mac_address}] %(message)s')
        else:
            log_handler = logging.StreamHandler()
            log_formatter = logging.Formatter(f'%(levelname)10s: [user={self.username}; mac={self.mac_address}] %(message)s')
        log_handler.setFormatter(log_formatter)
        self.logger.addHandler(log_handler)
        # self.logger.info("Loglevel set to: %s", ucs_debuglevel)

    def build_access_dict(self, ldap_result: list[tuple[str, dict[str, list[bytes]]]]) -> dict[str, bool]:
        access_dict = {
            dn: convert_network_access_attr(attributes)
            for (dn, attributes) in ldap_result
        }
        return access_dict

    def get_user_network_access(self, uid: str) -> dict[str, bool]:
        users = self.ldapConnection.search(filter=filter_format('(uid=%s)', (uid, )), attr=['univentionNetworkAccess'])
        if not users:
            users = self.ldapConnection.search(filter=filter_format('(mailPrimaryAddress=%s)', (uid, )), attr=['univentionNetworkAccess'])
        if not users:
            users = self.ldapConnection.search(filter=filter_format('(macAddress=%s)', (uid,)), attr=['univentionNetworkAccess'])
        return self.build_access_dict(users)

    def get_station_network_access(self, mac_address: str) -> dict[str, bool]:
        stations = self.ldapConnection.search(filter=filter_format('(macAddress=%s)', (mac_address, )), attr=['univentionNetworkAccess'])
        return self.build_access_dict(stations)

    def get_groups_network_access(self, dn: str) -> dict[str, bool]:
        groups = self.ldapConnection.search(filter=filter_format('(uniqueMember=%s)', (dn, )), attr=['univentionNetworkAccess'])
        return self.build_access_dict(groups)

    def evaluate_ldap_network_access(self, access: dict[str, bool], level: str = '') -> bool:
        short_circuit = not self.logger.isEnabledFor(logging.DEBUG)
        policy = any(access.values())
        if short_circuit and policy:
            return policy
        for dn, pol in access.items():
            self.logger.debug("%s%s %r", level, 'ALLOW' if pol else 'DENY', dn)
            parents_access = self.get_groups_network_access(dn)
            if self.evaluate_ldap_network_access(parents_access, level=level + '-> '):
                policy = True
                if short_circuit:
                    break
        return policy

    def check_proxy_filter_policy(self) -> bool:
        """Dummy function for UCS@school"""
        self.logger.debug('UCS@school RADIUS support is not installed')
        return False

    def check_network_access(self) -> bool:
        result = self.get_user_network_access(self.username)
        if not result:
            self.logger.info('Login attempt with unknown username')
            return False
        self.logger.debug('Checking LDAP settings for user')
        policy = self.evaluate_ldap_network_access(result)
        if policy:
            self.logger.info('Login attempt permitted by LDAP settings')
        else:
            self.logger.info('Login attempt denied by LDAP settings')
        return policy

    def check_station_whitelist(self) -> bool:
        if not self.whitelisting:
            self.logger.debug('MAC filtering is disabled by radius/mac/whitelisting.')
            return True
        self.logger.debug('Checking LDAP settings for stationId')
        if not self.mac_address:
            self.logger.info('Login attempt without MAC address, but MAC filtering is enabled.')
            return False
        result = self.get_station_network_access(self.mac_address)
        if not result:
            self.logger.info('Login attempt with unknown MAC address')
            return False
        policy = self.evaluate_ldap_network_access(result)
        if policy:
            self.logger.info('Login attempt permitted by LDAP settings')
        else:
            self.logger.info('Login attempt denied by LDAP settings')
        return policy

    def getNTPasswordHash(self) -> bytes:
        "stationId may be not supplied to the program"
        if not (self.check_proxy_filter_policy() or self.check_network_access()):
            raise UserNotAllowedError('User is not allowed to authenticate via RADIUS')
        if not self.check_station_whitelist():
            raise MacNotAllowedError('stationId is denied, because it is not whitelisted')
        # user is authorized to authenticate via RADIUS, retrieve NT-password-hash from LDAP and return it
        self.logger.info('User is allowed to use RADIUS')

        pwd_attr = 'univentionRadiusPassword' if self.use_ssp else 'sambaNTPassword'
        if '@' in self.username:
            result = self.ldapConnection.search(filter=filter_format('(mailPrimaryAddress=%s)', (self.username, )), attr=[pwd_attr, 'sambaAcctFlags'])
        else:
            result = self.ldapConnection.search(filter=filter_format('(|(uid=%s)(macAddress=%s))', (self.username, self.username)), attr=[pwd_attr, 'sambaAcctFlags'])
        try:
            nt_password_hash = codecs.decode(result[0][1][pwd_attr][0], 'hex')
        except (IndexError, KeyError, TypeError):
            raise NoHashError('No valid NT-password-hash found. Check the "%s" attribute of the user.' % (pwd_attr,))
        sambaAccountFlags = frozenset(result[0][1]['sambaAcctFlags'][0].decode('UTF-8'))
        if sambaAccountFlags & DISALLOWED_SAMBA_ACCOUNT_FLAGS:
            raise UserDeactivatedError('Account is deactivated')
        return nt_password_hash
