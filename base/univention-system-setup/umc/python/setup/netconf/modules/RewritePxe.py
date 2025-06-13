#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import os
import re
from ipaddress import IPv4Interface
from re import Match

from univention.management.console.modules.setup.netconf import SkipPhase
from univention.management.console.modules.setup.netconf.common import AddressMap


class Mapping:

    def __init__(self, ipv4_changes: dict[IPv4Interface, IPv4Interface]) -> None:
        self.mapping = {
            str(old_ip.ip): str(new_ip.ip)
            for (old_ip, new_ip) in ipv4_changes.items()
            if new_ip
        }
        assert self.mapping
        pattern = '''\
        (?:^|(?<![0-9]))
        (%s)
        (?:$|(?![0-9]))
        ''' % (
            '|'.join(re.escape(_) for _ in self.mapping.keys()),
        )
        self.regexp = re.compile(pattern, re.VERBOSE)

    def apply(self, string: str) -> str:
        return self.regexp.sub(self._subst, string)

    def _subst(self, match: Match[str]) -> str:
        pattern = match.group()
        return self.mapping[pattern]


class PhaseRewritePxe(AddressMap):
    """Rewrite IP configuration of PXE boot."""

    priority = 95
    dirname = "/var/lib/univention-client-boot/pxelinux.cfg"

    def check(self) -> None:
        super().check()
        if not os.path.exists(self.dirname):
            raise SkipPhase("No '%s'" % (self.dirname,))
        if not any(self.ipv4_changes().values()):
            raise SkipPhase("No IPv4 changes")

    def pre(self) -> None:
        mapping = Mapping(self.ipv4_changes())
        for filename in os.listdir(self.dirname):
            pathname = os.path.join(self.dirname, filename)
            self._rewrite_pxe(pathname, mapping)

    def _rewrite_pxe(self, pathname: str, mapping: Mapping) -> None:
        self.logger.debug("Processing '%s'...", pathname)
        with open(pathname) as read_pxe:
            orig = config = read_pxe.read()
        config = mapping.apply(orig)
        if orig == config:
            self.logger.debug("No change in %s", pathname)
            return
        self.logger.debug("Updating '%s'...", pathname)
        if self.changeset.no_act:
            return
        with open(pathname, "w") as write_pxe:
            write_pxe.write(config)
