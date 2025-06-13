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
from enum import IntFlag
from itertools import chain
from typing import TYPE_CHECKING

import univention.ucslint.base as uub


if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path


class JSS(IntFlag):
    UNREF = 0
    CALLED = 1
    COPIED = 2


class UniventionPackageCheck(uub.UniventionPackageCheckDebian):

    def getMsgIds(self) -> uub.MsgIds:
        return {
            '0001-1': (uub.RESULT_STYLE, 'the old command "univention-admin" is used'),
            '0001-2': (uub.RESULT_ERROR, '"$@" for passing credentials to univention-directory-manager is missing'),
            '0001-3': (uub.RESULT_WARN, 'join scripts are now versioned - the variable VERSION is not set'),
            '0001-4': (uub.RESULT_WARN, 'join scripts are now versioned - the string " v${VERSION} " within grep/echo is missing'),
            '0001-5': (uub.RESULT_ERROR, 'debian/rules is missing'),
            '0001-6': (uub.RESULT_WARN, 'join script seems not to be installed via debian/rules'),
            '0001-7': (uub.RESULT_WARN, 'join script seems not to be called in any postinst file'),
            '0001-8': (uub.RESULT_WARN, 'join scripts should be called with "|| true" do avoid failing postinst scripts if "set -e" is used'),
            '0001-9': (uub.RESULT_WARN, 'cannot open specified file'),
            '0001-10': (uub.RESULT_ERROR, 'join script contains "eval $(ucr shell)" without proper quoting'),  # unused, moved to 0017
            '0001-11': (uub.RESULT_ERROR, 'join script contains lines with unquoted $@'),
            '0001-12': (uub.RESULT_ERROR, 'join script contains more than one line with VERSION=  statement'),
            '0001-13': (uub.RESULT_ERROR, 'join script does not include "joinscripthelper.lib"'),
            '0001-14': (uub.RESULT_ERROR, 'join script does not call "joinscript_init"'),
            '0001-15': (uub.RESULT_ERROR, 'join script does not call "joinscript_save_current_version"'),
            '0001-17': (uub.RESULT_WARN, 'unjoin script seems not to be called in any postrm file'),
            '0001-18': (uub.RESULT_WARN, 'unjoin script seems not to be copied in any prerm file'),
            '0001-19': (uub.RESULT_ERROR, 'unjoin script must not call "joinscript_save_current_version"'),
            '0001-20': (uub.RESULT_ERROR, 'unjoin script does not call "joinscript_remove_script_from_status_file"'),
            '0001-21': (uub.RESULT_WARN, 'unjoin script does not call "joinscript_init"'),
            '0001-22': (uub.RESULT_ERROR, '"dh --with univention-join" is used in "debian/rules" without "Build-Depends: univention-join-dev" in "debian/rules"'),
            '0001-23': (uub.RESULT_STYLE, 'Consider switchting to "univention-join" debhelper sequence'),
            '0001-24': (uub.RESULT_ERROR, 'Invalid joinscript api'),
        }

    RE_LINE_ENDS_WITH_TRUE = re.compile(r'\|\|[ \t]+true[ \t]*$')
    RE_LINE_CONTAINS_SET_E = re.compile(r'\n[\t ]*set -e', re.M)
    RE_DH_UMC = re.compile(r'\bdh-umc-module-install\b|\bdh\b.*--with\b.*\bumc\b')
    RE_DH_JOIN = re.compile(r'(?P<old>\bunivention-install-joinscript\b)|\bdh\b.*--with\b.*\bunivention-join\b')
    RE_JOIN_API = re.compile(r'^## joinscript api: (?!bindpwdfile|nocredentials)(.*)')

    def check_join_script(self, filename: Path) -> None:
        """Check a single join script."""
        try:
            with filename.open() as fd:
                content = fd.read()
        except OSError:
            self.addmsg('0001-9', 'failed to open and read file', filename)
            return

        self.debug(f'checking {filename}')

        is_uninstall = filename.suffix == '.uinst'
        lines = content.splitlines()
        cnt = {
            'version': 0,
            'vversion': 0,
            'joinscripthelper.lib': 0,
            'joinscript_init': 0,
            'joinscript_save_current_version': 0,
            'joinscript_remove_script_from_status_file': 0,
        }
        for row, line in enumerate(lines, start=1):
            line = line.strip()

            # check joinscript api
            match = self.RE_JOIN_API.match(line)
            if match:
                self.addmsg('0001-24', f'Invalid joinscript api {match[1]!r}', filename, row, line=line)

            if not line or line.startswith('#'):
                continue

            # check for old style joinscript
            if line.startswith('VERSION='):
                cnt['version'] += 1
                if cnt['version'] > 1:
                    self.addmsg('0001-12', 'join script does set VERSION more than once', filename, row, line=line)
            if line.find(' v${VERSION} ') >= 0:
                cnt['vversion'] += 1

            # check for new style joinscript
            if line.startswith(('source /usr/share/univention-join/joinscripthelper.lib', '. /usr/share/univention-join/joinscripthelper.lib')):
                cnt['joinscripthelper.lib'] += 1
            if 'joinscript_init' in line:
                cnt['joinscript_init'] += 1
            if 'joinscript_save_current_version' in line:
                cnt['joinscript_save_current_version'] += 1
            if 'joinscript_remove_script_from_status_file' in line:
                cnt['joinscript_remove_script_from_status_file'] += 1

            # check udm calls
            if 'univention-admin ' in line or 'univention-directory-manager ' in line or 'udm ' in line:
                if 'univention-admin ' in line:
                    self.addmsg('0001-1', 'join script still uses "univention-admin"', filename, row, line=line)

                if ' $@ ' not in line and ' "$@" ' not in line and ' "${@}" ' not in line:
                    self.addmsg('0001-2', 'join script is missing "$@"', filename, row, line=line)

            if ' $@ ' in line or ' ${@} ' in line:
                self.addmsg('0001-11', 'join script contains unquoted $@', filename, row, line=line)

        if cnt['version'] == 0:
            self.addmsg('0001-3', 'join script does not set VERSION', filename)

        if not cnt['joinscripthelper.lib']:
            # no usage of joinscripthelper.lib
            if cnt['vversion'] > 0 and cnt['vversion'] < 2:
                self.addmsg('0001-4', 'join script does not grep for " v${VERSION} "', filename)
            elif cnt['vversion'] == 0:
                self.addmsg('0001-13', 'join script does not use joinscripthelper.lib', filename)
        else:
            if is_uninstall:
                if not cnt['joinscript_init']:
                    self.addmsg('0001-21', 'unjoin script does not call "joinscript_init"', filename)
                if cnt['joinscript_save_current_version']:
                    self.addmsg('0001-19', 'unjoin script must not use joinscript_save_current_version', filename)
                if not cnt['joinscript_remove_script_from_status_file']:
                    self.addmsg('0001-20', 'unjoin script does not call "joinscript_remove_script_from_status_file"', filename)
            else:
                if not cnt['joinscript_init']:
                    self.addmsg('0001-14', 'join script does not use joinscript_init', filename)
                if not cnt['joinscript_save_current_version']:
                    self.addmsg('0001-15', 'join script does not use joinscript_save_current_version', filename)

    def check(self, path: Path) -> None:
        super().check(path)
        self.check_files(chain(
            path.glob("[0-9][0-9]*.inst"),
            path.glob("[0-9][0-9]*.uinst"),
        ))

    def check_files(self, paths: Iterable[Path]) -> None:
        paths = list(paths)
        fnlist_joinscripts = {}
        fnlist_joinscripts.update({fn: JSS.CALLED for fn in paths if fn.match("[0-9][0-9]*.inst")})
        fnlist_joinscripts.update({fn: JSS.CALLED | JSS.COPIED for fn in paths if fn.match("[0-9][0-9]*.uinst")})

        #
        # check if join scripts use versioning
        #
        for js in fnlist_joinscripts:
            self.check_join_script(js)

        #
        # check if join scripts are present in debian/rules || debian/*.install
        #
        found: dict[Path, int] = {}
        debianpath = self.path / 'debian'
        # get all .install files
        fnlist = list(uub.FilteredDirWalkGenerator(debianpath, suffixes=['.install']))
        # append debian/rules
        fn_rules = self.path / 'debian' / 'rules'
        fnlist.append(fn_rules)

        # Look for dh-umc-modules-install
        try:
            fn_control = self.path / 'debian' / 'control'
            ctrl: uub.ParserDebianControl | None = uub.ParserDebianControl(fn_control)
        except uub.UCSLintException:
            self.debug('Errors in debian/control. Skipping here')
            ctrl = None

        try:
            c_rules = fn_rules.read_text()
        except OSError:
            self.addmsg('0001-9', 'failed to open and read file', fn_rules)
        else:
            match = self.RE_DH_JOIN.search(c_rules)
            if match:
                self.debug(f'Detected use of {match[0]}')
                is_old = bool(match[1])
                if is_old:
                    self.addmsg('0001-23', 'Consider switchting to "univention-join" debhelper sequence', fn_rules)
                if ctrl:
                    for binary_package in ctrl.binary_sections:
                        package = binary_package['Package']
                        for js in fnlist_joinscripts:
                            if js.stem[2:] == package:
                                self.debug(f'univention-install-joinscript will take care of {js}')
                                fnlist_joinscripts[js] = JSS.UNREF
                                found[js] = found.get(js, 0) + 1

                    if 'univention-join-dev' not in ctrl.source_section.dep and not is_old:
                        self.addmsg('0001-22', '"dh --with univention-join" is used in "debian/rules" without "Build-Depends: univention-join-dev" in "debian/rules"', fn_control)

            if self.RE_DH_UMC.search(c_rules):
                self.debug('Detected use of dh-umc-module-install')
                for fn in uub.FilteredDirWalkGenerator(debianpath, suffixes=['.umc-modules']):
                    for js in fnlist_joinscripts:
                        if js.stem[2:] == fn.stem:
                            self.debug(f'{js} installed by dh-umc-module-install')
                            found[js] = found.get(js, 0) + 1
                            fnlist_joinscripts[js] = JSS.UNREF

        for fn in fnlist:
            try:
                content = fn.read_text()
            except OSError:
                self.addmsg('0001-9', 'failed to open and read file', fn)
                continue

            for js in fnlist_joinscripts:
                self.debug(f'looking for {js.name} in {fn}')
                if js.name in content:
                    self.debug(f'found {js.name} in {fn}')
                    found[js] = found.get(js, 0) + 1

        for js in fnlist_joinscripts:
            if found.get(js, 0) == 0:
                self.addmsg('0001-6', 'join script is not mentioned in debian/rules or *.install files', js)

        #
        # check if join scripts are present in debian/*{pre,post}{inst,rm}
        #
        for fn in self.path.glob("debian/*"):
            if '.debhelper.' in fn.name:
                continue

            if fn.suffix == '.postinst' or fn.name == 'postinst':
                bit = JSS.CALLED
            elif fn.suffix == '.prerm' or fn.name == 'prerm':
                bit = JSS.COPIED
            elif fn.suffix == '.postrm' or fn.name == 'postrm':
                bit = JSS.CALLED
            else:
                continue

            self.debug(f'loading {fn}')
            try:
                content = fn.read_text()
            except OSError:
                self.addmsg('0001-9', 'failed to open and read file', fn)
                continue

            set_e = self.RE_LINE_CONTAINS_SET_E.search(content)
            if set_e:
                self.debug(f'found "set -e" in {fn}')

            for js in fnlist_joinscripts:
                self.debug(f'looking for {js.name} in {fn}')
                if js.name in content:
                    fnlist_joinscripts[js] &= ~bit
                    self.debug(f'found {js.name} in {fn}')

                    if set_e:
                        for row, line in enumerate(content.splitlines(), start=1):
                            if js.name in line:
                                match = self.RE_LINE_ENDS_WITH_TRUE.search(line)
                                if not match:
                                    self.addmsg('0001-8', f'the join script {js.name} is not called with "|| true" but "set -e" is set', fn, row, line=line)

        for js, missing in fnlist_joinscripts.items():
            if missing & JSS.CALLED and js.suffix == '.inst':
                self.addmsg('0001-7', 'Join script is not mentioned in debian/*.postinst', js)
            if missing & JSS.CALLED and js.suffix == '.uinst':
                self.addmsg('0001-17', 'Unjoin script seems not to be called in any postrm file', js)
            if missing & JSS.COPIED and js.suffix == '.uinst':
                self.addmsg('0001-18', 'Unjoin script seems not to be copied in any prerm file', js)
