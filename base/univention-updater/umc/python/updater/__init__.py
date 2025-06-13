#!/usr/bin/python3
#
# Univention Management Console
#  module: updater
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2011-2025 Univention GmbH
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

import importlib.util
import os
from collections.abc import Callable, Iterable
from datetime import datetime
from hashlib import md5
from os import getpid, stat
from shlex import quote
from time import time
from traceback import format_exc
from typing import TYPE_CHECKING, Any

import psutil
from apt import Cache

from univention.lib import atjobs
from univention.lib.i18n import Translation
from univention.management.console.config import ucr
from univention.management.console.log import MODULE
from univention.management.console.modules import Base, UMC_Error
from univention.management.console.modules.decorators import sanitize, simple_response, threaded
from univention.management.console.modules.sanitizers import (
    ChoicesSanitizer, IntegerSanitizer, ListSanitizer, StringSanitizer,
)
from univention.updater.errors import RequiredComponentError
from univention.updater.tools import UniventionUpdater


if TYPE_CHECKING:
    from types import ModuleType


_ = Translation('univention-management-console-module-updater').translate

# the file whose file time is used as the 'serial' value for the 'Components' grid.
COMPONENTS_SERIAL_FILE = '/etc/apt/sources.list.d/20_ucs-online-component.list'

HOOK_DIRECTORY = '/usr/share/univention-updater/hooks'

INSTALLERS = {
    'release': {
        'purpose': _("Release update to version %s"),
        'command': "/usr/share/univention-updater/univention-updater net --updateto %s --ignoressh --ignoreterm",
        'prejob': 'ucr set updater/maintenance=true',
        'postjob': 'ucr set updater/maintenance=false',
        'logfile': '/var/log/univention/updater.log',
        'statusfile': '/var/lib/univention-updater/univention-updater.status',
    },
    'distupgrade': {
        'purpose': _("Package update"),
        'command': "/usr/share/univention-updater/univention-updater-umc-dist-upgrade; /usr/share/univention-updater/univention-updater-check",
        'prejob': '/usr/share/univention-updater/disable-apache2-umc',
        'postjob': '/usr/share/univention-updater/enable-apache2-umc --no-restart',
        'logfile': '/var/log/univention/updater.log',
        'statusfile': '/var/lib/univention-updater/umc-dist-upgrade.status',
    },
}


class Watched_File:
    """
    A class that takes a file name and watches changes to this file.
    We don't use any advanced technologies (FAM, inotify etc.) but
    rather basic 'stat' calls, monitoring mtime and size.
    """

    def __init__(self, path: str, count: int = 2) -> None:
        self._file = path
        self._count = count

        self._last_returned_stamp = 0  # the last result we returned to the caller. will be returned as long as there are not enough changes.

        self._unchanged_count = 0  # incremented if size and timestamp didn't change

        self._last_stamp = 0  # last timestamp we've seen
        self._last_size = 0  # last size we've seen
        self._last_md5 = ''

    def timestamp(self) -> int:
        """
        Main function. returns the current timestamp whenever size or mtime
        have changed. Defers returning the new value until changes have
        settled down, e.g. until the same values have appeared 'count' times.
        """
        current_stamp = 0
        current_size = 0
        st = stat(self._file)
        if st:
            current_stamp = int(st.st_mtime)
            current_size = st.st_size
            # Fake a changed mtime if size is different. Subsequent processing
            # only depends on the mtime field.
            if current_size != self._last_size:
                current_stamp = int(time())
                MODULE.info("Size of '%s': %s -> %s" % (self._file, self._last_size, current_size))
                self._last_size = current_size

        if current_stamp == self._last_stamp:
            self._unchanged_count += 1
            if self._unchanged_count >= self._count:
                # Don't record new timestamp if MD5 of file is the same
                try:
                    with open(self._file, 'rb') as fd:
                        hash_ = md5(fd.read()).hexdigest()
                except OSError:
                    pass
                else:
                    if hash_ != self._last_md5:
                        self._last_md5 = hash_
                        self._last_returned_stamp = current_stamp
                    else:
                        MODULE.info("Hash of '%s' unchanged" % self._file)
        else:
            self._unchanged_count = 0
            self._last_stamp = current_stamp

        return self._last_returned_stamp


class Watched_Files:
    """Convenience class to monitor more than one file at a time."""

    def __init__(self, files: Iterable[str], count: int = 2) -> None:
        self._count = count
        self._files = [Watched_File(f, 0) for f in files]
        self._last_returned_stamp = 0  # the last result we returned to the caller. will be returned as long as there are not enough changes.
        self._unchanged_count = 0  # incremented if size and timestamp didn't change
        self._last_stamp = 0  # last timestamp we've seen

    def timestamp(self) -> int:
        latest = max(f.timestamp() for f in self._files)
        if latest == self._last_stamp:
            self._unchanged_count += 1
            if self._unchanged_count >= self._count:
                self._last_returned_stamp = latest
        else:
            self._unchanged_count = 0
            self._last_stamp = latest

        return self._last_returned_stamp


class Instance(Base):

    def init(self) -> None:
        MODULE.info("Initializing 'updater' module (PID = %d)" % (getpid(),))
        self._current_job = ''
        self._logfile_start_line = 0
        self._serial_file = Watched_File(COMPONENTS_SERIAL_FILE)
        try:
            self.uu = UniventionUpdater(False)
        except Exception as exc:  # FIXME: let it raise
            self.uu = None
            MODULE.error("init() ERROR: %s" % (exc,))

    @simple_response
    def query_maintenance_information(self) -> dict[str, Any]:
        ret = self._maintenance_information()
        ret.update(self._last_update())
        return ret

    def _last_update(self) -> dict[str, Any]:
        status_file = '/var/lib/univention-updater/univention-updater.status'
        ret: dict[str, Any] = {'last_update_failed': False, 'last_update_version': None}
        try:
            fstat = stat(status_file)
            mtime = datetime.fromtimestamp(fstat.st_mtime)
            delta = datetime.now() - mtime
            if delta.days != 0:  # no fresh failure
                return ret

            with open(status_file) as fd:
                info: dict[str, str] = dict(
                    line.strip().split('=', 1)  # type: ignore
                    for line in fd
                )

            ret['last_update_failed'] = info.get('status') == 'FAILED'
            if ret['last_update_failed']:
                ret['last_update_version'] = info.get('next_version')
        except (OSError, ValueError) as exc:
            MODULE.error(str(exc))

        return ret

    def _maintenance_information(self) -> dict[str, Any]:
        default = {'show_warning': False}
        if not self.uu:
            return default

        ucr.load()
        if ucr.is_true('license/extended_maintenance/disable_warning'):
            return default

        version = self.uu.current_version
        for _ver, data in self.uu.get_releases(version, version):
            status = data.get('status', 'unmaintained')

            maintenance_extended = status == 'extended'
            show_warning = maintenance_extended or status != 'maintained'

            return {
                'ucs_version': str(version),
                'show_warning': show_warning,
                'maintenance_extended': maintenance_extended,
                'base_dn': ucr.get('license/base'),
            }

        return default

    @simple_response
    def query_releases(self) -> list[dict[str, str]]:
        """
        Returns a list of system releases suitable for the
        corresponding ComboBox
        """
        # be as current as possible.
        self.uu.ucr_reinit()
        ucr.load()

        appliance_mode = ucr.is_true('server/appliance')

        available_versions, blocking_components = self.uu.get_all_available_release_updates()
        result = [{'id': str(rel), 'label': 'UCS %s' % (rel,)} for rel in available_versions]
        #
        # appliance_mode=no ; blocking_comp=no  → add "latest version"
        # appliance_mode=no ; blocking_comp=yes →  no "latest version"
        # appliance_mode=yes; blocking_comp=no  → add "latest version"
        # appliance_mode=yes; blocking_comp=yes → add "latest version"
        #
        if result and (appliance_mode or not blocking_components):
            # UniventionUpdater returns available version in ascending order, so
            # the last returned entry is the one to be flagged as 'latest' if there's
            # no blocking component.
            result[-1]['label'] = '%s (%s)' % (result[-1]['label'], _('latest version'))

        return result

    @sanitize(
        hooks=ListSanitizer(StringSanitizer(minimum=1), required=True),
    )
    @threaded
    def call_hooks(self, request) -> Any:
        """Calls the specified hooks and returns data given back by each hook"""
        result = {}
        hookmanager = HookManager(HOOK_DIRECTORY)  # , raise_exceptions=False
        hooks = request.options['hooks']
        MODULE.info('requested hooks: %s' % (hooks,))
        for hookname in hooks:
            MODULE.info('calling hook %s' % hookname)
            result[hookname] = hookmanager.call_hook(hookname)

        MODULE.info('result: %r' % (result,))
        return result

    @simple_response
    def updates_check(self) -> dict[str, list[tuple[str, str]]]:
        """
        Returns the list of packages to be updated/installed
        by a dist-upgrade.
        """
        install = []
        update = []
        remove = []

        apt = Cache(memonly=True)
        apt.update()
        apt.open()
        apt.clear()
        apt.upgrade(dist_upgrade=True)
        for pkg in apt.get_changes():
            if pkg.marked_install:
                assert pkg.candidate is not None
                install.append((pkg.name, pkg.candidate.version))
            if pkg.marked_upgrade:
                assert pkg.candidate is not None
                update.append((pkg.name, pkg.candidate.version))
            if pkg.marked_delete:
                assert pkg.installed is not None
                remove.append((pkg.name, pkg.installed.version))

        return {
            "update": sorted(update),
            "install": sorted(install),
            "remove": sorted(remove),
        }

    @simple_response
    def updates_available(self) -> bool:
        """
        Asks if there are package updates available. (don't get confused
        by the name of the UniventionUpdater function that is called here.)
        This is a separate call since it can take an amount of time, thus
        being invoked by a separate button (and not in the background)
        """
        ucr.load()
        try:
            # be as current as possible.
            what = 'reinitializing UniventionUpdater'
            self.uu.ucr_reinit()

            what = 'checking update availability'
            new, upgrade, removed = self.uu.component_update_get_packages()
            return any((new, upgrade, removed))
        except Exception as ex:
            typ = str(type(ex)).strip('<>')
            msg = '[while %s] [%s] %s' % (what, typ, str(ex))
            MODULE.error(msg)
        return False

    def status(self, request) -> None:  # TODO: remove unneeded things
        """One call for all single-value variables."""
        result: dict[str, Any] = {}
        ucr.load()

        try:
            result['erratalevel'] = int(ucr.get('version/erratalevel', 0))
        except ValueError:
            result['erratalevel'] = 0

        result['appliance_mode'] = ucr.is_true('server/appliance')
        result['timestamp'] = int(time())
        result['reboot_required'] = ucr.is_true('update/reboot/required', False)

        try:
            # be as current as possible.
            what = 'reinitializing UniventionUpdater'
            self.uu.ucr_reinit()

            what = 'getting UCS version'
            result['ucs_version'] = str(self.uu.current_version)

            # if nothing is returned -> convert to empty string.
            what = 'querying available release updates'
            try:
                ver = self.uu.release_update_available(errorsto='exception')
                result['release_update_available'] = '' if ver is None else str(ver)
            except RequiredComponentError as exc:
                result['release_update_available'] = exc.version

            what = 'querying update-blocking components'
            blocking_components = self.uu.get_all_available_release_updates()[1] or set()
            # check apps
            if result['release_update_available']:
                try:
                    from univention.appcenter.actions import get_action
                    update_check = get_action('update-check')
                    if update_check:
                        blocking_apps = update_check.get_blocking_apps(ucs_version=result['release_update_available'])
                        if blocking_apps:
                            blocking_components.update(set(blocking_apps))
                except (ImportError, ValueError):
                    # the new univention.appcenter package is not installed.
                    # Cannot be a dependency as the app center depends on updater...
                    raise UMC_Error(_('Error checking if installed apps are available for next UCS version.'))

            result['release_update_blocking_components'] = ' '.join(blocking_components)

            # Component counts are now part of the general 'status' data.
            what = "counting components"  # noqa: F841
            components = [bool(comp) for comp in self.uu.get_components(all=True)]
            result['components'] = len(components)
            result['enabled'] = sum(components)

            # HACK: the 'Updates' form polls on the serial file
            #       to refresh itself. Including the serial value
            #       into the form helps us to have a dependent field
            #       that can trigger the refresh of the "Releases"
            #       combobox and the 'package updates available' field.
            result['serial'] = self._serial_file.timestamp()

        except Exception as exc:  # FIXME: don't catch everything
            raise UMC_Error("%s %s %s" % (
                _('Error contacting the update server. Please check your proxy or firewall settings, if any. Or it may be a problem with your configured DNS server.'),
                _('This is the error message:'),
                exc,
            ), traceback=format_exc())

        self.finished(request.id, [result])

    @simple_response
    def running(self) -> str:
        """
        Returns the id (key into INSTALLERS) of a currently
        running job, or the empty string if nothing is running.
        """
        return self.__which_job_is_running()

    @sanitize(
        job=ChoicesSanitizer([*list(INSTALLERS), ''], required=True),
        count=IntegerSanitizer(default=0),
    )
    @simple_response
    def updater_log_file(self, job: str, count: int) -> float | list[str] | None:
        """
        returns the content of the log file associated with
        the job.

        :param job: Job name.
        :param count: has the same meaning as already known:
                <0 ...... return timestamp of file (for polling)
                0 ....... return whole file as a string list
                >0 ...... ignore this many lines, return the rest of the file

        .. note::
                As soon as we have looked for a running job at least once,
                we know the job key and can associate it here.

        TODO: honor a given 'job' argument
        """
        job = self._current_job or job

        if not job:
            return None

        fname = INSTALLERS[job]['logfile']
        if count < 0:
            try:
                return stat(fname).st_ctime
            except OSError:
                return 0

        # don't read complete file if we have an 'ignore' count
        count += self._logfile_start_line
        return self._logview(fname, -count)

    def _logview(self, fname: str, count: int) -> list[str]:
        """
        Contains all functions needed to view or 'tail' an arbitrary text file.

        :param count: can have different values:
                < 0 ... ignore this many lines, return the rest of the file
                0 ..... return the whole file, split into lines.
                > 0 ... return the last 'count' lines of the file. (a.k.a. tail -n <count>)
        """
        lines = []
        try:
            with open(fname, 'rb') as fd:
                for line in fd:
                    if (count < 0):
                        count += 1
                    else:
                        lines.append(line.rstrip().decode('utf-8', 'replace'))
                        if (count > 0) and (len(lines) > count):
                            lines.pop(0)
        except OSError:
            pass
        return lines

    @sanitize(
        job=ChoicesSanitizer(INSTALLERS, required=True),
    )
    @simple_response
    def updater_job_status(self, job: str) -> dict[str, Any]:  # TODO: remove this completely
        """Returns the status of the current/last update even if the job is not running anymore."""
        result: dict[str, Any] = {}
        try:
            with open(INSTALLERS[job]['statusfile']) as fd:
                for line in fd:
                    fields = line.strip().split('=')
                    if len(fields) == 2:
                        result['_%s_' % fields[0]] = fields[1]
        except OSError:
            pass

        result['running'] = self.__which_job_is_running() != ''
        return result

    @sanitize(
        job=ChoicesSanitizer(INSTALLERS, required=True),
        detail=StringSanitizer(r'^[A-Za-z0-9\.\- ]*$'),
    )
    @simple_response
    def run_installer(self, job: str, detail: str = '') -> dict[str, int]:
        """
        This is the function that invokes any kind of installer. Arguments accepted:

        :param job: ..... the main thing to do. can be one of:
                'release' ...... perform a release update
                'distupgrade' .. update all currently installed packages (distupgrade)

        :param detail: ....... an argument that specifies the subject of the installer:
                for 'release' .... the target release number,
                for all other subjects: detail has no meaning.
        """
        MODULE.info("Starting function %r" % (job,))
        self._current_job = job
        spec = INSTALLERS[job]

        # remember initial lines of logfile before starting update to not show it in the frontend
        logfile = spec['logfile']
        try:
            with open(logfile, 'rb') as fd:
                self._logfile_start_line = sum(1 for line in fd)
        except OSError:
            pass

        command = spec['command']
        if '%' in command:
            command = command % (quote(detail).translate({0: None, 10: None, 13: None}),)
        MODULE.info("Creating job: %r" % (command,))
        command = '''
%s
%s < /dev/null
%s''' % (spec["prejob"], command, spec["postjob"])
        atjobs.add(command, comments={"lines": self._logfile_start_line})

        return {'status': 0}

    def __which_job_is_running(self) -> str:
        # first check running at jobs
        for atjob in atjobs.list(True):
            for job, inst in INSTALLERS.items():
                cmd = inst['command'].split('%')[0]
                if cmd in atjob.command:
                    self._current_job = job
                    try:
                        self._logfile_start_line = int(atjob.comments.get('lines', 0))
                    except ValueError:
                        pass
                    return job
        # no atjob found, parse process list (if univention-upgrade was started via CLI)
        commands = [
            ('/usr/share/univention-updater/univention-updater-umc-dist-upgrade', 'distupgrade'),
            ('/usr/share/univention-updater/univention-updater', 'release'),
            ('/usr/sbin/univention-upgrade', 'distupgrade'),  # we don't know if it is a dist-upgrade or a release upgrade
        ]
        for cmd, job in commands:
            for process in psutil.process_iter():
                try:
                    cmdline = process.cmdline() if callable(process.cmdline) else process.cmdline
                except psutil.NoSuchProcess:
                    pass

                if cmd in cmdline:
                    self._current_job = job
                    self._logfile_start_line = 0
                    return job
        return ''


class HookManager:
    """
    This class tries to provide a simple interface to load and call hooks within existing code.
    Python modules are loaded from specified `module_dir` and automatically registered.
    These Python modules have to contain at least a global method `register_hooks()` that returns
    a list of tuples (`hook_name`, `callable`).

    Simple hook file example::

            def test_hook(*args, **kwargs):
                    print('1ST_TEST_HOOK:', args, kwargs)
                    return ('Result', 1)

            def other_hook(*args, **kwargs):
                    print('OTHER_HOOK:', args, kwargs)
                    return 'Other result'

            def register_hooks():
                    return [
                            ('test_hook', test_hook),
                            ('pre_hook', other_hook),
                    ]

    The method `call_hook(hookname, *args, **kwargs)` calls all registered methods for specified
    hookname and passes `*args` and `**kwargs` to them. The return value of each method will be
    saved and returned by `call_hook()` as a list. If no method has been registered for
    specified hookname, an empty list will be returned.

    If `raise_exceptions` has been set to `False`, exceptions while loading Python modules will be
    discarded silently. If a hook raises an exception, it will be caught and returned in
    result list of `call_hooks()` instead of corresponding return value. E.g.::

            [['Mein', 'Result', 123], <exceptions.ValueError instance at 0x7f80496f6638>]

    How to use HookManager::

    >>> hm = HookManager(TESTDIR)
    >>> list(hm.get_hook_list())
    ['test_hook', 'pre_hook']
    >>> result = hm.call_hook('test_hook', 'abc', 123, x=1)
    1ST_TEST_HOOK: ('abc', 123) {'x': 1}
    2ND_TEST_HOOK: ('abc', 123) {'x': 1}
    >>> result
    [('Result', 1), ('Result', 2)]
    >>> hm.call_hook('unknown_hook')
    []
    """

    def __init__(self, module_dir: str, raise_exceptions: bool = True) -> None:
        """
        :param module_dir: path to directory that contains Python modules with hook functions
        :param raise_exceptions: if `False`, all exceptions while loading Python modules will be dropped and all exceptions while calling hooks will be caught and returned in result list
        """
        self.__loaded_modules: dict[str, ModuleType] = {}
        self.__registered_hooks: dict[str, list[Callable[..., Any]]] = {}
        self.__module_dir = module_dir
        self.__raise_exceptions = raise_exceptions
        self.__load_hooks()
        self.__register_hooks()

    def __load_hooks(self) -> None:
        """loads all Python modules in specified module directory."""
        if os.path.exists(self.__module_dir) and os.path.isdir(self.__module_dir):
            for f in os.listdir(self.__module_dir):
                if f.endswith('.py') and len(f) > 3:
                    modname = f[0:-3]
                    try:
                        spec = importlib.util.spec_from_file_location(modname, os.path.join(self.__module_dir, f))
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)  # type: ignore
                        self.__loaded_modules[modname] = module
                    except Exception:
                        if self.__raise_exceptions:
                            raise

    def __register_hooks(self) -> None:
        for module in self.__loaded_modules.values():
            try:
                hooklist = module.register_hooks()  # type: ignore
                for hookname, func in hooklist:
                    # if returned function is not callable then continue
                    if not callable(func):
                        continue
                    self.__registered_hooks.setdefault(hookname, []).append(func)
            except Exception:
                if self.__raise_exceptions:
                    raise

    def set_raise_exceptions(self, val: bool) -> None:
        """
        Enable or disable raising exceptions.

        :param val: `True` to pass exceptions through, `False` to return them instead of the return value.
        """
        if val in (True, False):
            self.__raise_exceptions = val
        else:
            raise ValueError('boolean value required')

    def get_hook_list(self) -> Iterable[str]:
        """returns a list of hook names that have been defined by loaded Python modules."""
        return self.__registered_hooks.keys()

    def call_hook(self, name: str, *args: Any, **kwargs: Any) -> list[Any]:
        """
        All additional arguments are passed to hook methods.
        If `self.__raise_exceptions` is `False`, all exceptions while calling hooks will be caught and returned in result list.
        If return value is an empty list, no hook has been called.
        """
        result = []
        for func in self.__registered_hooks.get(name, []):
            try:
                res = func(*args, **kwargs)
                result.append(res)
            except Exception as e:
                if self.__raise_exceptions:
                    raise
                else:
                    result.append(e)
        return result
