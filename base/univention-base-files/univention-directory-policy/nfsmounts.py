#!/usr/bin/python3
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

"""Add/remove NFS mount points from LDAP to/from /etc/fstab and mount them"""


import argparse
import os
import subprocess
import sys
from os.path import abspath, sep
from typing import IO

import ldap
from ldap.filter import filter_format

import univention.uldap
from univention.config_registry import ucr
from univention.lib import fstab
from univention.lib.policy_result import PolicyResultFailed, policy_result


verbose = False
simulate = False

MAGIC_LDAP = '#LDAP Entry DN:'


def debug(msg: str, out: IO[str] = sys.stderr) -> None:
    """Print verbose information 'msg' to 'out'."""
    if verbose:
        print(msg, file=out)


def exit(result: int, message: str | None = None) -> None:
    """Exit with optional error message."""
    script = os.path.basename(sys.argv[0])
    if message:
        print('%s: %s' % (script, message), file=sys.stderr)
    sys.exit(result)


def query_policy(host_dn: str, server: str | None = None, password_file: str = "/etc/machine.secret", verbose: bool = False) -> set[str]:
    """Get NFS shares from LDAP as per policy for dn."""
    debug('Retrieving policy for %s...\n' % (host_dn,))
    try:
        (results, _) = policy_result(dn=host_dn, binddn=host_dn, bindpw=password_file, ldap_server=server)
    except PolicyResultFailed as ex:
        if verbose:
            print('WARN: failed to execute univention_policy_result: %s' % (ex,), file=sys.stderr)
        sys.exit(1)
    return set(results.get('univentionNFSMounts', []))


def main() -> None:
    # parse command line
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dn', default=ucr['ldap/hostdn'], help=argparse.SUPPRESS)
    parser.add_argument('-s', '--simulate', action='store_true', help='simulate and show values to be set')
    parser.add_argument('-v', '--verbose', action='store_true', help='print verbose information')
    args = parser.parse_args()

    global simulate, verbose
    simulate = args.simulate
    verbose = args.verbose

    if not args.dn:
        parser.error("ldap/hostdn is not set.")
    debug("Hostdn is %s\n" % args.dn)

    to_mount = update_fstab(args, simulate)
    mount(to_mount)


def update_fstab(args: argparse.Namespace, simulate: bool) -> set[str]:
    """remove all nfs mounts from the fstab"""
    debug("Rewriting /etc/fstab...\n")
    current_fstab = fstab.File('/etc/fstab')
    to_mount = set()
    nfs_mounts = query_policy(args.dn)

    for nfs_mount in nfs_mounts:
        debug("NFS Mount: %s ..." % nfs_mount)

        data = get_nfs_data(nfs_mount, current_fstab.get())
        if data:
            dn, nfs_path_ip, mp = data
            comment = "%s %s" % (MAGIC_LDAP, dn)
            nfs_entry = current_fstab.find(comment=comment)
            if nfs_entry is not None:
                debug("\n- %s" % (nfs_entry,))
                current_fstab.remove(nfs_entry)
            nfs_entry = fstab.Entry(nfs_path_ip, mp, "nfs", comment=comment)
            current_fstab.append(nfs_entry)
            debug("\n+ %s" % (nfs_entry,))
            to_mount.add(mp)

    debug('Switching /etc/fstab...\n')
    if not simulate:
        current_fstab.save()

    # Discard already mounted
    current_mtab = fstab.File('/etc/mtab')
    to_mount.difference_update(entry.mount_point for entry in current_mtab.get('nfs'))
    return to_mount


def get_nfs_data(nfs_mount: str, entries: list[fstab.Entry]) -> tuple[str, str, str] | None:
    fields = nfs_mount.split(' ')  # dn_univentionShareNFS mount_point
    dn = fields[0]
    if not dn:
        debug('no dn, skipping\n')
        return None

    lo = univention.uldap.getMachineConnection()
    # get univention share host and path for dn
    try:
        result = lo.lo.search_s(
            dn,
            ldap.SCOPE_SUBTREE,
            'objectclass=*',
            attrlist=['univentionShareHost', 'univentionSharePath'])
    except ldap.NO_SUCH_OBJECT:
        return None

    try:
        attributes = result[0][1]
        share_host = attributes['univentionShareHost'][0].decode('ASCII')
        share_path = attributes['univentionSharePath'][0].decode('utf-8')
    except LookupError:
        debug('not found, skipping\n')
        return None

    mp = fields[-1] or share_path
    # skip share if target already in fstab
    mount_points = [entry.mount_point for entry in entries]
    if mp in mount_points:
        debug('already mounted on %s, skipping\n' % mp)
        return None

    # skip share if to self
    fqdn = "%(hostname)s.%(domainname)s" % ucr
    if share_host == fqdn and overlap(share_path, mp):
        debug('is self and %s overlaps %s, skipping\n' % (share_path, mp))
        return None

    nfs_path_fqdn = "%s:%s" % (share_host, share_path)
    # skip share if the source is already in the fstab
    sources = [entry.spec for entry in entries]
    if nfs_path_fqdn in sources:
        debug('already mounted from %s, skipping\n' % nfs_path_fqdn)
        return None

    # get the ip of the share_host
    hostname, _, domain = share_host.partition('.')
    if hostname and _ and domain:
        result = lo.lo.search_s(ucr['ldap/base'], ldap.SCOPE_SUBTREE, filter_format('(&(relativeDomainName=%s)(zoneName=%s))', (hostname, domain)), attrlist=['aRecord'])
        try:
            attributes = result[0][1]
            nfs_path_ip = "%s:%s" % (attributes['aRecord'][0].decode('ASCII'), share_path)
        except LookupError:
            nfs_path_ip = nfs_path_fqdn
    else:
        nfs_path_ip = nfs_path_fqdn

    # skip share if the source is already in the fstab
    if nfs_path_ip in sources:
        debug('already mounted from %s, skipping\n' % nfs_path_ip)
        return None

    return dn, nfs_path_ip, mp


def overlap(path_a: str, path_b: str) -> bool:
    """
    Check if two paths overlap.

    >>> overlap("/mnt/a", "/mnt/b")
    False
    >>> overlap("/mnt/a", "/mnt/aa")
    False
    >>> overlap("/mnt/a", "/mnt")
    True
    """
    return all(
        a == b
        for a, b in zip(
            abspath(path_a).split(sep),
            abspath(path_b).split(sep),
        )
    )


def mount(to_mount: set[str]) -> None:
    """mount new NFS filesystems"""
    for mp in sorted(to_mount):
        if not os.path.exists(mp):
            os.makedirs(mp)
        debug('Mounting %s...\n' % mp)
        if not simulate:
            subprocess.call(['mount', mp])


if __name__ == '__main__':
    main()
