#!/usr/bin/python3
#
# Univention Quota
#  Dump Quota settings into a cache directory
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2015-2025 Univention GmbH
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
import pickle  # noqa: S403

import ldap
from ldap.filter import filter_format

import univention.debug as ud
import univention.lib.policy_result
import univention.uldap

import listener


description = 'Dump quota settings into a cache directory'
filter = '(|(objectClass=univentionPolicyShareUserQuota)(objectClass=organizationalRole)(objectClass=organizationalUnit)(objectClass=univentionBase)(objectClass=univentionShare))'

'''
The listener module has to re-create the cache for one share if the share
path, the share hostname, or the policy reference has been changed at a share
object or if a quota policy has been changed or if a policy reference has
been changed at a parent object.
'''

SHARE_CACHE_DIR = '/var/cache/univention-quota/'
SHARE_CACHE_TODO_DIR = '/var/cache/univention-quota/todo'


def _dump_share_and_policy_result(dn: str, share_object: dict[str, list[bytes]], policy_result: dict[str, list[bytes]]) -> None:
    filename = os.path.join(SHARE_CACHE_DIR, dn)

    with open(filename, 'wb+') as fd:
        os.chmod(filename, 0o600)
        p = pickle.Pickler(fd)
        p.dump((dn, share_object, policy_result))
        p.clear_memo()


def _read_share_and_policy_result(dn: str) -> tuple[dict[str, list[bytes]] | None, dict[str, list[bytes]] | None]:
    filename = os.path.join(SHARE_CACHE_DIR, dn)

    if not os.path.exists(filename):
        return (None, None)

    with open(filename, 'rb') as fd:
        (_tdn, share_object, policy_result) = pickle.load(fd, encoding='bytes')

    return (share_object, policy_result)


def _remove_cache_for_share(dn: str) -> None:
    filename = os.path.join(SHARE_CACHE_DIR, dn)
    ud.debug(ud.LISTENER, ud.INFO, 'Remove "%s"' % filename)
    if os.path.exists(filename):
        os.remove(filename)


def _is_share(new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> bool:
    if new and b'univentionShare' in new['objectClass']:
        return True
    return bool(old and b'univentionShare' in old['objectClass'])


def _is_quota_policy(new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> bool:
    if new and b'univentionPolicyShareUserQuota' in new['objectClass']:
        return True
    return bool(old and b'univentionPolicyShareUserQuota' in old['objectClass'])


def _is_container(new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> bool:
    for oc in [b'organizationalRole', b'organizationalUnit', b'univentionBase']:
        if new and oc in new['objectClass']:
            return True
        if old and oc in old['objectClass']:
            return True
    return False


def _get_ldap_connection() -> univention.uldap.access:
    try:
        connection = univention.uldap.getMachineConnection(ldap_master=False)
    except ldap.SERVER_DOWN:
        connection = univention.uldap.getMachineConnection()

    return connection


def _is_container_change_relevant(new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> bool:
    new_reference = new.get('univentionPolicyReference', []) if new else []
    old_reference = old.get('univentionPolicyReference', []) if old else []

    if not old_reference and not new_reference:
        return False

    result = False

    lo = _get_ldap_connection()
    # Check if one policy is a quota policy
    for dn in old_reference + new_reference:
        ldap_object = lo.get(dn.decode('UTF-8'))
        # If the policy doesn't exist, we don't know if the policy was a quota policy
        if not ldap_object:
            result = True
            break
        if _is_quota_policy(ldap_object, {}):
            result = True
            break
    lo.lo.unbind()

    return result


def _get_fqdn() -> str:
    return '%(hostname)s.%(domainname)s' % listener.configRegistry


def _is_share_used_on_this_server(new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> bool:
    fqdn = _get_fqdn().encode('ASCII')
    if new and fqdn in new['univentionShareHost']:
        return True
    return bool(old and fqdn in old['univentionShareHost'])


def _add_all_shares_below_this_container_to_dn_list(container_dn: str) -> None:
    lo = _get_ldap_connection()
    for dn in lo.searchDn(base=container_dn, filter=filter_format('(&(objectClass=univentionShare)(univentionShareHost=%s))', [_get_fqdn()])):
        _add_share_to_dn_list(dn)
    lo.lo.unbind()


def _add_share_to_dn_list(dn: str) -> None:
    ud.debug(ud.LISTENER, ud.INFO, 'Add %s to share list' % dn)
    filename = os.path.join(SHARE_CACHE_TODO_DIR, dn)
    # Create todo file
    open(filename, 'w').close()


def _get_all_quota_references(dn: str) -> list[tuple[str, dict[str, list[bytes]]]]:
    references: list[tuple[str, dict[str, list[bytes]]]] = []
    lo = _get_ldap_connection()
    for ddn, attr in lo.search(filter=filter_format('(univentionPolicyReference=%s)', [dn])):
        references.append((ddn, attr))
    lo.lo.unbind()
    return references


def handler(dn: str, new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> None:
    ud.debug(ud.LISTENER, ud.INFO, 'Run handler for dn: %r' % dn)
    listener.setuid(0)
    try:
        if _is_share(new, old):
            ud.debug(ud.LISTENER, ud.INFO, '%r: is share' % dn)
            if _is_share_used_on_this_server(new, old):
                _add_share_to_dn_list(dn)
            ud.debug(ud.LISTENER, ud.INFO, '%r: is share (done)' % dn)

        elif _is_quota_policy(new, old):
            ud.debug(ud.LISTENER, ud.INFO, '%r: is quota policy' % dn)
            references = _get_all_quota_references(dn)
            if references:
                for ndn, attrs in references:
                    ud.debug(ud.LISTENER, ud.INFO, '%r: recursion: %r' % (dn, ndn))
                    handler(ndn, attrs, {})
            ud.debug(ud.LISTENER, ud.INFO, '%r: is quota policy (done)' % dn)

        elif _is_container(new, old):
            ud.debug(ud.LISTENER, ud.INFO, '%r: is container' % dn)
            if _is_container_change_relevant(new, old):
                _add_all_shares_below_this_container_to_dn_list(dn)
            ud.debug(ud.LISTENER, ud.INFO, '%r: is container (done)' % dn)
    finally:
        listener.unsetuid()


def clean() -> None:
    listener.setuid(0)
    try:
        if os.path.exists(SHARE_CACHE_DIR):
            for filename in os.listdir(SHARE_CACHE_DIR):
                if filename == 'todo':
                    continue
                os.remove(os.path.join(SHARE_CACHE_DIR, filename))
        if os.path.exists(SHARE_CACHE_TODO_DIR):
            for filename in os.listdir(SHARE_CACHE_TODO_DIR):
                os.remove(os.path.join(SHARE_CACHE_TODO_DIR, filename))
    finally:
        listener.unsetuid()


def postrun() -> None:
    listener.setuid(0)
    lo = None
    try:
        for dn in os.listdir(SHARE_CACHE_TODO_DIR):
            filename = os.path.join(SHARE_CACHE_TODO_DIR, dn)
            if not lo:
                lo = _get_ldap_connection()
            attrs = lo.get(dn)
            ud.debug(ud.LISTENER, ud.INFO, '%r: attrs: %r' % (dn, attrs))

            if not attrs or _get_fqdn().encode('ASCII') not in attrs.get('univentionShareHost'):
                os.remove(filename)
                _remove_cache_for_share(dn)
                continue

            policy_result = univention.lib.policy_result.policy_result(dn)[0]
            ud.debug(ud.LISTENER, ud.INFO, '%r: policy_result: %r' % (dn, policy_result))
            _dump_share_and_policy_result(dn, attrs, policy_result)

            os.remove(filename)
        if lo:
            lo.lo.unbind()
    finally:
        listener.unsetuid()
