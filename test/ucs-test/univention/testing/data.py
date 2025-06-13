# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Test case, environment, result and related classes."""

# pylint: disable-msg=R0902,W0201,R0903,E1101,E0611

from __future__ import annotations

import errno
import logging
import os
import re
import select
import signal
import sys
from datetime import datetime
from functools import reduce
from operator import and_, or_
from subprocess import PIPE, Popen, call
from time import monotonic
from typing import IO, TYPE_CHECKING, Any, TypeVar, cast

import apt
import retrying
import yaml
from apt_pkg import Error as Apt_Pkg_Error

from univention.config_registry import ConfigRegistry
from univention.testing.codes import Reason
from univention.testing.errors import TestError
from univention.testing.internal import UCSVersion
from univention.testing.pytest import PytestRunner


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator, Sequence


__all__ = ['TestCase', 'TestEnvironment', 'TestFormatInterface', 'TestResult']

T = TypeVar("T")

# <http://stackoverflow.com/questions/1707890/>
ILLEGAL_XML_UNICHR = (
    (0x00, 0x08), (0x0B, 0x1F), (0x7F, 0x84), (0x86, 0x9F),
    (0xD800, 0xDFFF), (0xFDD0, 0xFDDF), (0xFFFE, 0xFFFF),
    (0x1FFFE, 0x1FFFF), (0x2FFFE, 0x2FFFF), (0x3FFFE, 0x3FFFF),
    (0x4FFFE, 0x4FFFF), (0x5FFFE, 0x5FFFF), (0x6FFFE, 0x6FFFF),
    (0x7FFFE, 0x7FFFF), (0x8FFFE, 0x8FFFF), (0x9FFFE, 0x9FFFF),
    (0xAFFFE, 0xAFFFF), (0xBFFFE, 0xBFFFF), (0xCFFFE, 0xCFFFF),
    (0xDFFFE, 0xDFFFF), (0xEFFFE, 0xEFFFF), (0xFFFFE, 0xFFFFF),
    (0x10FFFE, 0x10FFFF),
)
RE_ILLEGAL_XML = re.compile('[%s]' % ''.join(f'{chr(low)}-{chr(high)}' for (low, high) in ILLEGAL_XML_UNICHR if low < sys.maxunicode))


def checked_set(values: Iterable[T] | None) -> set[T]:
    if not isinstance(values, list | tuple | set | frozenset):
        raise TypeError('"%r" not a list or tuple' % values)
    return set(values)


class TestEnvironment:
    """
    Test environment for running test cases.

    Handels system data, requirements checks, test output.
    """

    logger = logging.getLogger('test.env')

    def __init__(self, interactive: bool = True, logfile: str | None = None) -> None:
        self.exposure = 'safe'
        self.interactive = interactive
        self.timeout = 0

        self._load_host()
        self._load_ucr()
        self._load_join()
        self._load_apt()
        self._local_apps: list[str] | None = None

        if interactive:
            self.tags_required: set[str] | None = None
            self.tags_prohibited: set[str] | None = None
        else:
            self.tags_required = set()
            self.tags_prohibited = {'SKIP', 'WIP'}

        self.log = open(logfile or os.path.devnull, 'a')

    @property
    @retrying.retry(wait_fixed=3000, stop_max_attempt_number=3)
    def local_apps(self) -> list[str]:
        """Lazy load locally installed apps."""
        logging.getLogger('univention.appcenter').setLevel(TestEnvironment.logger.getEffectiveLevel())
        if self._local_apps is None:
            # shitty, but we have no app cache in pbuilder and apps_cache can't handle that
            try:
                from univention.appcenter.app_cache import Apps
                apps_cache = Apps()
                self._local_apps = [app.id for app in apps_cache.get_all_locally_installed_apps()]
            except (ImportError, TypeError, PermissionError, Apt_Pkg_Error):
                self._local_apps = [
                    key.split('/')[2]
                    for key, value in self.ucr.items()
                    if key.startswith('appcenter/apps')
                    if len(key.split('/')) > 3
                    if key.split('/')[3] == 'status'
                    if value == 'installed'
                ]
        return self._local_apps

    def _load_host(self) -> None:
        """Load host system information."""
        (_sysname, nodename, _release, _version, machine) = os.uname()
        self.hostname = nodename
        self.architecture = machine

    def _load_ucr(self) -> None:
        """Load Univention Config Registry information."""
        self.ucr = ConfigRegistry()
        self.ucr.load()
        self.role = self.ucr.get('server/role', '')
        TestEnvironment.logger.debug('Role=%r' % self.role)

        version = self.ucr.get('version/version', '0.0').split('.', 1)
        major, minor = int(version[0]), int(version[1])
        patchlevel = int(self.ucr.get('version/patchlevel', 0))
        if (major, minor) < (3, 0):
            securitylevel = int(self.ucr.get('version/security-patchlevel', 0))
            self.ucs_version = UCSVersion((major, minor, patchlevel, securitylevel))
        else:
            erratalevel = int(self.ucr.get('version/erratalevel', 0))
            self.ucs_version = UCSVersion((major, minor, patchlevel, erratalevel))
        TestEnvironment.logger.debug('Version=%r' % self.ucs_version)

    def _load_join(self) -> None:
        """Load join status."""
        with open(os.path.devnull, 'w+') as devnull:
            try:
                ret = call(
                    ('/usr/sbin/univention-check-join-status',),
                    stdin=devnull, stdout=devnull, stderr=devnull)
                self.joined = ret == 0
            except OSError:
                self.joined = False
        TestEnvironment.logger.debug('Join=%r' % self.joined)

    def _load_apt(self) -> None:
        """Load package information."""
        self.apt = apt.Cache()

    def dump(self, stream: IO[str] = sys.stdout) -> None:
        """Dump environment information."""
        print('hostname: %s' % (self.hostname,), file=stream)
        print('architecture: %s' % (self.architecture,), file=stream)
        print('version: %s' % (self.ucs_version,), file=stream)
        print('role: %s' % (self.role,), file=stream)
        print('apps: %s' % (self.local_apps,), file=stream)
        print('joined: %s' % (self.joined,), file=stream)
        print('tags_required: %s' % (' '.join(self.tags_required or set()) or '-',), file=stream)
        print('tags_prohibited: %s' % (' '.join(self.tags_prohibited or set()) or '-',), file=stream)
        print('timeout: %d' % (self.timeout,), file=stream)

    def tag(self, require: set[str] = set(), ignore: set[str] = set(), prohibit: set[str] = set()) -> None:
        """Update required, ignored, prohibited tags."""
        if self.tags_required is not None:
            self.tags_required -= set(ignore)
            self.tags_required |= set(require)
        if self.tags_prohibited is not None:
            self.tags_prohibited -= set(ignore)
            self.tags_prohibited |= set(prohibit)
        TestEnvironment.logger.debug(f'tags_required={self.tags_required!r} tags_prohibited={self.tags_prohibited!r}')

    def set_exposure(self, exposure: str) -> None:
        """Set maximum allowed exposure level."""
        self.exposure = exposure

    def set_timeout(self, timeout: int) -> None:
        """Set maximum allowed time for single test."""
        self.timeout = timeout


class _TestReader:  # pylint: disable-msg=R0903
    """Read test case header lines starting with ##."""

    def __init__(self, stream: IO[bytes]) -> None:
        self.stream = stream

    def read(self, size: int = -1) -> bytes:
        """Read next line prefixed by '## '."""
        while True:
            line = self.stream.readline(size)
            if not line:
                return b''  # EOF
            if line.startswith(b'## '):
                return line[3:]
            if not line.startswith(b'#'):
                while line:
                    line = self.stream.readline(size)


class Verdict:
    """Result of a test, either successful or failed."""

    INFO = 0  # Successful check, continue
    WARNING = 1  # Non-critical condition, may continue
    ERROR = 2  # Critical contion, abort

    logger = logging.getLogger('test.cond')

    def __init__(self, level: int, message: str, reason: Reason | None = None) -> None:
        self.level = level
        self.message = message
        self.reason = reason
        Verdict.logger.debug(self)

    def __bool__(self) -> bool:
        return self.level < Verdict.ERROR
    __nonzero__ = __bool__

    def __str__(self) -> str:
        return '%s: %s' % ('IWE'[self.level], self.message)

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(level={self.level!r}, message={self.message!r})'


class Check:
    """Abstract check."""

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check if precondition to run test is met."""
        raise NotImplementedError()

    def pytest_args(self, environment: TestEnvironment) -> list[str]:
        return []


class CheckExecutable(Check):
    """Check language."""

    def __init__(self, filename: str) -> None:
        super().__init__()
        self.filename = filename
        self.executable_args: list[str] = []

    def check(self, _environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for required executable."""
        if not os.path.isabs(self.filename):
            if self.filename.startswith('python') or self.filename.startswith('pytest') or self.filename.startswith('py.test'):
                self.filename = '/usr/bin/' + self.filename
            elif self.filename.endswith('sh'):
                self.filename = '/bin/' + self.filename
            else:
                yield Verdict(Verdict.ERROR, f'Unknown executable: {self.filename}', Reason.INSTALL)
                return
        if self.filename.startswith('/usr/bin/python3'):
            self.executable_args.append('-u')
        if os.path.isfile(self.filename):
            yield Verdict(Verdict.INFO, f'Executable: {self.filename}')
        else:
            yield Verdict(Verdict.ERROR, f'Missing executable: {self.filename}', Reason.INSTALL)

    def __str__(self) -> str:
        return self.filename


class CheckVersion(Check):
    """Check expected result of test for version."""

    STATES = frozenset(('found', 'fixed', 'skip', 'run'))

    def __init__(self, versions: dict[str, str]) -> None:
        super().__init__()
        self.versions = versions
        self.state = 'run'

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for expected version."""
        versions = []
        for version, state in self.versions.items():
            ucs_version = UCSVersion(version)
            if state not in CheckVersion.STATES:
                yield Verdict(Verdict.WARNING, f'Unknown state "{state}" for version "{version}"')
                continue
            versions.append((ucs_version, state))
        versions.sort()
        for (ucs_version, state) in versions:
            if ucs_version <= environment.ucs_version:
                self.state = state
        if self.state == 'skip':
            yield Verdict(Verdict.ERROR, f'Skipped for version {environment.ucs_version}', Reason.VERSION_MISMATCH)


class CheckTags(Check):
    """Check for required / prohibited tags."""

    def __init__(self, tags: Iterable[str]) -> None:
        super().__init__()
        self.tags = checked_set(tags)

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for required / prohibited tags."""
        if environment.tags_required is None or environment.tags_prohibited is None:
            yield Verdict(Verdict.INFO, 'Tags disabled')
            return
        prohibited = self.tags & environment.tags_prohibited
        if prohibited:
            yield Verdict(Verdict.ERROR, 'De-selected by tag: %s' % (' '.join(prohibited),), Reason.ROLE_MISMATCH)
        elif environment.tags_required:
            required = self.tags & environment.tags_required
            if required:
                yield Verdict(Verdict.INFO, 'Selected by tag: %s' % (' '.join(required),))
            else:
                yield Verdict(Verdict.ERROR, 'De-selected by tag: %s' % (' '.join(environment.tags_required),), Reason.ROLE_MISMATCH)

    def pytest_args(self, environment: TestEnvironment) -> list[str]:
        args = []
        for tag in self.tags:
            args.extend(['--ucs-test-default-tags', tag])
        for tag in (environment.tags_required or []):
            if tag in ('SKIP', 'WIP'):
                continue
            args.extend(['--ucs-test-tags-required', tag])
        for tag in (environment.tags_prohibited or []):
            if tag in ('SKIP', 'WIP'):
                continue
            args.extend(['--ucs-test-tags-prohibited', tag])
        return args


class CheckApps(Check):
    """Check apps on server."""

    def __init__(self, apps_required: Iterable[str] = (), apps_prohibited: Iterable[str] = ()) -> None:
        super().__init__()
        self.apps_required = checked_set(apps_required)
        self.apps_prohibited = checked_set(apps_prohibited)

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for required / prohibited apps."""
        for app in self.apps_required:
            if app not in environment.local_apps:
                yield Verdict(Verdict.ERROR, 'Required app missing: %s' % app, Reason.APP_MISMATCH)
        for app in self.apps_prohibited:
            if app in environment.local_apps:
                yield Verdict(Verdict.ERROR, 'Prohibited app installed: %s' % app, Reason.APP_MISMATCH)


class CheckRoles(Check):
    """Check server role."""

    ROLES = frozenset((
        'domaincontroller_master',
        'domaincontroller_backup',
        'domaincontroller_slave',
        'memberserver',
        'basesystem',
    ))

    def __init__(self, roles_required: Iterable[str] = (), roles_prohibited: Iterable[str] = ()) -> None:
        super().__init__()
        self.roles_required = checked_set(roles_required)
        self.roles_prohibited = checked_set(roles_prohibited)

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for required / prohibited server role."""
        overlap = self.roles_required & self.roles_prohibited
        if overlap:
            yield Verdict(Verdict.WARNING, 'Overlapping roles: %s' % (' '.join(overlap),))
            roles = self.roles_required - self.roles_prohibited
        elif self.roles_required:
            roles = set(self.roles_required)
        else:
            roles = set(CheckRoles.ROLES) - set(self.roles_prohibited)

        unknown_roles = roles - CheckRoles.ROLES
        if unknown_roles:
            yield Verdict(Verdict.WARNING, 'Unknown roles: %s' % (' '.join(unknown_roles),))

        if environment.role not in roles:
            yield Verdict(Verdict.ERROR, 'Wrong role: %s not in (%s)' % (environment.role, ','.join(roles)), Reason.ROLE_MISMATCH)


class CheckJoin(Check):
    """Check join status."""

    def __init__(self, joined: bool | None) -> None:
        super().__init__()
        self.joined = joined

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for join status."""
        if self.joined is None:
            yield Verdict(Verdict.INFO, 'No required join status')
        elif self.joined and not environment.joined:
            yield Verdict(Verdict.ERROR, 'Test requires system to be joined', Reason.JOIN)
        elif not self.joined and environment.joined:
            yield Verdict(Verdict.ERROR, 'Test requires system to be not joined', Reason.JOINED)
        else:
            yield Verdict(Verdict.INFO, f'Joined: {environment.joined}')


class CheckComponents(Check):
    """Check for required / prohibited components."""

    def __init__(self, components: dict[str, str]) -> None:
        super().__init__()
        self.components = components

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for required / prohibited components."""
        for component, required in self.components.items():
            key = f'repository/online/component/{component}'
            active = environment.ucr.is_true(key, False)
            if required:
                if active:
                    yield Verdict(Verdict.INFO, f'Required component {component} active')
                else:
                    yield Verdict(Verdict.ERROR, f'Required component {component} missing', Reason.INSTALL)
            else:  # not required
                if active:
                    yield Verdict(Verdict.ERROR, f'Prohibited component {component} active', Reason.INSTALLED)
                else:
                    yield Verdict(Verdict.INFO, f'Prohibited component {component} not active')


class CheckPackages(Check):
    """Check for required packages."""

    def __init__(self, packages: Sequence[str], packages_not: Sequence[str]) -> None:
        super().__init__()
        self.packages = packages
        self.packages_not = packages_not

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for required / prohibited packages."""
        def check_disjunction(conjunction):
            """Check is any of the alternative packages is installed."""
            for name, dep_version, dep_op in conjunction:
                try:
                    pkg = environment.apt[name]
                except KeyError:
                    yield Verdict(Verdict.ERROR, f'Package {name} not found', Reason.INSTALL)
                    continue
                ver = pkg.installed
                if ver is None:
                    yield Verdict(Verdict.ERROR, f'Package {name} not installed', Reason.INSTALL)
                    continue
                if dep_version and not apt.apt_pkg.check_dep(ver.version, dep_op, dep_version):
                    yield Verdict(Verdict.ERROR, f'Package {name} version mismatch', Reason.INSTALL)
                    continue
                yield Verdict(Verdict.INFO, f'Package {name} installed')
                break

        for dependency in self.packages:
            deps = apt.apt_pkg.parse_depends(dependency)
            for conjunction in deps:
                conditions = list(check_disjunction(conjunction))
                success = reduce(or_, (bool(_) for _ in conditions), False)
                if success:
                    for condition in conditions:
                        if condition.level < Verdict.ERROR:
                            yield condition
                else:
                    for condition in conditions:
                        yield condition

        for pkg in self.packages_not:
            try:
                p = environment.apt[pkg]
            except KeyError:
                continue
            if p.installed:
                yield Verdict(Verdict.ERROR, f'Package {pkg} is installed, but should not be', Reason.INSTALLED)
                break


class CheckExposure(Check):
    """Check for signed exposure."""

    STATES = ['safe', 'careful', 'dangerous']

    def __init__(self, exposure: str) -> None:
        super().__init__()
        self.exposure = exposure

    def check(self, environment: TestEnvironment) -> Iterator[Verdict]:
        """Check environment for permitted exposure level."""
        if self.exposure not in CheckExposure.STATES:
            yield Verdict(Verdict.WARNING, f'Unknown exposure: {self.exposure}')
            return
        if CheckExposure.STATES.index(self.exposure) > CheckExposure.STATES.index(environment.exposure):
            yield Verdict(Verdict.ERROR, f'Too dangerous: {self.exposure} > {environment.exposure}', Reason.DANGER)
        else:
            yield Verdict(Verdict.INFO, f'Safe enough: {self.exposure} <= {environment.exposure}')

    def pytest_args(self, environment: TestEnvironment) -> list[str]:
        args = []
        args.extend(['--ucs-test-exposure', environment.exposure.lower()])
        if self.exposure:
            args.extend(['--ucs-test-default-exposure', self.exposure.lower()])
        return args


class TestCase:
    """Test case."""

    logger = logging.getLogger('test.case')
    RE_NL = re.compile(br'[\r\n]+')

    def __init__(self, filename: str) -> None:
        self.filename = os.path.abspath(filename)
        self.uid = os.path.sep.join(filename.rsplit(os.path.sep, 2)[-2:])

        self.exe: CheckExecutable | None = None
        self.args: list[str] = []
        self.description: str | None = None
        self.bugs: set[str] = set()
        self.otrs: set[str] = set()
        self.timeout: int | None = None
        self.is_pytest: bool = False
        self.external_junit: str | None = None
        self.environment: dict = {}

    def load(self) -> TestCase:
        """Load test case from stream."""
        try:
            header = self.load_meta()
        except OSError as ex:
            TestCase.logger.critical(
                'Failed to read "%s": %s',
                self.filename, ex)
            raise TestError('Failed to open file')

        self.parse_meta(header)

        return self

    def load_meta(self) -> dict[str, Any]:
        TestCase.logger.info('Loading test %s', self.filename)

        with open(self.filename, 'rb') as tc_file:
            firstline = tc_file.readline()
            if not firstline.startswith(b'#!'):
                raise TestError('Missing hash-bang')
            args = firstline.decode('utf-8').split(None)
            try:
                lang = args[1]
            except IndexError:
                lang = ''
            self.exe = CheckExecutable(lang)
            self.args = args[2:]

            reader = cast(IO[bytes], _TestReader(tc_file))
            try:
                header = yaml.safe_load(reader) or {}
            except yaml.scanner.ScannerError as ex:
                TestCase.logger.critical(
                    'Failed to read "%s": %s',
                    self.filename, ex,
                    exc_info=True)
                raise TestError('Invalid test YAML data')

        return header

    def parse_meta(self, header: dict[str, Any]) -> None:
        try:
            self.description = header.get('desc', '').strip()
            self.bugs = checked_set(header.get('bugs', []))
            self.otrs = checked_set(header.get('otrs', []))
            self.versions = CheckVersion(header.get('versions', {}))
            self.tags = CheckTags(header.get('tags', []))
            self.roles = CheckRoles(
                header.get('roles', []),
                header.get('roles-not', []))
            self.apps = CheckApps(
                header.get('apps', []),
                header.get('apps-not', []))
            self.join = CheckJoin(header.get('join'))
            self.components = CheckComponents(header.get('components', {}))
            self.packages = CheckPackages(header.get('packages', []), header.get('packages-not', []))
            self.exposure = CheckExposure(header.get('exposure', 'dangerous'))
            self.external_junit = header.get('external-junit', '').strip()
            self.environment = {k: str(v) for k, v in header.get('env', {}).items()}
            try:
                self.timeout = int(header['timeout'])
            except LookupError:
                pass
        except (TypeError, ValueError) as ex:
            TestCase.logger.critical(
                'Tag error in "%s": %s',
                self.filename, ex,
                exc_info=True)
            raise TestError(ex)

        self.is_pytest = PytestRunner.is_pytest(self)

    def check(self, environment: TestEnvironment) -> list[Verdict]:
        """Check if the test case should run."""
        TestCase.logger.info(f'Checking test {self.filename}')
        if self.timeout is None:
            self.timeout = environment.timeout
        conditions = []
        assert self.exe is not None
        conditions += list(self.exe.check(environment))
        conditions += list(self.versions.check(environment))
        conditions += list(self.tags.check(environment))
        conditions += list(self.roles.check(environment))
        conditions += list(self.apps.check(environment))
        conditions += list(self.components.check(environment))
        conditions += list(self.packages.check(environment))
        conditions += list(self.exposure.check(environment))
        return conditions

    def pytest_check(self, environment: TestEnvironment) -> list[str]:
        args: list[str] = []
        args += self.exe.pytest_args(environment) if self.exe else "No exectable"
        args += self.versions.pytest_args(environment)
        args += self.tags.pytest_args(environment)
        args += self.roles.pytest_args(environment)
        args += self.apps.pytest_args(environment)
        args += self.components.pytest_args(environment)
        args += self.packages.pytest_args(environment)
        args += self.exposure.pytest_args(environment)
        return args

    def _run_tee(self, proc: Popen, result: TestResult, stdout: IO[str] = sys.stdout, stderr: IO[str] = sys.stderr) -> None:
        """Run test collecting and passing through stdout, stderr:"""
        assert proc.stdout is not None
        assert proc.stderr is not None
        rfd, wfd = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        channels: dict[int, tuple[IO[str], list, str, IO[str], str, bytearray]] = {
            proc.stdout.fileno(): (proc.stdout, [], 'stdout', stdout, '[]', bytearray()),
            proc.stderr.fileno(): (proc.stderr, [], 'stderr', stderr, '()', bytearray()),
            rfd: (open(rfd), [], "child", stderr, "{}", bytearray()),
        }
        combined = []

        def sigchld(signum: int, _frame: Any) -> None:
            self.logger.debug('Received SIG %d', signum)
            try:
                os.close(wfd)
            except OSError:
                pass

        signal.signal(signal.SIGCHLD, sigchld)
        next_kill = next_read = 0.0
        shutdown = False
        kill_sequence = self._terminate_proc(proc)
        while channels:
            current = monotonic()
            if next_kill <= current:
                shutdown, next_kill = next(kill_sequence)
                next_kill += current

            delays = [max(0.0, t - current) for t in (next_kill, next_read) if 0.0 < t < float("inf")]
            self.logger.debug("Delay=%r", delays)
            rlist, _wlist, _elist = select.select(list(channels), [], [], min(delays) if delays else None)
            self.logger.debug("rlist=%r", rlist)

            if rfd in rlist:
                self.logger.debug("Child died, collecting remaining output")
                shutdown = True
                next_kill = current + 3.0

            next_read = 0.0
            for fd in rlist or list(channels):
                stream, log, name, out, paren, buf = channels[fd]

                if fd in rlist:
                    data = os.read(fd, 1024)
                    out.buffer.write(data)  # type: ignore[attr-defined]
                    buf += data
                    eof = data == b''
                else:  # select() timed out, process remaining output
                    data = b''
                    eof = shutdown

                while buf:
                    if eof:  # all remaining on shutdown
                        line = buf
                        buf = bytearray()
                    else:  # otherwise only complete lines
                        match = TestCase.RE_NL.search(buf)
                        if not match:
                            break
                        line = buf[0:match.start()]
                        del buf[0:match.end()]

                    now = datetime.now().isoformat(' ')
                    entry = b'%s %s\n' % (f'{paren[0]}{now}{paren[1]}'.encode('ascii'), line.rstrip(b'\r\n'))
                    log.append(entry)
                    combined.append(entry)

                if eof:
                    self.logger.debug('Closing FD %d %s', fd, name)
                    stream.close()
                    del channels[fd]
                    TestCase._attach(result, name, log)

                if buf and data:  # re-do uncomplete line
                    next_read = current + 0.1

        self.logger.debug("Done")
        for fd in (rfd, wfd):
            try:
                os.close(fd)
            except OSError:
                pass

        TestCase._attach(result, 'stdout', combined)

    def _terminate_proc(self, proc: Popen) -> Iterator[tuple[bool, float]]:
        yield False, self.timeout or float("inf")
        try:
            for i in range(8):  # 2^8 * 100ms = 25.5s
                self.logger.info('Sending %d. SIGTERM to %d', i + 1, proc.pid)
                os.killpg(proc.pid, signal.SIGTERM)
                rc = proc.poll()
                self.logger.debug('rc=%s', rc)
                if rc is not None:
                    break
                yield False, (1 << i) / 10.0
            self.logger.info('Sending SIGKILL to %d', proc.pid)
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError as ex:
            if ex.errno != errno.ESRCH:
                self.logger.warning(
                    'Failed to kill process %d: %s', proc.pid, ex,
                    exc_info=True)
        while True:
            yield True, 1.0

    @staticmethod
    def _attach(result, part, content):
        """Attach content."""
        text = b''.join(content)
        dirty = text.decode(sys.getfilesystemencoding(), 'replace')
        clean = RE_ILLEGAL_XML.sub('\uFFFD', dirty)
        if clean:
            result.attach(part, 'text/plain', clean)

    def _translate_result(self, result: TestResult) -> Reason:
        """Translate exit code into result."""
        if result.result == int(Reason.SKIP):
            return Reason.SKIP

        if result.result == 0:
            return {
                'fixed': Reason.FIXED_EXPECTED,
                'found': Reason.FIXED_UNEXPECTED,
                'run': Reason.OKAY,
            }.get(self.versions.state, Reason.OKAY)

        try:
            return Reason.lookup(result.result)
        except Exception:
            return {
                'fixed': Reason.FAIL_UNEXPECTED,
                'found': Reason.FAIL_EXPECTED,
                'run': Reason.FAIL,
            }.get(self.versions.state, Reason.FAIL)

    def run(self, result: TestResult) -> None:
        """Run the test case and fill in result."""
        base = os.path.basename(self.filename)
        dirname = os.path.dirname(self.filename)
        assert self.exe is not None
        cmd = [self.exe.filename, *self.exe.executable_args, base, *self.args]

        if self.is_pytest:
            cmd = PytestRunner.extend_command(self, cmd)
            cmd.extend(self.pytest_check(result.environment))

        time_start = datetime.now()

        print('\n*** BEGIN *** %r ***' % (cmd,), file=result.environment.log)
        print('*** %s *** %s ***' % (self.uid, self.description), file=result.environment.log)
        print('*** START TIME: %s ***' % (time_start.strftime("%Y-%m-%d %H:%M:%S")), file=result.environment.log)
        result.environment.log.flush()

        # Protect wrapper from Ctrl-C as long as test case is running
        def handle_int(_signal: int, _frame: Any) -> None:
            """Handle Ctrl-C signal."""
            result.reason = Reason.ABORT
        old_sig_int = signal.signal(signal.SIGINT, handle_int)

        def prepare_child() -> None:
            """Setup child process."""
            os.setsid()
            signal.signal(signal.SIGINT, signal.SIG_IGN)

        try:
            TestCase.logger.debug('Running %r using %s in %s', cmd, self.exe, dirname)
            try:
                assert self.exe is not None
                if result.environment.interactive:
                    proc = Popen(
                        cmd, executable=self.exe.filename,
                        shell=False, stdout=PIPE, stderr=PIPE,
                        close_fds=True, cwd=dirname,
                        preexec_fn=os.setsid,  # noqa: PLW1509
                        env=dict(os.environ, **self.environment),
                    )
                    to_stdout, to_stderr = sys.stdout, sys.stderr
                else:
                    with open(os.path.devnull, 'rb') as devnull:
                        proc = Popen(
                            cmd, executable=self.exe.filename,
                            shell=False, stdin=devnull,
                            stdout=PIPE, stderr=PIPE, close_fds=True,
                            cwd=dirname, preexec_fn=prepare_child,  # noqa: PLW1509
                            env=dict(os.environ, **self.environment),
                        )
                    to_stdout = to_stderr = result.environment.log

                self._run_tee(proc, result, to_stdout, to_stderr)

                result.result = proc.wait()
            except OSError:
                TestCase.logger.error('Failed to execute %r using %s in %s', cmd, self.exe, dirname)
                raise
        finally:
            signal.signal(signal.SIGINT, old_sig_int)
            if result.reason == Reason.ABORT:
                raise KeyboardInterrupt()  # pylint: disable-msg=W1010

        time_end = datetime.now()
        time_delta = time_end - time_start

        print('*** END TIME: %s ***' % (time_end.strftime("%Y-%m-%d %H:%M:%S")), file=result.environment.log)
        print('*** TEST DURATION (H:MM:SS.ms): %s ***' % (time_delta), file=result.environment.log)
        print('*** END *** %d ***' % (result.result,), file=result.environment.log)
        result.environment.log.flush()

        result.duration = time_delta.total_seconds() * 1000
        TestCase.logger.info('Test %r using %s in %s returned %s in %s ms', cmd, self.exe, dirname, result.result, result.duration)

        result.reason = self._translate_result(result)


class TestResult:
    """Test result from running a test case."""

    def __init__(self, case: TestCase, environment: TestEnvironment) -> None:
        self.case = case
        self.environment = environment
        self.result = -1
        self.reason = Reason.UNKNOWN
        self.duration = 0.0
        self.artifacts: dict[str, tuple[str, Any]] = {}
        self.condition: bool | None = None
        self.is_pytest = False

    def dump(self, stream: IO[str] = sys.stdout) -> None:
        """Dump test result data."""
        print('Case: %s' % (self.case.uid,), file=stream)
        print('Environment: %s' % (self.environment.hostname,), file=stream)
        print('Result: %d' % (self.result,), file=stream)
        print('Reason: %s (%d) %s' % (self.reason, int(self.reason), self.reason.eofs), file=stream)
        print('Duration: %d' % (self.duration or 0,), file=stream)
        for (key, (mime, content)) in self.artifacts.items():
            print('Artifact[%s]: %s %r' % (key, mime, content))

    def attach(self, key: str, mime: str, content: Any) -> None:
        """Attach artifact 'content' of mime-type 'mime'."""
        self.artifacts[key] = (mime, content)

    def check(self) -> bool:
        """Test conditions to run test."""
        conditions = self.case.check(self.environment)
        self.attach('check', 'python', conditions)
        self.condition = reduce(and_, (bool(_) for _ in conditions), True)
        reasons = [c.reason for c in conditions if c.reason is not None] + [Reason.UNKNOWN]
        self.reason = reasons[0]
        return self.condition

    def run(self) -> TestResult:
        """Return test."""
        if self.condition is None:
            self.check()
        if self.condition:
            self.case.run(self)
        else:
            self.result = int(Reason.SKIP)
        return self


class TestFormatInterface:  # pylint: disable-msg=R0921
    """Format UCS Test result."""

    def __init__(self, stream: IO[str] = sys.stdout) -> None:
        self.stream: IO[str] = stream
        self.environment: TestEnvironment | None = None
        self.count = 0
        self.section = ''
        self.case: TestCase | None = None
        self.prefix = ''

    def begin_run(self, environment: TestEnvironment, count: int = 1) -> None:
        """Called before first test."""
        self.environment = environment
        self.count = count

    def begin_section(self, section: str) -> None:
        """Called before each section."""
        self.section = section

    def begin_test(self, case: TestCase, prefix: str = '') -> None:
        """Called before each test."""
        self.case = case
        self.prefix = prefix

    def end_test(self, result: TestResult) -> None:
        """Called after each test."""
        self.case = None
        self.prefix = ''

    def end_section(self) -> None:
        """Called after each section."""
        self.section = ''

    def end_run(self) -> None:
        """Called after all test."""
        self.environment = None
        self.count = 0

    def format(self, result: TestResult) -> None:
        """Format single test."""
        raise NotImplementedError()


def __run_test(filename: str) -> None:
    """Run local test."""
    test_env = TestEnvironment()
    # test_env.dump()
    test_case = TestCase(filename).load()
    # try:
    #     test_case.check(te)
    # except TestConditionError, ex:
    #     for msg in ex:
    #         print msg
    test_result = TestResult(test_case, test_env)
    test_result.dump()


if __name__ == '__main__':
    import doctest
    doctest.testmod()
    # __run_test('tst3')
