#!/usr/bin/python3
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

"""Tool for updating local system"""

from __future__ import annotations

import os
import re
import sys
from argparse import SUPPRESS, ArgumentParser, Namespace
from datetime import datetime
from errno import ENOENT
from subprocess import DEVNULL, call
from textwrap import dedent, wrap
from typing import IO, TYPE_CHECKING, Literal, NoReturn


try:
    import univention.debug as ud
except ImportError:
    import univention.debug2 as ud  # type: ignore

from univention.admindiary.client import write_event
from univention.admindiary.events import UPDATE_FINISHED_FAILURE, UPDATE_FINISHED_SUCCESS, UPDATE_STARTED
from univention.config_registry import ConfigRegistry
from univention.lib.ucs import UCS_Version
from univention.updater.commands import cmd_dist_upgrade, cmd_update
from univention.updater.errors import (
    ConfigurationError, DownloadError, PreconditionError, RequiredComponentError, VerificationError,
)
from univention.updater.locking import UpdaterLock, apt_lock
from univention.updater.tools import Component, LocalUpdater, UniventionUpdater  # noqa: F401


if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


_ESRC = Literal["SETTINGS", "PREPARATION", "PREUP", "UPDATE", "POSTUP"]
_CMDS = Literal["local", "net"]


# TODO:
#   * check the local repository path /var/lib/univention-reposiotry
#   * changed variable update/server to repository/online/server

FN_STATUS = '/var/lib/univention-updater/univention-updater.status'
failure = '/var/lib/univention-updater/update-failed'
reboot_required = '/run/univention-updater-reboot'
TMPSOURCE = '/etc/apt/sources.list.d/00_ucs_temporary_installation.list'
TMPSOURCE2 = '/etc/apt/sources.list.d/00_ucs_update_in_progress.list'

LOGNAME = '/var/log/univention/updater.log'
fd_log: IO[str] = sys.stderr
stdout_orig = sys.stdout
nostdout = False

updater_status: dict[str, str] = {}

RE_APT = re.compile(
    r"""
    ^deb(?:-src)?
    \s+
    (?:\[ [^]]* \]\s*)?
    ([a-z][a-z0-9+.-]*)
    :
    """, re.VERBOSE)


class UpdateError(Exception):
    """
    Exception to signal errors on update.

    :param msg: Human readable message.
    :param errorsource: One of 'SETTINGS', 'PREPARATION', 'PREUP', 'UPDATE', 'POSTUP'
    """

    def __init__(self, msg: str, errorsource: _ESRC) -> None:
        Exception.__init__(self, msg)
        self.errorsource = errorsource


def log(str: str) -> None:
    """Log message to LOGNAME."""
    print(str, file=fd_log)
    fd_log.flush()


def dprint(str: object) -> None:
    """Print message to stdout and LOGNAME."""
    for fd in (stdout_orig, fd_log)[nostdout:]:
        print(str, file=fd)
        fd.flush()


def update_status(**kwargs: str) -> None:
    """
    update updater_status and write status to disk

    Keys:
    - current_version ==> UCS_Version ==> 2.3-1
    - next_version    ==> UCS_Version ==> 2.3-2
    - target_version  ==> UCS_Version ==> 2.4-0
    - type            ==> (LOCAL|NET)
    - status          ==> (RUNNING|FAILED|DONE)
    - phase           ==> (PREPARATION|PREUP|UPDATE|POSTUP)     ==> only valid if status=RUNNING
    - errorsource     ==> (SETTINGS|PREPARATION|PREUP|UPDATE|POSTUP)
    """
    updater_status.update(kwargs)
    if updater_status.get('status') != 'RUNNING':
        updater_status.pop('phase', None)
    # write temporary file
    fn = '%s.new' % FN_STATUS
    try:
        with open(fn, 'w+') as fd:
            fd.writelines('%s=%s\n' % (key, val) for key, val in updater_status.items())
        os.rename(fn, FN_STATUS)
    except OSError as ex:
        dprint('Warning: cannot update status: %s' % (ex,))


def get_status() -> dict[str, str]:
    """
    Read Updater status from file.

    :returns: Dictionary with status

    .. seealso::
        :py:func:`update_status`
    """
    status: dict[str, str] = {}
    try:
        with open(FN_STATUS) as fd:
            for line in fd:
                try:
                    key, value = line.rstrip().split('=', 1)
                except ValueError:
                    continue
                status[key] = value
    except OSError:
        pass
    return status


def remove_temporary_sources_list() -> None:
    """Add the temporary sources.list."""
    for fn in (TMPSOURCE, TMPSOURCE2):
        try:
            os.remove(fn)
        except OSError as ex:
            if ex.errno != ENOENT:
                raise


def add_temporary_sources_list(temporary_sources_list: Iterable[str]) -> None:
    """Add line to a temporary sources.list."""
    remove_temporary_sources_list()
    with open(TMPSOURCE, 'w') as fp:
        for entry in temporary_sources_list:
            print(entry, file=fp)


def update_available(opt: Namespace, ucr: ConfigRegistry) -> tuple[UniventionUpdater, UCS_Version | None]:
    """
    Checks if there is an update available.
    Returns the next version, or None if up-to-date, or throws an UpdateError if the next version can not be identified.
    """
    log(f'--->DBG:update_available(mode={opt.mode})')

    if opt.mode == 'local':
        return update_local(opt, ucr)
    elif opt.mode == 'net':
        return update_net(opt, ucr)
    else:
        raise ValueError(opt.mode)


def update_local(opt: Namespace, ucr: ConfigRegistry) -> tuple[UniventionUpdater, UCS_Version | None]:
    dprint('Checking local repository')
    updater = LocalUpdater()
    try:
        assert updater.server.access(None, '')
        nextversion = updater.release_update_available(errorsto='exception')
    except DownloadError:
        raise UpdateError(
            'A local repository was not found.\n'
            '       Please check the UCR variable repository/mirror/basepath\n'
            '       or try to install via "univention-updater net"', errorsource='SETTINGS')

    return updater, nextversion


def update_net(opt: Namespace, ucr: ConfigRegistry) -> tuple[UniventionUpdater, UCS_Version | None]:
    dprint('Checking network repository')
    try:
        updater = UniventionUpdater()
        nextversion = updater.release_update_available(errorsto='exception')
    except RequiredComponentError:
        raise
    except ConfigurationError as ex:
        raise UpdateError('The configured repository is unavailable: %s' % (ex,), errorsource='SETTINGS')

    return (updater, nextversion)


def update_ucr_updatestatus() -> None:
    try:
        call(('/usr/share/univention-updater/univention-updater-check',), stdout=DEVNULL, stderr=DEVNULL)
    except OSError:
        dprint('Warning: calling univention-updater-check failed.')


def call_local(opt: Namespace) -> NoReturn:
    """Call updater in "local" mode."""
    cmd = [
        arg for args in (
            [sys.argv[0], 'local'],
            ['--updateto', str(opt.updateto)] if opt.updateto else [],
            ["--no-clean"][:opt.no_clean],
            ["--ignoressh"][:opt.ignoressh],
            ["--ignoreterm"][:opt.ignoreterm],
            ["--ignore-releasenotes"][:opt.ignore_releasenotes],
        ) for arg in args
    ]
    os.execv(sys.argv[0], cmd)  # noqa: S606
    dprint('Fatal: failed to exec: %r' % cmd)
    sys.exit(1)


def parse_args(args: Sequence[str] | None = None) -> Namespace:
    """Parse command line arguments."""
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("--reboot", action="store_true", help=SUPPRESS)  # Deprecated
    parser.add_argument("--updateto", metavar="RELEAASE", type=UCS_Version, help="Upper limit for version")
    parser.add_argument("--no-clean", action="store_true", help="Skip cleaning downloaded package file")

    group = parser.add_argument_group("Non-interactive usage")
    group.add_argument("--ignoressh", action="store_true", help="Skip check for SSH terminal")
    group.add_argument("--ignoreterm", action="store_true", help="Skip check for X11 Terminal")
    group.add_argument("--ignore-releasenotes", action="store_true", help="Skip showing release notes")
    group.add_argument("--noninteractive", action="store_true", help="Do not ask interactive questions")

    group = parser.add_argument_group("Verbosity options")
    group.add_argument("--silent", action="store_true", help="No output to STDOUT")
    group.add_argument("--verbose", "-v", action="count", default=2, help="Increase verbosity")

    parser.add_argument("--check", action="store_true", help="Check if system is up-to-date")
    parser.add_argument("mode", choices=("local", "net"), help="Update source")

    return parser.parse_args(args)


def setup_logging(opt: Namespace, ucr: ConfigRegistry) -> IO[str]:
    ud.init(LOGNAME, 0, 0)
    try:
        loglevel = int(ucr.get('update/debug/level', opt.verbose))
    except ValueError:
        loglevel = opt.verbose
    ud.set_level(ud.NETWORK, loglevel)

    if opt.silent:
        global nostdout
        nostdout = True

    return open(LOGNAME, 'a+')


def check(opt: Namespace, ucr: ConfigRegistry) -> bool:
    """Return pending update status."""
    try:
        _updater, nextversion = update_available(opt, ucr)
        if nextversion:
            dprint('Next version is %s' % nextversion)
            return True
    except UpdateError as msg:
        dprint("Error: %s" % msg)
        print('Error: Please check "%s" for details.' % LOGNAME, file=sys.stderr)
        # Errors are handled as "update currently no available"
    except RequiredComponentError as ex:
        dprint("%s" % ex)
    else:
        dprint('System is up to date')  # Sync with /etc/cron.d/univention-maintenance
    return False


def find(opt: Namespace, ucr: ConfigRegistry) -> tuple[UniventionUpdater, UCS_Version] | None:
    lastversion = '%(version/version)s-%(version/patchlevel)s' % ucr
    log('**** Starting univention-updater %s with parameter=%s' % (lastversion, sys.argv))

    # Bug #51880: if last postup.sh failed
    last_status = get_status()
    if last_status.get('status') == 'FAILED' and last_status.get('errorsource') == 'POSTUP':
        dprint("ERROR: The postup.sh of the last update was not executed successfully.")
        dprint("       Please check https://help.univention.com/t/what-to-do-if-postup-failed/15885 for further information.")
        dprint("       The update can be started after the postup.sh has been successfully re-executed and ")
        dprint("       /var/lib/univention-updater/univention-updater.status has been removed.")
        sys.exit(1)

    update_status(current_version=lastversion, type=opt.mode.upper(), status='RUNNING', phase='PREPARATION')

    updater, nextversion = update_available(opt, ucr)
    if not nextversion:
        dprint('System is up to date (UCS %s)' % lastversion)
        return None

    if opt.updateto and nextversion > opt.updateto:
        dprint('Update hold at %s, next %s is after %s' % (lastversion, nextversion, opt.updateto))
        return None

    return (updater, nextversion)


def run(opt: Namespace, ucr: ConfigRegistry, updater: UniventionUpdater, nextversion: UCS_Version) -> None:

    if opt.noninteractive:
        opt.ignore_releasenotes = True
        os.environ['UCS_FRONTEND'] = 'noninteractive'
        with open(os.path.devnull) as null:
            os.dup2(null.fileno(), sys.stdin.fileno())

    dprint('Update to = %s' % nextversion)
    update_status(next_version=nextversion)
    if opt.updateto:
        update_status(target_version=opt.updateto)

    if opt.ignore_releasenotes:
        os.environ['update_warning_releasenotes_internal'] = 'no'
    if opt.ignoressh:
        os.environ['update%d%d_ignoressh' % nextversion.mm] = 'yes'
    if opt.ignoreterm:
        os.environ['update%d%d_ignoreterm' % nextversion.mm] = 'yes'

    add_temporary_sources_list(updater.release_update_temporary_sources_list(nextversion))
    try:
        phase = 'preup'
        update_status(phase='PREUP')

        scripts = updater.get_sh_files(nextversion, nextversion)
        for phase, order in updater.call_sh_files(scripts, LOGNAME, str(nextversion)):
            # do not switch back and forth between PRE and UPDATE phase resp. UPDATE and POST phase.
            if (phase, order) not in (
                    ('update', 'pre'),
                    ('update', 'post'),
            ):
                update_status(phase=phase.upper())

            if (phase, order) == ('update', 'pre'):
                log('**** Downloading scripts at %s' % datetime.now().ctime())
            elif (phase, order) == ('preup', 'pre'):
                log('**** Starting actual update at %s' % datetime.now().ctime())
            elif (phase, order) == ('update', 'main'):
                with apt_lock():
                    if call(cmd_update, shell=True, stdout=fd_log, stderr=fd_log):
                        raise UpdateError('Failed to execute "%s"' % cmd_update, errorsource='UPDATE')

                context_id = write_event(UPDATE_STARTED, {'hostname': ucr.get('hostname')})
                if context_id:
                    os.environ['ADMINDIARY_CONTEXT'] = context_id

                # Used by ../univention-maintenance-mode/univention-maintenance-mode-update-progress
                detailed_status = FN_STATUS + '.details'
                with apt_lock(), open(detailed_status, 'w+b') as detailed_status_fd:
                    fno = detailed_status_fd.fileno()
                    env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
                    cmd2 = "%s -o APT::Status-FD=%s" % (cmd_dist_upgrade, fno)
                    resultCode = call(cmd2, shell=True, stdout=fd_log, stderr=fd_log, env=env, pass_fds=(fno,))
                    if os.path.exists(detailed_status):
                        os.unlink(detailed_status)
                    if resultCode != 0:
                        raise UpdateError('Failed to execute "%s"' % cmd_dist_upgrade, errorsource='UPDATE')
            elif (phase, order) == ('postup', 'main'):
                # Bug #23202: After an update of Python ucr.handler_set() may not work any more
                cmd = [
                    'univention-config-registry', 'set',
                    f'version/version={nextversion.FORMAT % nextversion}',
                    f'version/patchlevel={nextversion.patchlevel}',
                ]
                call(cmd, stdout=fd_log, stderr=fd_log)

    except BaseException:
        if phase == 'preup' or (phase == 'update' and order == 'pre'):
            remove_temporary_sources_list()
        raise

    remove_temporary_sources_list()

    if os.path.exists('/usr/sbin/univention-pkgdb-scan'):
        call(['/usr/sbin/univention-pkgdb-scan'], stdout=fd_log, stderr=fd_log)

    if not opt.no_clean:
        call(['apt-get', 'clean'])

    call(['touch', reboot_required])
    write_event(UPDATE_FINISHED_SUCCESS, {'hostname': ucr.get('hostname'), 'version': 'UCS %(version/version)s-%(version/patchlevel)s errata%(version/erratalevel)s' % ucr})


def main() -> None:

    # PATH does not contain */sbin when called from cron
    os.environ['PATH'] = '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'

    opt = parse_args()

    ucr = ConfigRegistry()
    ucr.load()

    global fd_log
    with setup_logging(opt, ucr) as fd_log:
        try:
            try:
                with UpdaterLock():
                    if opt.check:
                        sys.exit(check(opt, ucr))

                    ret = find(opt, ucr)
                    if ret:
                        run(opt, ucr, ret[0], ret[1])

                    update_status(status='DONE')
                    if os.path.exists(failure):
                        os.unlink(failure)

                    if ret:
                        os.execv(sys.argv[0], sys.argv)  # noqa: S606
            except VerificationError as ex:
                msg = '\n'.join([
                    "Update aborted due to verification error:", "%s" % (ex,), *wrap(
                        dedent("                    This can and should only be disabled temporarily\n                    using the UCR variable 'repository/online/verify'.\n                    "),
                    ),
                ])
                raise UpdateError(msg, errorsource='SETTINGS')
            except ConfigurationError as e:
                msg = 'Update aborted due to configuration error: %s' % e
                raise UpdateError(msg, errorsource='SETTINGS')
            except RequiredComponentError as ex:
                update_status(status='DONE', errorsource='PREPARATION')
                dprint(ex)
            except PreconditionError as ex:
                (phase, order, component, _script) = ex.args
                if phase == 'preup':
                    phase = 'pre-update'
                    errorsource: _ESRC = 'PREUP'
                elif phase == 'postup':
                    phase = 'post-update'
                    errorsource = 'POSTUP'
                else:
                    errorsource = 'UPDATE'

                if order == 'main':
                    order = 'release %s' % component
                elif order == 'pre':
                    order = 'component %s before calling release script' % component
                elif order == 'post':
                    order = 'component %s after calling release script' % component

                msg = 'Update aborted by %s script of %s' % (phase, order)
                raise UpdateError(msg, errorsource=errorsource)

            update_ucr_updatestatus()

        except UpdateError as msg:
            write_event(UPDATE_FINISHED_FAILURE, {'hostname': ucr.get('hostname')})
            update_status(status='FAILED', errorsource=msg.errorsource)
            dprint("Error: %s" % msg)
            call(['touch', failure])
            sys.exit('Error: Please check "%s" for details.' % LOGNAME)
        except KeyboardInterrupt:
            update_status(status='FAILED')
            dprint("\nUpdate aborted by user (ctrl-c)\n")
            sys.exit(1)


if __name__ == '__main__':
    main()
