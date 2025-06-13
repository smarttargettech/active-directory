# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright (C) 2008-2025 Univention GmbH
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

import re
from itertools import chain
from typing import TYPE_CHECKING

import univention.ucslint.base as uub


if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


# 1) check if strings like "dc=univention,dc=qa" appear in debian/* and conffiles/*
# 2) check if strings like "univention.qa" appear in debian/* and conffiles/*


class UniventionPackageCheck(uub.UniventionPackageCheckDebian):

    def getMsgIds(self) -> uub.MsgIds:
        return {
            '0002-1': (uub.RESULT_WARN, 'cannot open file'),
            '0002-2': (uub.RESULT_ERROR, 'found basedn used in QA'),
            '0002-3': (uub.RESULT_ERROR, 'found domainname used in QA'),
        }

    def check(self, path: Path) -> None:
        super().check(path)
        self.check_files(chain(
            uub.FilteredDirWalkGenerator(path / 'conffiles'),
            uub.FilteredDirWalkGenerator(path / 'debian'),
        ))

    def check_files(self, paths: Iterable[Path]) -> None:
        tester = uub.UPCFileTester()
        tester.addTest(re.compile(r'dc=univention,dc=(?:local|qa|test)'), '0002-2', 'contains invalid basedn', cntmax=0)
        tester.addTest(re.compile(r'univention\.(?:local|qa|test)'), '0002-3', 'contains invalid domainname', cntmax=0)

        for fn in paths:
            try:
                tester.open(fn)
            except OSError:
                self.addmsg('0002-1', 'failed to open and read file', fn)
            else:
                self.msg += tester.runTests()
