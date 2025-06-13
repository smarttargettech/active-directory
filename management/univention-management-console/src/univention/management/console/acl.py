#!/usr/bin/python3
#
# Univention Management Console
#  UMC ACL implementation
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2006-2025 Univention GmbH
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

r"""
UMC ACL implementation
======================

This module implements the UMC ACLs used to define the access rights for
users and groups to the UMC service.

UMC ACLs are defined by creating *UMC operation set* objects that are added
to *UMC policies*. These policies can be connected with users or
groups.

An *UMC operation set* consists of a list of UMC command patterns like

.. code-block:: none

    udm/* objectType=nagios/*

This specifies that all commands hat match the pattern `udm/\*` can be
called if the option *objectType* is given and the value matches the
pattern `nagios/\*`.

Patterns for commands and options may just use the asterik and know no
other wildcards. For options there is one additional format allowed to
specify that the option may not exist. Therefore the following format is
used

.. code-block:: none

    udm/* !objectType
"""


import itertools
import json
import operator
import os
import traceback
from fnmatch import fnmatch

import ldap
from ldap.filter import filter_format

import univention.admin.handlers.computers.domaincontroller_backup as dc_backup
import univention.admin.handlers.computers.domaincontroller_master as dc_master
import univention.admin.handlers.computers.domaincontroller_slave as dc_slave
import univention.admin.uexceptions as udm_errors
from univention.admin.handlers.computers import memberserver

from .config import ucr
from .log import ACL


class Rule(dict):  # noqa: PLW1641
    """
    A simple class representing one ACL rule in a form that can be
    simply serialized.
    """

    @property
    def fromUser(self):
        """Returns *True* if the rule was connected with a user, otherwise False"""
        return self.get('fromUser', False)

    @property
    def host(self):
        """Returns a hostname pattern. If the pattern matches the hostname the command is allowed on the host"""
        return self.get('host', '*')

    @property
    def command(self):
        """Returns the command pattern this rule describes"""
        return self.get('command', '')

    @property
    def options(self):
        """Returns the option pattern for the rule"""
        return self.get('options', {})

    @property
    def flavor(self):
        """Returns the flavor if given otherwise *None*"""
        return self.get('flavor', None)

    def __eq__(self, other):
        return self.fromUser == other.fromUser and self.host == other.host and self.command == other.command and self.flavor == other.flavor and self.options == other.options


class ACLs:
    """
    Provides methods to determine the access rights of users to
    specific UMC commands. It defines a cache for ACLs, a parser for
    command definitions of ACLs and functions for comparison.
    """

    # constants
    (MATCH_NONE, MATCH_PART, MATCH_FULL) = range(3)

    #: defines the directory for the cache files
    CACHE_DIR = '/var/cache/univention-management-console/acls'

    #: list of all supported computer types for ACL rules
    _systemroles = (dc_master, dc_backup, dc_slave, memberserver)

    def __init__(self, ldap_base=None, acls=None):
        self.__ldap_base = ldap_base
        self.acls = []
        if acls:
            self.acls = [Rule(x) for x in acls]

    def reload(self):
        self.acls = []

    def _expand_hostlist(self, lo, hostlist):
        hosts = []
        if self.__ldap_base is None:
            self.__ldap_base = ucr.get('ldap/base', None)

        for host in hostlist:
            host = host.decode('utf-8')
            if host.startswith('systemrole:'):
                role = host[len('systemrole:'):]
                if role.lower() == ucr.get('server/role').lower():
                    hosts.append(ucr['hostname'])
            elif host.startswith('service:'):
                service = host[len('service:'):]
                for role in ACLs._systemroles:
                    servers = role.lookup(None, lo, filter_format('univentionService=%s', [service]), base=self.__ldap_base)
                    for server in servers:
                        if 'name' in server:
                            hosts.append(server['name'])
            elif host == '*':
                hosts.append(ucr['hostname'])
            elif fnmatch(ucr['hostname'], host):
                hosts.append(ucr['hostname'])

        return hosts

    def __parse_command(self, command):
        data = ''
        if ':' in command:
            command, data = command.split(':', 1)
        options = {}
        if data:
            elements = data.split(',')
            for elem in elements:
                if '=' in elem:
                    key, value = elem.split('=', 1)
                    options[key.strip()] = value.strip()
                elif elem.startswith('!'):  # key without value allowed if starting with ! -> key may not exist
                    options[elem.strip()] = None
        return command, options

    def _append(self, lo, fromUser, ldap_object):
        for host in self._expand_hostlist(lo, ldap_object.get('umcOperationSetHost', [b'*'])):
            flavor = ldap_object.get('umcOperationSetFlavor', [b'*'])
            for command in ldap_object.get('umcOperationSetCommand', b''):
                command, options = self.__parse_command(command.decode('utf-8'))
                new_rule = Rule({'fromUser': fromUser, 'host': host, 'command': command, 'options': options, 'flavor': flavor[0].decode('utf-8')})
                self.acls.append(new_rule)

    def __compare_rules(self, rule1, rule2):
        """Hacky version of rule comparison"""
        if not rule1:
            return rule2
        if not rule2:
            return rule1

        if rule1.fromUser and not rule2.fromUser:
            return rule1
        elif not rule1.fromUser and rule2.fromUser:
            return rule2
        else:
            if len(rule1.command) >= len(rule2.command):
                return rule1
            else:
                return rule2

    def __option_match(self, opt_pattern, opts):
        match = ACLs.MATCH_FULL
        for key, value in opt_pattern.items():
            # a key starting with ! means it may not be available
            if key.startswith('!') and key[1:] in opts:
                return ACLs.MATCH_NONE
            # else if key not in opts no rule available -> OK
            if key not in opts:
                continue

            if isinstance(opts[key], str):
                options = (opts[key], )
            else:
                options = opts[key]
            for option in options:
                if not value.endswith('*'):
                    if value != option:
                        return ACLs.MATCH_NONE
                elif not option.startswith(value[: -1]):
                    return ACLs.MATCH_NONE

            match = ACLs.MATCH_FULL

        return match

    def __command_match(self, cmd1, cmd2):
        """
        if cmd1 == cmd2 return self.COMMAND_MATCH
        if cmd2 is part of cmd1 return self.COMMAND_PART
        if noting return self.COMMAND_NONE
        """
        if cmd1 == cmd2:
            return ACLs.MATCH_FULL

        if cmd1 and cmd1.endswith('*') and cmd2.startswith(cmd1[:-1]):
            return ACLs.MATCH_PART

        return ACLs.MATCH_NONE

    def __flavor_match(self, flavor1, flavor2):
        """
        if flavor1 == flavor2 or flavor1 is None or the pattern '*' return self.COMMAND_MATCH
        if flavor2 is part of flavor1 return self.COMMAND_PART
        if noting return self.COMMAND_NONE
        """
        if flavor1 == flavor2 or flavor1 is None or flavor1 == '*':
            return ACLs.MATCH_FULL

        if flavor1.endswith('*') and flavor2 and flavor2.startswith(flavor1[:-1]):
            return ACLs.MATCH_PART

        return ACLs.MATCH_NONE

    def _is_allowed(self, acls, command, hostname, options, flavor):
        for rule in acls:
            if hostname and rule.host not in ('*', hostname):
                continue
            match = self.__command_match(rule.command, command)
            opt_match = self.__option_match(rule.options, options)
            flavor_match = self.__flavor_match(rule.flavor, flavor)
            if match in (ACLs.MATCH_PART, ACLs.MATCH_FULL) and opt_match == ACLs.MATCH_FULL and flavor_match in (ACLs.MATCH_PART, ACLs.MATCH_FULL):
                return True

        # default is to prohibit the command execution
        return False

    def is_command_allowed(self, command, hostname=None, options={}, flavor=None):
        """
        This method verifies if the given command (with options and
        flavor) is on the named host allowed.

        :param str command: the command to check access for
        :param str hostname: FQDN of the host
        :param dict options: the command options given in the HTTP request
        :param str flavor: the flavor given in the HTTP request
        :rtype: bool
        """
        if not hostname:
            hostname = ucr['hostname']

        # first check the group rules. If the group policy allows the
        # command there is no need to check the user policy
        user_rules = [x for x in self.acls if x.fromUser]
        group_rules = [x for x in self.acls if not x.fromUser]

        return self._is_allowed(user_rules + group_rules, command, hostname, options, flavor)

    def _dump(self):
        """Dumps the ACLs for the user"""
        ACL.debug('Allowed UMC operations:')
        ACL.debug(' %-5s | %-20s | %-15s | %-20s | %-20s' % ('User', 'Host', 'Flavor', 'Command', 'Options'))
        ACL.debug('******************************************************************************')
        for rule in self.acls:
            ACL.debug(' %-5s | %-20s | %-15s | %-20s | %-20s' % (rule.fromUser, rule.host, rule.flavor, rule.command, rule.options))
        ACL.debug('')

    def _read_from_file(self, username):
        filename = os.path.join(ACLs.CACHE_DIR, username.replace('/', ''))

        try:
            with open(filename) as fd:
                acls = json.load(fd)
            acls = [Rule(x) for x in acls]
        except OSError as exc:
            ACL.process('Could not load ACLs of %r: %s' % (username, exc))
            return False

        self.acls = []
        for rule in acls:
            if rule not in self.acls:
                if 'flavor' not in rule:
                    rule['flavor'] = None
                if 'options' not in rule:
                    rule['options'] = {}
                self.acls.append(rule)

    def _write_to_file(self, username):
        filename = os.path.join(ACLs.CACHE_DIR, username.replace('/', ''))

        try:
            file = os.open(filename, os.O_WRONLY | os.O_TRUNC | os.O_CREAT, 0o600)
            os.write(file, json.dumps(self.acls, ensure_ascii=True).encode('ASCII'))
            os.close(file)
        except OSError as exc:
            ACL.error('Could not write ACL file: %s' % (exc,))
            return False

    def json(self):
        """Returns the ACL definitions in a JSON compatible form."""
        return self.acls


class LDAP_ACLs(ACLs):
    """
    Reads ACLs from LDAP directory for the given username. By
    inheriting the class :class:`ACLs` the ACL definitions can be cached
    on the local system. If the LDAP server can not be reached the cache
    is used if available.
    """

    FROM_USER = True
    FROM_GROUP = False

    def __init__(self, username, ldap_base):
        self.username = username
        ACLs.__init__(self, ldap_base)

    def reload(self, lo=None):
        super().reload()

        if lo:
            self._read_from_ldap(lo)
            self._write_to_file(self.username)
        else:
            # read ACLs from file
            self._read_from_file(self.username)

        self._dump()

    def _get_policy_for_dn(self, lo, dn):
        policy = lo.getPolicies(dn, policies=[], attrs={}, result={}, fixedattrs={})

        return policy.get('umcPolicy', None)

    def _read_from_ldap(self, lo):
        # TODO: check for fixed attributes
        try:
            userdn = lo.searchDn(filter_format('(&(objectClass=person)(uid=%s))', [self.username]), unique=True)[0]
            policy = self._get_policy_for_dn(lo, userdn)
        except (udm_errors.base, ldap.LDAPError, IndexError) as exc:
            if not isinstance(exc, IndexError):
                ACL.warn('Error reading credentials from LDAP for user %s: %s' % (self.username, traceback.format_exc()))
            # read ACLs from file
            self._read_from_file(self.username)
            return

        if policy and 'umcPolicyGrantedOperationSet' in policy:
            for value in policy['umcPolicyGrantedOperationSet']['value']:
                self._append(lo, LDAP_ACLs.FROM_USER, lo.get(value.decode('UTF-8')))

        # TODO: check for nested groups
        groupDNs = lo.searchDn(filter=filter_format('uniqueMember=%s', [userdn]))

        for gDN in groupDNs:
            policy = self._get_policy_for_dn(lo, gDN)
            if policy and 'umcPolicyGrantedOperationSet' in policy:
                for value in policy['umcPolicyGrantedOperationSet']['value']:
                    self._append(lo, LDAP_ACLs.FROM_GROUP, lo.get(value.decode('UTF-8')))

        # make the ACLs unique
        self.acls.sort(key=operator.itemgetter('fromUser', 'host', 'command', 'flavor'))

        result = []
        for _k, g in itertools.groupby(self.acls, operator.itemgetter('fromUser', 'host', 'command', 'options', 'flavor')):
            result.append(next(g))

        self.acls[:] = result
