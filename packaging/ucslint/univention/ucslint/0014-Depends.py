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
from pathlib import Path
from typing import TYPE_CHECKING


try:
    from apt import Cache  # type: ignore
except ImportError:
    Cache = None

import univention.ucslint.base as uub


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator

    from apt.package import Version


class UniventionPackageCheck(uub.UniventionPackageCheckDebian):
    RE_FIELD = re.compile(r"([a-z0-9_]+)[ \t]*(?:(<<|<=|=|>=|>>)[ \t]*([-a-zA-Z0-9.+~]+))?")
    RE_INIT = re.compile(r"^(?:File|Subfile): (etc/init.d/.+)$")
    RE_TRANSITIONAL = re.compile(r'\b[Tt]ransition(?:al)?(?: dummy)? [Pp]ackage\b')  # re.IGNORECASE
    DEPS = {
        'uicr': (re.compile(r"(?:/usr/bin/)?univention-install-(?:config-registry(?:-info)?|service-info)|\bdh\b.*--with\b.*\bucr\b"), {'univention-config-dev'}),
        'umcb': (re.compile(r"(?:/usr/bin/)?dh-umc-module-build|\bdh\b.*--with\b.*\bumc\b"), {'univention-management-console-dev'}),
        'ucr': (re.compile(r"""(?:^|(?<=['";& \t]))(?:/usr/sbin/)?(?:univention-config-registry|ucr)(?:(?=['";& \t])|$)"""), {'univention-config', '${misc:Depends}'}),
        'ial': (re.compile(r"/usr/share/univention-config-registry/init-autostart\.lib"), {'univention-base-files'}),
    }
    PRIORITIES = frozenset({'required', 'important'})

    def __init__(self) -> None:
        super().__init__()
        self.apt: Cache | None = None

    def getMsgIds(self) -> uub.MsgIds:
        return {
            '0014-0': (uub.RESULT_WARN, 'failed to open/read file'),
            '0014-1': (uub.RESULT_ERROR, 'parsing error in debian/control'),
            '0014-2': (uub.RESULT_ERROR, 'univention-install-... is used in debian/rules, but debian/control lacks a build-dependency on univention-config-dev.'),
            '0014-3': (uub.RESULT_ERROR, 'dh-umc-module-build is used in debian/rules, but debian/control lacks a build-dependency on univention-management-console-dev.'),
            '0014-4': (uub.RESULT_ERROR, 'univention-config-registry is used in a .preinst script, but the package lacks a pre-dependency on univention-config.'),
            '0014-5': (uub.RESULT_ERROR, 'univention-config-registry is used in a maintainer script, but the package lacks a dependency on univention-config.'),
            '0014-6': (uub.RESULT_WARN, 'init-autostart.lib is sourced by a script, but the package lacks an explicit dependency on univention-base-files.'),
            '0014-7': (uub.RESULT_WARN, 'The source package contains debian/*.univention- files, but the package is not found in debian/control.'),
            '0014-8': (uub.RESULT_WARN, 'unexpected UCR file'),
            '0014-9': (uub.RESULT_WARN, 'depends on transitional package'),
            '0014-10': (uub.RESULT_WARN, 'depends on "Essential:yes" package'),
            '0014-11': (uub.RESULT_STYLE, 'depends on "Priority:required/important" package'),
        }

    def postinit(self, path: Path) -> None:
        """Check to be run before real check or to create pre-calculated data for several runs. Only called once!"""
        try:
            self.apt = Cache(memonly=True)
        except Exception as ex:
            self.debug(f'failed to load APT cache: {ex}')

    def _scan_script(self, fn: Path) -> set[str]:
        """Find calls to 'univention-install-', 'ucr' and use of 'init-autostart.lib' in file 'fn'."""
        need = set()
        self.debug(f'Reading {fn}')
        try:
            with fn.open() as fd:
                for line in fd:
                    for (key, (regexp, _pkgs)) in self.DEPS.items():
                        if regexp.search(line):
                            self.debug(f'Found {key.upper()} in {fn}')
                            need.add(key)
        except OSError:
            self.addmsg('0014-0', 'failed to open and read file', fn)
            return need

        return need

    def check_source(self, path: Path, source_section: uub.DebianControlSource) -> set[str]:
        """Check source package for dependencies."""
        src_deps = source_section.dep_all

        fn_rules = path / 'debian' / 'rules'
        need = self._scan_script(fn_rules)
        uses_uicr = 'uicr' in need
        uses_umcb = 'umcb' in need

        # Assert packages using "univention-install-" build-depens on "univention-config-dev" and depend on "univention-config"
        if uses_uicr and not src_deps & self.DEPS['uicr'][1]:
            self.addmsg('0014-2', 'Missing Build-Depends: univention-config-dev', fn_rules)

        if uses_umcb and not src_deps & self.DEPS['umcb'][1]:
            self.addmsg('0014-3', 'Missing Build-Depends: univention-management-console-dev', fn_rules)

        return src_deps

    def check_package(self, path: Path, section: uub.DebianControlBinary) -> set[str]:
        """Check binary package for dependencies."""
        pkg = section['Package']
        self.debug(f'Package: {pkg}')

        bin_pre_set = section.pre
        bin_deps = bin_pre_set | section.dep

        # Assert packages using "ucr" in preinst pre-depend on "univention-config"
        for ms in ('preinst',):
            fn = path / 'debian' / f'{pkg}.{ms}'
            if not fn.exists():
                continue
            need = self._scan_script(fn)
            if 'ucr' in need and not bin_pre_set & self.DEPS['ucr'][1]:
                self.addmsg('0014-4', 'Missing Pre-Depends: univention-config', fn)

        # Assert packages using "ucr" depend on "univention-config"
        for ms in ('postinst', 'prerm', 'postrm'):
            fn = path / 'debian' / f'{pkg}.{ms}'
            if not fn.exists():
                continue
            need = self._scan_script(fn)
            if 'ucr' in need and not bin_deps & self.DEPS['ucr'][1]:
                self.addmsg('0014-5', 'Missing Depends: univention-config, ${misc:Depends}', fn)

        for fn in path.glob(f'[0-9][0-9]{pkg}.inst'):
            need = self._scan_script(fn)
            if 'ucr' in need and not bin_deps & self.DEPS['ucr'][1]:
                self.addmsg('0014-4', 'Missing Depends: univention-config, ${misc:Depends}', fn)

        # FIXME: scan all other files for ucr as well?

        # Assert packages using "init-autostart.lib" depends on "univention-base-files"
        init_files = {
            path / 'debian' / f'{pkg}.init',
            path / 'debian' / f'{pkg}.init.d',
        }
        try:
            fn = path / 'debian' / f'{pkg}.univention-config-registry'
            if fn.exists():
                with fn.open() as fd:
                    for line in fd:
                        m = self.RE_INIT.match(line)
                        if m:
                            init_files.add(path / 'conffiles' / m[1])
        except OSError:
            self.addmsg('0014-0', 'failed to open and read file', fn)

        for fn in init_files:
            if not fn.exists():
                continue
            need = self._scan_script(fn)
            if 'ial' in need and not bin_deps & self.DEPS['ial'][1]:
                self.addmsg('0014-6', 'Missing Depends: univention-base-files', fn)

        return bin_deps | section.rec | section.sug

    def check(self, path: Path) -> None:
        super().check(path)
        self.check_files([])

    def check_files(self, paths: Iterable[Path]) -> None:
        if self.path == Path('/'):
            return
        fn_control = self.path / 'debian' / 'control'
        self.debug(f'Reading {fn_control}')
        try:
            parser = uub.ParserDebianControl(fn_control)
        except uub.FailedToReadFile:
            self.addmsg('0014-0', 'failed to open and read file', fn_control)
            return
        except uub.UCSLintException:
            self.addmsg('0014-1', 'parsing error', fn_control)
            return

        deps = self.check_source(self.path, parser.source_section)
        for section in parser.binary_sections:
            deps |= self.check_package(self.path, section)

        self.check_unknown(self.path, parser)
        self.check_transitional(self.path, deps)
        self.check_essential(self.path, deps)

    def check_unknown(self, path: Path, parser: uub.ParserDebianControl) -> None:
        # Assert all files debian/$pkg.$suffix belong to a package $pkg declared in debian/control
        SUFFIXES = (
            '.univention-config-registry',
            '.univention-config-registry-variables',
            '.univention-config-registry-categories',
            '.univention-service',
        )
        exists = {
            filename.name
            for filename in path.glob('debian/*.univention-*')
            if filename.suffix in SUFFIXES
        }
        known = {
            section['Package'] + suffix
            for section in parser.binary_sections
            for suffix in SUFFIXES
        }
        for unowned in exists - known:
            self.addmsg('0014-8', 'unexpected UCR file', path / 'debian' / unowned)

    def check_transitional(self, path: Path, deps: Iterable[str]) -> None:
        fn_control = path / 'debian' / 'control'
        for cand in self._cand(deps):
            if self.RE_TRANSITIONAL.search(cand.summary or ''):
                self.addmsg('0014-9', f'depends on transitional package {cand.package.name}', fn_control)

    def check_essential(self, path: Path, deps: Iterable[str]) -> None:
        fn_control = path / 'debian' / 'control'
        for cand in self._cand(deps):
            if cand.package.essential:
                self.addmsg('0014-10', f'depends on "Essential:yes" package {cand.package.name}', fn_control)
            elif cand.priority in self.PRIORITIES:
                self.addmsg('0014-11', f'depends on "Priority:required/important" package {cand.package.name}', fn_control)

    def _cand(self, deps: Iterable[str]) -> Iterator[Version]:
        if not self.apt:
            return

        for dep in deps:
            if dep.startswith('${'):
                continue
            try:
                pkg = self.apt[dep]
                cand = pkg.candidate
                if not cand:
                    raise LookupError(dep)
            except LookupError as ex:
                self.debug(f'not found {dep}: {ex}')
            else:
                yield cand
