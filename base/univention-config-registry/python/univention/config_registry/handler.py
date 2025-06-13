#
#  main configuration registry classes
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
#
# API stability :pylint: disable-msg=R0201,W0613,R0903
# Too pedantic  :pylint: disable-msg=W0704
# Rewrite       :pylint: disable-msg=R0912

"""Univention Configuration Registry handlers."""


import errno
import os
import pickle  # noqa: S403
import random
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping
from grp import getgrnam
from pwd import getpwnam
from typing import IO, Any

from univention.config_registry.misc import asciify, directory_files
from univention.debhelper import parseRfc822  # pylint: disable-msg=W0403


_OPT = Mapping[str, Any]
_UCR = Mapping[str, str]
_CHANGES = Mapping[str, tuple[str | None, str | None]]
_ARG = tuple[_UCR, _CHANGES]
_INFO = Mapping[str, list[str]]

__all__ = ['ConfigHandlers']

VARIABLE_PATTERN = re.compile('@%@([^@]+)@%@')
VARIABLE_TOKEN = re.compile('@%@')
EXECUTE_TOKEN = re.compile(b'@!@')
WARNING_PATTERN = re.compile('(UCRWARNING|BCWARNING|UCRWARNING_ASCII)=(.+)')

INFO_DIR = '/etc/univention/templates/info'
FILE_DIR = '/etc/univention/templates/files'
SCRIPT_DIR = '/etc/univention/templates/scripts'
MODULE_DIR = '/etc/univention/templates/modules'

WARNING_TEXT = '''\
Warning: This file is auto-generated and might be overwritten by
         univention-config-registry.
         Please edit the following file(s) instead:
Warnung: Diese Datei wurde automatisch generiert und kann durch
         univention-config-registry ueberschrieben werden.
         Bitte bearbeiten Sie an Stelle dessen die folgende(n) Datei(en):

'''
assert asciify(WARNING_TEXT) == WARNING_TEXT, "Only ASCII allowed in WARNING_TEXT"


def run_filter(template: str, directory: _UCR, srcfiles: Iterable[str] = set(), opts: _OPT = {}) -> bytes:
    """
    Process a template file: substitute variables.

    :param template: Text string of template.
    :param directory: UCR instance.
    :param srcfiles: File names of source template.
    :param opts: Command line options.
    :returns: The modified template with all UCR variables and sections replaced.
    """
    template = _replace_variables(template, directory, srcfiles)

    tmpl = template.encode("UTF-8")

    if opts.get('disallow-execution', False):
        return tmpl

    tmpl = _replace_exec(tmpl)

    return tmpl


def _replace_variables(template: str, directory: _UCR, srcfiles: Iterable[str]) -> str:
    while True:
        i = VARIABLE_TOKEN.finditer(template)
        try:
            start = next(i)
            end = next(i)
            name = template[start.end():end.start()]

            if name in directory:
                value = directory[name]
                if not isinstance(value, str):
                    # Python 2 with unicode value
                    value = value.encode('UTF-8')  # important! template must not be of type unicode ever (in py2), otherwise some characters are lost in the below subprocess stdinput
            else:
                match = WARNING_PATTERN.match(name)
                if match:
                    mode, prefix = match.groups()
                    value = warning_string(prefix, srcfiles=srcfiles)
                    if mode == "UCRWARNING_ASCII":
                        value = asciify(value)
                else:
                    value = ''

            if isinstance(value, list | tuple):
                value = value[0]
            template = template[:start.start()] + value + template[end.end():]
        except StopIteration:
            break

    return template


def _replace_exec(template: bytes) -> bytes:
    while True:
        i = EXECUTE_TOKEN.finditer(template)
        try:
            start = next(i)
            end = next(i)

            proc = subprocess.Popen(
                (sys.executable,),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                close_fds=True)
            value = proc.communicate(b'''\
# -*- coding: utf-8 -*-
import univention.config_registry
configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()
# for compatibility
baseConfig = configRegistry
%s
''' % template[start.end():end.start()])[0]
            template = template[:start.start()] + value + template[end.end():]

        except StopIteration:
            break

    return template


def run_script(script: str, arg: str, changes: _CHANGES) -> None:
    """
    Execute script with command line arguments using a shell and pass changes
    on STDIN.
    For each changed variable a line with the 'name of the variable', the 'old
    value', and the 'new value' are passed separated by '@%@'.

    :param script: File name of the script.
    :param arg: Execution mode, e.g. `generate` or `postinst`.
    :param changes: Dictionary of changed UCR variables, mapping UCR variable names to 2-tuple (old-value, new-value).
    """
    diff = [
        '%s@%%@%s@%%@%s\n' % (key, old, new)
        for (key, (old, new)) in changes.items()
        if old and new
    ]

    cmd = script + " " + arg
    proc = subprocess.Popen(cmd, shell=True, stdin=subprocess.PIPE, close_fds=True)
    proc.communicate(''.join(diff).encode('UTF-8'))


def run_module(modpath: str, fn: str, ucr: _UCR, changes: _CHANGES) -> None:
    """
    Load the Python module that MUST be located in :py:const:`MODULE_DIR` or any
    subdirectory.

    :param modpath: The path to the module relative to :py:const:`MODULE_DIR`.
    :param fn: Execution mode, e.g. `handler` or `preinst` or `postinst`.
    :param ucr: UCR instance.
    :param changes: Dictionary of changed UCR variables, mapping UCR variable names to 2-tuple (old-value, new-value).
    """
    # temporarily prepend MODULE_DIR to load path
    sys.path.insert(0, MODULE_DIR)
    module_name = os.path.splitext(modpath)[0]
    try:
        module = __import__(module_name.replace(os.path.sep, '.'))
        f = getattr(module, fn)
        f(ucr, changes)
    except (AttributeError, ImportError) as ex:
        print(ex, file=sys.stderr)
    del sys.path[0]


def warning_string(prefix: str = '# ', srcfiles: Iterable[str] = set()) -> str:
    """
    Generate UCR warning text.

    :param prefix: String to prepend before each line.
    :param srcfiles: File names of source template.
    :returns: A warning sting based on :py:const:`WARNING_TEXT`.
    """
    res = [
        '%s%s' % (prefix, line)
        for line in WARNING_TEXT.splitlines()
    ] + [
        '%s\t%s' % (prefix, srcfile)
        for srcfile in sorted(srcfiles)
    ] + [
        prefix,
    ]

    return "\n".join(res)


class ConfigHandler:
    """Base class of all config handlers."""

    variables: set[str] = set()

    def __call__(self, args: _ARG) -> None:
        raise NotImplementedError()


class ConfigHandlerDiverting(ConfigHandler):
    """
    File diverting config handler.

    :param to_file: Destination file name.
    """

    def __init__(self, to_file: str) -> None:
        super().__init__()
        self.to_file = os.path.join('/', to_file)
        self.user: int | None = None
        self.group: int | None = None
        self.mode: int | None = None
        self.preinst: str | None = None
        self.postinst: str | None = None

    def __hash__(self):
        """Return unique hash."""
        return hash(self.to_file)

    def __eq__(self, other):
        """Compare this to other handler."""
        if isinstance(other, type(self)):
            return self.to_file == other.to_file
        return NotImplemented

    def __ne__(self, other):
        """Compare this to other handler."""
        if isinstance(other, type(self)):
            return self.to_file != other.to_file
        return NotImplemented

    def _set_perm(self, stat: os.stat_result | None, to_file: str | None = None) -> None:
        """
        Set file permissions.

        :param stat: File status.
        :param to_file: Destination file name.
        """
        if not to_file:
            to_file = self.to_file
        elif self.to_file != to_file:
            try:
                old_stat = os.stat(self.to_file)
                os.chmod(to_file, old_stat.st_mode)
                os.chown(to_file, old_stat.st_uid, old_stat.st_gid)
            except OSError:
                pass

        if self.user or self.group or self.mode:
            if self.mode:
                os.chmod(to_file, self.mode)

            if self.user and self.group:
                os.chown(to_file, self.user, self.group)
            elif self.user:
                os.chown(to_file, self.user, 0)
            elif self.group:
                os.chown(to_file, 0, self.group)
        elif stat:
            os.chmod(to_file, stat.st_mode)

    def _call_silent(self, *cmd: str) -> int:
        """
        Call command with stdin, stdout, and stderr redirected from/to :file:`/dev/null`.

        :param cmd: List of command with arguments.
        :returns: Process exit code.
        """
        with open(os.path.devnull, 'w', encoding='utf-8') as null:
            # tell possibly wrapped dpkg-divert to really do the work
            env = dict(os.environ)
            env['DPKG_MAINTSCRIPT_PACKAGE'] = 'univention-config'
            return subprocess.call(cmd, stdin=null, stdout=null, stderr=null, env=env)

    def need_divert(self) -> bool:
        """Check if diversion is needed."""
        return False

    def install_divert(self) -> None:
        """Prepare file for diversion."""
        deb = '%s.debian' % self.to_file
        self._call_silent('dpkg-divert', '--quiet', '--rename', '--local', '--divert', deb, '--add', self.to_file)
        # Make sure a valid file still exists
        if os.path.exists(deb) and not os.path.exists(self.to_file):
            # Don't use shutil.copy2() which looses file ownership (Bug #22596)
            self._call_silent('cp', '-p', deb, self.to_file)

    def uninstall_divert(self) -> bool:
        """
        Undo diversion of file.

        :returns: `True` because the diversion was removed.
        """
        try:
            os.unlink(self.to_file)
        except OSError:
            pass
        deb = '%s.debian' % self.to_file
        self._call_silent('dpkg-divert', '--quiet', '--rename', '--local', '--divert', deb, '--remove', self.to_file)
        return True

    def _temp_file_name(self) -> str:
        dirname, basename = os.path.split(self.to_file)
        filename = '.%s__ucr__commit__%s' % (basename, random.random())
        return os.path.join(dirname, filename)


class ConfigHandlerMultifile(ConfigHandlerDiverting):
    """
    Handler for multifile.

    :param dummy_from_file: Source file name used to copy file permissions from.
    :param to_file: Destination file name.
    """

    def __init__(self, dummy_from_file: str, to_file: str) -> None:
        super().__init__(to_file)
        self.variables: set[str] = set()
        self.from_files: set[str] = set()
        self.dummy_from_file = dummy_from_file
        self.def_count = 1

    def __setstate__(self, state):
        """Load state upon unpickling."""
        self.__dict__.update(state)
        # may raise AttributeError, which forces UCR to rebuild the cache
        self.def_count  # :pylint: disable-msg=W0104  # noqa: B018

    def add_subfiles(self, subfiles: list[tuple[str, set[str]]]) -> None:
        """
        Add subfiles to multifile.

        :param subfiles: List of 2-tuples (file-name, set-of-variable-names).
        """
        for from_file, variables in subfiles:
            self.from_files.add(from_file)
            self.variables |= variables

    def remove_subfile(self, subfile: str) -> None:
        """
        Remove subfile.

        Removed diversion of set of sub-files becomes empty.
        """
        self.from_files.discard(subfile)
        if not self.need_divert():
            self.uninstall_divert()

    def __call__(self, args: _ARG) -> None:
        """Generate multfile from subfile templates."""
        ucr, changed = args
        print('Multifile: %s' % self.to_file)

        if hasattr(self, 'preinst') and self.preinst:
            run_module(self.preinst, 'preinst', ucr, changed)

        if self.def_count == 0 or not self.from_files:
            return

        to_dir = os.path.dirname(self.to_file)
        if not os.path.isdir(to_dir):
            os.makedirs(to_dir, 0o755)

        if os.path.isfile(self.dummy_from_file):
            stat: os.stat_result | None = os.stat(self.dummy_from_file)
        elif os.path.isfile(self.to_file):
            stat = os.stat(self.to_file)
        else:
            stat = None

        tmp_to_file = self._temp_file_name()
        try:
            filter_opts: dict[str, Any] = {}

            with open(tmp_to_file, 'wb') as to_fp:
                self._set_perm(stat, tmp_to_file)

                for from_file in sorted(self.from_files, key=os.path.basename):
                    try:
                        with open(from_file, encoding='utf-8') as from_fp:
                            to_fp.write(run_filter(from_fp.read(), ucr, srcfiles=self.from_files, opts=filter_opts))
                    except OSError:
                        continue

            try:
                os.rename(tmp_to_file, self.to_file)
            except OSError as ex:
                if ex.errno == errno.EBUSY:
                    with open(self.to_file, 'w+', encoding='utf-8') as fd:
                        fd.write(open(tmp_to_file, encoding='utf-8').read())
                    os.unlink(tmp_to_file)
        except Exception:
            if os.path.exists(tmp_to_file):
                os.unlink(tmp_to_file)
            raise

        if hasattr(self, 'postinst') and self.postinst:
            run_module(self.postinst, 'postinst', ucr, changed)

        script_file = os.path.join(SCRIPT_DIR, self.to_file.strip("/"))
        if os.path.isfile(script_file):
            run_script(script_file, 'postinst', changed)

    def need_divert(self) -> bool:
        """
        Diversion is needed when at least one multifile and one subfile
        definition exists.
        """
        return self.def_count >= 1 and bool(self.from_files)

    def install_divert(self) -> None:
        """Prepare file for diversion."""
        if self.need_divert():
            super().install_divert()

    def uninstall_divert(self) -> bool:
        """
        Undo diversion of file.

        :returns: `True` when the diversion is removed, `False` when the diversion is still needed.
        """
        if self.need_divert():
            return False
        return super().uninstall_divert()


class ConfigHandlerFile(ConfigHandlerDiverting):
    """
    Handler for (single)file.

    :param from_file: Template source file name.
    :param to_file: Destination file name.
    """

    def __init__(self, from_file: str, to_file: str) -> None:
        super().__init__(to_file)
        self.from_file = from_file

    def __call__(self, args: _ARG) -> None:
        """Generate file from template."""
        ucr, changed = args

        if hasattr(self, 'preinst') and self.preinst:
            run_module(self.preinst, 'preinst', ucr, changed)

        print('File: %s' % self.to_file)

        to_dir = os.path.dirname(self.to_file)
        if not os.path.isdir(to_dir):
            os.makedirs(to_dir, 0o755)

        try:
            stat = os.stat(self.from_file)
        except OSError:
            print("The referenced template file does not exist", file=sys.stderr)
            return

        tmp_to_file = self._temp_file_name()
        try:
            filter_opts: dict[str, Any] = {}

            with open(self.from_file, encoding='utf-8') as from_fp, open(tmp_to_file, 'wb') as to_fp:
                self._set_perm(stat, tmp_to_file)

                to_fp.write(run_filter(from_fp.read(), ucr, srcfiles=[self.from_file], opts=filter_opts))

            try:
                os.rename(tmp_to_file, self.to_file)
            except OSError as ex:
                if ex.errno == errno.EBUSY:
                    with open(self.to_file, 'w+', encoding='utf-8') as fd:
                        fd.write(open(tmp_to_file, encoding='utf-8').read())
                    os.unlink(tmp_to_file)
        except Exception:
            if os.path.exists(tmp_to_file):
                os.unlink(tmp_to_file)
            raise

        if hasattr(self, 'postinst') and self.postinst:
            run_module(self.postinst, 'postinst', ucr, changed)

        script_file = self.from_file.replace(FILE_DIR, SCRIPT_DIR)
        if os.path.isfile(script_file):
            run_script(script_file, 'postinst', changed)

    def need_divert(self) -> bool:
        """For simple files the diversion is always needed."""
        return True


class ConfigHandlerScript(ConfigHandler):
    """
    Handler for UCR scripts.

    :param script: Script file name.
    """

    def __init__(self, script: str) -> None:
        super().__init__()
        self.script = script

    def __hash__(self):
        """Return unique hash."""
        return hash(self.script)

    def __eq__(self, other):
        """Compare this to other handler."""
        if isinstance(other, type(self)):
            return self.script == other.script
        return NotImplemented

    def __ne__(self, other):
        """Compare this to other handler."""
        if isinstance(other, type(self)):
            return self.script != other.script
        return NotImplemented

    def __call__(self, args: _ARG) -> None:
        """Call external programm after change."""
        _ucr, changed = args
        print('Script: %s' % self.script)
        if os.path.isfile(self.script):
            run_script(self.script, 'generate', changed)


class ConfigHandlerModule(ConfigHandler):
    """
    Handler for UCR Python module.

    :param module: Module file name.
    """

    def __init__(self, module: str) -> None:
        super().__init__()
        self.module = module

    def __hash__(self):
        """Return unique hash."""
        return hash(self.module)

    def __eq__(self, other):
        """Compare this to other handler."""
        if isinstance(other, type(self)):
            return self.module == other.module
        return NotImplemented

    def __ne__(self, other):
        """Compare this to other handler."""
        if isinstance(other, type(self)):
            return self.module != other.module
        return NotImplemented

    def __call__(self, args: _ARG) -> None:
        """Call Python module after change."""
        ucr, changed = args
        print('Module: %s' % self.module)
        run_module(self.module, 'handler', ucr, changed)


def grep_variables(text: str) -> set[str]:
    """
    Search UCR template text for used variables.

    :returns: Set of all variables inside `@%@` delimiters.
    """
    return set(VARIABLE_PATTERN.findall(text))


class ConfigHandlers:
    """Manage handlers for configuration variables."""

    CACHE_FILE = '/var/cache/univention-config/cache'
    # 0: without version
    # 1: with version header
    # 2: switch to handlers mapping to set, drop file, add multifile.def_count
    # 3: split config_registry into sub modules
    VERSION = 3
    VERSION_MIN = 3
    VERSION_MAX = 3
    VERSION_TEXT = 'univention-config cache, version'
    VERSION_NOTICE = '%s %s\n' % (VERSION_TEXT, VERSION)
    VERSION_RE = re.compile('^%s (?P<version>[0-9]+)$' % VERSION_TEXT)

    _handlers: dict[str, set[ConfigHandler]] = {}  # variable -> set(handlers)
    _multifiles: dict[str, ConfigHandlerMultifile] = {}  # multifile -> handler
    _subfiles: dict[str, list[tuple[str, set[str]]]] = {}  # multifile -> [(subfile, variables)] // pending

    def __init__(self) -> None:
        pass

    @staticmethod
    def _get_cache_version(cache_file: IO) -> int:
        """
        Read cached `.info` data.

        :param cache_file: Opened cache file.
        :returns: Version.
        """
        line = cache_file.readline()    # IOError is propagated
        match = ConfigHandlers.VERSION_RE.match(line)
        if match:
            version = int(match.group('version'))
        # "Old style" cache (version 0) doesn't contain version notice
        else:
            cache_file.seek(0)
            version = 0
        return version

    @classmethod
    def _parse_rfc822_file(cls, fname: str) -> list[dict[str, list[str]]]:
        """
        Parse :rfc:`822` file.

        :param fname: Path to :rfc:`822` file.
        :returns: A list of dictionaries.
        """
        with open(fname, encoding='utf-8') as fd:
            return parseRfc822(fd.read())

    def load(self) -> None:
        """Load cached `.info` data or force update."""
        try:
            with open(ConfigHandlers.CACHE_FILE, 'rb') as cache_file:
                version = self._get_cache_version(cache_file)
                chv = ConfigHandlers
                if not chv.VERSION_MIN <= version <= chv.VERSION_MAX:
                    raise TypeError("Invalid cache file version.")
                pickler = pickle.Unpickler(cache_file)
                self._handlers = pickler.load()
                if version <= 1:
                    # version <= 1: _handlers[multifile] -> [handlers]
                    # version >= 2: _handlers[multifile] -> set([handlers])
                    self._handlers = {k: set(v) for k, v in self._handlers.items()}
                    # version <= 1: _files UNUSED
                    pickler.load()
                self._subfiles = pickler.load()
                self._multifiles = pickler.load()
        except (Exception, pickle.UnpicklingError):
            self.update()

    def get_handler(self, entry: _INFO) -> ConfigHandler | None:
        """
        Parse entry and return Handler instance.

        :param entry: `.info` file entry dictionary.
        :returns: An instance of `None`.
        """
        try:
            typ = entry['Type'][0]
            handler = getattr(self, '_get_handler_%s' % typ)
        except (LookupError, AttributeError):
            return None
        else:
            return handler(entry)

    def _parse_common_file_handler(self, handler: ConfigHandlerDiverting, entry: _INFO) -> None:
        """
        Parse common file and multifile entries.

        :param handler: Handler instance.
        :param entry: `.info` file entry dictionary.
        """
        try:
            handler.preinst = entry['Preinst'][0]
        except LookupError:
            pass

        try:
            handler.postinst = entry['Postinst'][0]
        except LookupError:
            pass

        handler.variables |= set(entry.get('Variables', set()))

        try:
            user = entry['User'][0]
        except LookupError:
            pass
        else:
            try:
                handler.user = getpwnam(user).pw_uid
            except LookupError:
                print(('W: failed to convert the username %s to the uid' % (user,)), file=sys.stderr)

        try:
            group = entry['Group'][0]
        except LookupError:
            pass
        else:
            try:
                handler.group = getgrnam(group).gr_gid
            except LookupError:
                print(('W: failed to convert the groupname %s to the gid' % (group,)), file=sys.stderr)

        try:
            mode = entry['Mode'][0]
        except LookupError:
            pass
        else:
            try:
                handler.mode = int(mode, 8)
            except ValueError:
                print('W: failed to convert mode %s' % (mode,), file=sys.stderr)

    def _get_handler_file(self, entry: _INFO) -> ConfigHandlerFile | None:
        """
        Parse file entry and return Handler instance.

        :param entry: `.info` file entry dictionary.
        :returns: An instance of `None`.
        """
        try:
            name = entry['File'][0]
        except LookupError:
            return None
        from_path = os.path.join(FILE_DIR, name)
        handler = ConfigHandlerFile(from_path, name)
        if os.path.exists(from_path):
            with open(from_path, encoding='utf-8') as fd:
                handler.variables = grep_variables(fd.read())

        self._parse_common_file_handler(handler, entry)

        return handler

    def _get_handler_script(self, entry: _INFO) -> ConfigHandlerScript | None:
        """
        Parse script entry and return Handler instance.

        :param entry: `.info` file entry dictionary.
        :returns: An instance of `None`.
        """
        try:
            script = entry['Script'][0]
            variables = entry['Variables']
        except LookupError:
            return None
        handler = ConfigHandlerScript(os.path.join(SCRIPT_DIR, script))
        handler.variables = set(variables)
        return handler

    def _get_handler_module(self, entry: _INFO) -> ConfigHandlerModule | None:
        """
        Parse module entry and return Handler instance.

        :param entry: `.info` file entry dictionary.
        :returns: An instance of `None`.
        """
        try:
            module = entry['Module'][0]
            variables = entry['Variables']
        except LookupError:
            return None
        handler = ConfigHandlerModule(os.path.splitext(module)[0])
        handler.variables = set(variables)
        return handler

    def _get_handler_multifile(self, entry: _INFO) -> ConfigHandlerMultifile | None:
        """
        Parse multifile entry and return Handler instance.

        :param entry: `.info` file entry dictionary.
        :returns: An instance of `None`.
        """
        try:
            mfile = entry['Multifile'][0]
        except LookupError:
            return None
        try:
            handler = self._multifiles[mfile]
            handler.def_count += 1
        except KeyError:
            from_path = os.path.join(FILE_DIR, mfile)
            handler = ConfigHandlerMultifile(from_path, mfile)

        self._parse_common_file_handler(handler, entry)

        # Add pending subfiles from earlier entries
        self._multifiles[mfile] = handler
        try:
            file_vars = self._subfiles.pop(mfile)
            handler.add_subfiles(file_vars)
        except KeyError:
            pass

        return handler

    def _get_handler_subfile(self, entry: dict[str, list[str]]) -> ConfigHandlerMultifile | None:
        """
        Parse subfile entry and return Handler instance.

        :param entry: `.info` file entry dictionary.
        :returns: An instance of `None`.
        """
        try:
            mfile = entry['Multifile'][0]
            subfile = entry['Subfile'][0]
        except LookupError:
            return None
        variables = set(entry.get('Variables', set()))
        name = os.path.join(FILE_DIR, subfile)
        try:
            with open(name, encoding='utf-8') as temp_file:
                variables |= grep_variables(temp_file.read())
        except OSError:
            print("Failed to process Subfile %s" % (name,), file=sys.stderr)
            return None
        qentry = (name, variables)
        # if multifile handler does not yet exists, queue subfiles for later
        try:
            handler = self._multifiles[mfile]
            handler.add_subfiles([qentry])
        except KeyError:
            pending = self._subfiles.setdefault(mfile, [])
            pending.append(qentry)
            return None
        return handler

    def update(self) -> set[ConfigHandler]:
        """
        Parse all `.info` files to build list of handlers.

        :returns: Set of all handlers.
        """
        self._handlers.clear()
        self._multifiles.clear()
        self._subfiles.clear()

        handlers: set[ConfigHandler] = set()
        for info in directory_files(INFO_DIR):
            if not info.endswith('.info'):
                continue
            for section in self._parse_rfc822_file(info):
                handler = self.get_handler(section)
                if handler:
                    handlers.add(handler)
        for handler in handlers:
            for variable in handler.variables:
                v2h = self._handlers.setdefault(variable, set())
                v2h.add(handler)

        self._save_cache()
        return handlers

    def update_divert(self, handlers: Iterable[ConfigHandler]) -> None:
        """
        Synchronize diversions with handlers.

        :param handlers: List of handlers.
        """
        wanted = {h.to_file: h for h in handlers if isinstance(h, ConfigHandlerDiverting) and h.need_divert()}
        to_remove: set[str] = set()
        # Scan for diversions done by UCR
        with open('/var/lib/dpkg/diversions', encoding='utf-8') as div_file:
            # from \n to \n package \n
            try:
                while True:
                    path_from = next(div_file).rstrip()
                    path_to = next(div_file).rstrip()
                    diversion = next(div_file).rstrip()
                    if path_from + '.debian' != path_to:
                        continue
                    if diversion != ':':  # local diversion
                        continue
                    assert path_from not in to_remove  # no duplicates
                    try:
                        handler = wanted.pop(path_from)
                    except KeyError:
                        to_remove.add(path_from)
            except StopIteration:
                pass

        # Remove existing diversion not wanted
        for path in to_remove:
            tmp_handler = ConfigHandlerDiverting(path)
            tmp_handler.uninstall_divert()
        # Install missing diversions still wanted
        for path, handler in wanted.items():
            handler.install_divert()

    def _save_cache(self) -> None:
        """Write cache file."""
        try:
            with open(ConfigHandlers.CACHE_FILE, 'wb') as cache_file:
                cache_file.write(ConfigHandlers.VERSION_NOTICE.encode('utf-8'))
                pickler = pickle.Pickler(cache_file)
                pickler.dump(self._handlers)
                pickler.dump(self._subfiles)
                pickler.dump(self._multifiles)
        except OSError as ex:
            if ex.errno != errno.EACCES:
                raise

    def register(self, package: str, ucr: _UCR) -> set[ConfigHandler]:
        """
        Register new info file for package.

        :param package: Name of the package to register.
        :param ucr: UCR instance.
        :returns: Set of (new) handlers.
        """
        handlers: set[ConfigHandler] = set()
        fname = os.path.join(INFO_DIR, '%s.info' % package)
        for section in self._parse_rfc822_file(fname):
            handler = self.get_handler(section)
            if handler:
                handlers.add(handler)

        for handler in handlers:
            if isinstance(handler, ConfigHandlerDiverting):
                handler.install_divert()

            values: dict[str, tuple[None, str | None]] = {}
            for variable in handler.variables:
                v2h = self._handlers.setdefault(variable, set())
                v2h.add(handler)
                values[variable] = (None, ucr[variable])
                try:
                    _re = re.compile(variable)
                except re.error:
                    continue

                values.update((key, (None, val)) for key, val in ucr.items() if _re.match(key))

            handler((ucr, values))

        self._save_cache()
        return handlers

    def unregister(self, package: str, ucr: _UCR) -> set[ConfigHandler]:
        """
        Un-register info file for package.

        :param package: Name of the package to un-register.
        :param ucr: UCR instance.
        :returns: Set of (then obsolete) handlers.
        """
        obsolete_handlers: set[ConfigHandler] = set()
        mf_handlers: set[ConfigHandler] = set()  # Remaining Multifile handlers
        fname = os.path.join(INFO_DIR, '%s.info' % package)
        for section in self._parse_rfc822_file(fname):
            try:
                typ = section['Type'][0]
            except LookupError:
                continue
            if typ == 'file':
                handler = self.get_handler(section)
            elif typ == 'subfile':
                mfile = section['Multifile'][0]
                sfile = section['Subfile'][0]
                try:
                    handler = self._multifiles[mfile]
                except KeyError:
                    continue  # skip SubFile w/o MultiFile
                name = os.path.join(FILE_DIR, sfile)
                handler.remove_subfile(name)
                mf_handlers.add(handler)
            elif typ == 'multifile':
                mfile = section['Multifile'][0]
                handler = self._multifiles[mfile]
                handler.def_count -= 1
                mf_handlers.add(handler)
            else:
                continue
            if not handler:  # Bug #17913
                print(("Skipping internal error: no handler for %r in %s" % (section, package)), file=sys.stderr)
                continue
            if isinstance(handler, ConfigHandlerDiverting) and handler.uninstall_divert():
                obsolete_handlers.add(handler)

        for handler in mf_handlers - obsolete_handlers:
            self.call_handler(ucr, handler)

        try:
            # remove cache file to force rebuild of cache
            os.unlink(ConfigHandlers.CACHE_FILE)
        except OSError:
            pass
        return obsolete_handlers

    def __call__(self, variables: Iterable[str], arg: _ARG) -> None:
        """
        Call handlers registered for changes in variables.

        :param variables: Changed UCR variable names.
        :param arg: 2-tuple(UCR-instance, changed) where changed is a dictionary mapping ucs-variable-names to values.
        """
        if not variables:
            return
        pending_handlers: set[ConfigHandler] = set()

        for reg_var, handlers in self._handlers.items():
            try:
                _re = re.compile(reg_var)
            except re.error as ex:
                print('Failed to compile regular expression %s: %s' % (reg_var, ex), file=sys.stderr)
                continue

            for variable in variables:
                if _re.match(variable):
                    pending_handlers |= handlers

        for handler in pending_handlers:
            handler(arg)

    def commit(self, ucr: _UCR, filelist: Iterable[str] = []) -> None:
        """
        Call handlers to (re-)generate files.

        :param ucr: UCR instance.
        :param filelist: List of files to re-generate. By default *all* files will be re-generated and all modules and scripts will we re-invoked!
        """
        _filelist = []
        for fname in filelist:
            fname = os.path.expanduser(fname)
            fname = os.path.expandvars(fname)
            fname = os.path.abspath(fname)
            _filelist.append(fname)

        # find handlers
        pending_handlers = set()
        for fname in directory_files(INFO_DIR):
            if not fname.endswith('.info'):
                continue
            for section in self._parse_rfc822_file(fname):
                if not section.get('Type'):
                    continue
                handler = None
                if _filelist:
                    files = section.get('File') or section.get('Multifile') or ()
                    for filename in files:
                        if not os.path.isabs(filename):
                            filename = '/%s' % filename
                        if filename in _filelist:
                            handler = self.get_handler(section)
                            break
                    else:
                        continue
                else:
                    handler = self.get_handler(section)

                if handler:
                    pending_handlers.add(handler)

        # print missing files
        for fname in set(_filelist) - {h.to_file for h in pending_handlers if isinstance(h, ConfigHandlerDiverting)}:
            print('Warning: The file %r is not registered as an UCR template.' % (fname,), file=sys.stderr)

        # call handlers
        for handler in pending_handlers:
            self.call_handler(ucr, handler)

    def call_handler(self, ucr: _UCR, handler: ConfigHandler) -> None:
        """
        Call handler passing current configuration variables.

        :param ucr: UCR instance.
        :param handler: The handler to call.
        """
        values: dict[str, tuple[str | None, str | None]] = {}
        for variable in handler.variables:
            if variable in self._handlers.keys():
                if ".*" in variable:
                    for i in range(4):
                        var = variable.replace(".*", "%s" % i)
                        val = ucr.get(var)
                        values[var] = (val, val)
                else:
                    val = ucr.get(variable)
                    values[variable] = (val, val)
        handler((ucr, values))
