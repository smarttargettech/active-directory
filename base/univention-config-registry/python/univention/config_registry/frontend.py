"""Univention Configuration Registry command line implementation."""
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
# API stability :pylint: disable-msg=W0613
# Rewrite       :pylint: disable-msg=R0912,R0914,R0915

import os
import re
import sys
import time
from collections.abc import Callable, Iterator
from typing import IO, Any, NoReturn

import univention.config_registry_info as cri
from univention.config_registry.backend import SCOPE, ConfigRegistry, exception_occured
from univention.config_registry.filters import filter_keys_only, filter_shell, filter_sort
from univention.config_registry.handler import ConfigHandlers, run_filter
from univention.config_registry.misc import escape_value, validate_key
from univention.config_registry.validation import Type


__all__ = [
    'REPLOG_FILE',
    'UnknownKeyException',
    'handler_commit',
    'handler_dump',
    'handler_filter',
    'handler_get',
    'handler_help',
    'handler_info',
    'handler_register',
    'handler_search',
    'handler_set',
    'handler_unregister',
    'handler_unset',
    'handler_update',
    'handler_version',
    'main',
]

REPLOG_FILE = '/var/log/univention/config-registry.replog'

_SHOW_EMPTY, _SHOW_DESCRIPTION, _SHOW_SCOPE, _SHOW_CATEGORIES, _SHOW_DEFAULT, _SHOW_TYPE = (1 << _ for _ in range(6))


class UnknownKeyException(Exception):
    """Query for unknown key: no info file nor set."""

    def __init__(self, value):
        Exception.__init__(self, value)

    def __str__(self):
        return 'W: Unknown key: "%s"' % self.args


def replog(ucr: ConfigRegistry, var: str, old_value: str | None, value: str | None = None) -> None:
    """
    This function writes a new entry to replication logfile if
    this feature has been enabled.

    :param ucr: UCR instance.
    :param var: UCR variable name.
    :param old_value: Old UCR variable value.
    :param value: New UCR variable value. `None` is now unset.
    """
    if ucr.is_true('ucr/replog/enabled', False):
        if value is not None:
            method = 'set'
            varvalue = "%s=%s" % (var, escape_value(value))
        else:
            method = 'unset'
            varvalue = "'%s'" % var

        scope_arg = {
            ConfigRegistry.LDAP: '--ldap-policy ',
            ConfigRegistry.FORCED: '--force ',
            ConfigRegistry.SCHEDULE: '--schedule ',
        }.get(ucr.scope, '')

        if old_value is None:
            old_value = "[Previously undefined]"

        log = '%s: %s %s%s old:%s\n' % (time.strftime("%Y-%m-%d %H:%M:%S"), method, scope_arg, varvalue, old_value)
        try:
            if not os.path.isfile(REPLOG_FILE):
                os.close(os.open(REPLOG_FILE, os.O_CREAT, 0o640))

            with open(REPLOG_FILE, "a+", encoding='utf-8') as logfile:
                logfile.write(log)
        except OSError as ex:
            print("E: exception occurred while writing to replication log: %s" % (ex,), file=sys.stderr)
            exception_occured()


def handler_set(args: list[str], opts: dict[str, Any] = {}, quiet: bool = False) -> None:
    """
    Set config registry variables in args.
    Args is an array of strings 'key=value' or 'key?value'.

    :param args: Command line arguments.
    :param opts: Command line options.
    :param quiet: Hide output.
    """
    ucr = ConfigRegistry()
    ucr.load()
    ignore_check = opts.get('ignore-check') or ucr.is_false('ucr/check/type')

    ucr = _ucr_from_opts(opts)
    info = _get_config_registry_info()
    with ucr:
        changes: dict[str, str | None] = {}
        for arg in args:
            sep_set = arg.find('=')  # set
            sep_def = arg.find('?')  # set if not already set
            if sep_set == -1 and sep_def == -1:
                print("W: Missing value for config registry variable '%s'" % (arg,), file=sys.stderr)
                continue

            if sep_set > 0 and sep_def == -1:
                sep = sep_set
            elif sep_def > 0 and sep_set == -1:
                sep = sep_def
            else:
                sep = min(sep_set, sep_def)
            key = arg[0:sep]
            value = arg[sep + 1:]
            key_exists = key in ucr._layer
            do_set_value = (not key_exists or sep == sep_set)
            if do_set_value and validate_key(key):
                if not quiet:
                    if key_exists:
                        print('Setting %s' % key)
                    else:
                        print('Create %s' % key)
                vinfo = info.get_variable(key) or info.match_pattern(key)
                if vinfo:  # Type checking can only be done if key is already configured
                    try:
                        validator = Type(vinfo)
                    except (TypeError, ValueError):
                        if ignore_check:
                            print('W: Invalid UCR type definition for type %r of %r, but set anyway' % (vinfo.get('type'), key), file=sys.stderr)
                        else:
                            print('E: Invalid UCR type definition for type %r of %r, value %r not set' % (vinfo.get('type'), key, value), file=sys.stderr)
                            opts['exit_code'] = 1
                            opts.setdefault('type_def_error', []).append((key, vinfo.get('type'), value))
                            continue  # do not set value and continue with next element of for loop to be set
                    else:
                        if not validator.check(value):
                            if ignore_check:
                                print('W: Value %r incompatible for %r, but setting anyway' % (value, key), file=sys.stderr)
                            else:
                                print('E: Value %r incompatible for %r' % (value, key), file=sys.stderr)
                                opts['exit_code'] = 2
                                opts.setdefault('type_errors', []).append((key, value))
                                continue  # do not set value and continue with next element of for loop to be set
                changes[key] = value
            else:
                if do_set_value:
                    opts['exit_code'] = 1
                if not quiet:
                    if key_exists:
                        print('Not updating %s' % key)
                    else:
                        print('Not setting %s' % key)
        changed = ucr.update(changes)

    _run_changed(ucr, changed, "" if quiet else 'W: %s is overridden by scope "%s"')


def handler_unset(args: list[str], opts: dict[str, Any] = {}) -> None:
    """
    Unset config registry variables in args.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = _ucr_from_opts(opts)
    with ucr:
        changes: dict[str, str | None] = {}
        for arg in args:
            if arg in ucr._layer:
                print('Unsetting %s' % arg)
                changes[arg] = None
            else:
                msg = "W: The config registry variable '%s' does not exist"
                print(msg % (arg,), file=sys.stderr)
        changed = ucr.update(changes)

    _run_changed(ucr, changed, 'W: %s is still set in scope "%s"')


def ucr_update(ucr: ConfigRegistry, changes: dict[str, str | None]) -> None:
    """
    Set or unset the given config registry variables.

    :param ucr: UCR instance.
    :param changes: Changed UCR variables.
    """
    with ucr:
        changed = ucr.update(changes)
    _run_changed(ucr, changed)


def _run_changed(ucr: ConfigRegistry, changed: dict[str, tuple[str | None, str | None]], msg: str = "") -> None:
    """
    Run handlers for changed UCR variables.

    :param ucr: UCR instance.
    :param changed: Mapping from UCR variable name to 2-tuple (old-value, new-value).
    :param msg: Message to be printed when change is shadowed by higher layer. Must contain 2 `%s` placeholders for `key` and `scope-name`.
    """
    visible: dict[str, tuple[str | None, str | None]] = {}
    for key, (old_value, new_value) in changed.items():
        replog(ucr, key, old_value, new_value)

        reg = ucr.scope
        while old_value is None and reg > 0:
            reg -= 1
            old_value = ucr._registry[reg].get(key)

        reg, new_value = ucr.get(key, (0, None), getscope=True)
        if reg > ucr.scope:
            if msg:
                print(msg % (key, SCOPE[reg]), file=sys.stderr)
        else:
            visible[key] = (old_value, new_value)

    handlers = ConfigHandlers()
    handlers.load()
    handlers(list(visible), (ucr, visible))


def _ucr_from_opts(opts: dict[str, Any]) -> ConfigRegistry:
    """
    Create :py:class:`ConfigRegistry` instance according to requested layer.

    :param opts: Command line options.
    :returns: A new UCR instance.
    """
    if opts.get('ldap-policy'):
        scope = ConfigRegistry.LDAP
    elif opts.get('force'):
        scope = ConfigRegistry.FORCED
    elif opts.get('schedule'):
        scope = ConfigRegistry.SCHEDULE
    else:
        scope = ConfigRegistry.NORMAL
    ucr = ConfigRegistry(write_registry=scope)
    return ucr


def handler_dump(args: list[str], opts: dict[str, Any] = {}) -> Iterator[str]:
    """
    Dump all variables.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = ConfigRegistry()
    ucr.load()
    yield from str(ucr).split('\n')


def handler_update(args: list[str], opts: dict[str, Any] = {}) -> None:
    """
    Update handlers.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    handlers = ConfigHandlers()
    cur = handlers.update()
    handlers.update_divert(cur)

    ucr = ConfigRegistry()
    _register_variable_default_values(ucr)


def handler_commit(args: list[str], opts: dict[str, Any] = {}) -> None:
    """
    Commit all registered templated files.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = ConfigRegistry()
    ucr.load()

    handlers = ConfigHandlers()
    handlers.load()
    handlers.commit(ucr, args)


def handler_register(args: list[str], opts: dict[str, Any] = {}) -> None:
    """
    Register new `.info` file.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = ConfigRegistry()
    ucr.load()

    handlers = ConfigHandlers()
    handlers.update()  # cache must be current
    # Bug #21263: by forcing an update here, the new .info file is already
    # incorporated. Calling register for multifiles will increment the
    # def_count a second time, which is not nice, but uncritical, since the
    # diversion is (re-)done when >= 1.

    _register_variable_default_values(ucr)
    handlers.register(args[0], ucr)
    # handlers.commit((ucr, {}))


def handler_unregister(args: list[str], opts: dict[str, Any] = {}) -> None:
    """
    Unregister old `.info` file.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = ConfigRegistry()
    ucr.load()

    handlers = ConfigHandlers()
    cur = handlers.update()  # cache must be current
    obsolete = handlers.unregister(args[0], ucr)
    handlers.update_divert(cur - obsolete)
    _register_variable_default_values(ucr)


def handler_filter(args: list[str], opts: dict[str, Any] = {}) -> None:
    """Run filter on STDIN to STDOUT."""
    ucr = ConfigRegistry()
    ucr.load()
    sys.stdout.buffer.write(run_filter(sys.stdin.read(), ucr, opts=opts))


def handler_search(args: list[str], opts: dict[str, Any] = {}) -> Iterator[str]:
    """
    Search for registry variable.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    search_keys = opts.get('key', False)
    search_values = opts.get('value', False)
    search_all = opts.get('all', False)
    count_search = int(search_keys) + int(search_values) + int(search_all)
    if count_search > 1:
        print('E: at most one out of [--key|--value|--all] may be set', file=sys.stderr)
        sys.exit(1)
    elif count_search == 0:
        search_keys = True
    search_values |= search_all
    search_keys |= search_all

    if args:
        try:
            search = re.compile('|'.join('(?:%s)' % (_,) for _ in args)).search
        except re.error as ex:
            print('E: invalid regular expression: %s' % (ex,), file=sys.stderr)
            sys.exit(1)
    else:
        def search(x):  # type: ignore[misc]
            return True

    info = _get_config_registry_info()

    category = opts.get('category')
    if category and not info.get_category(category):
        print('E: unknown category: "%s"' % (category,), file=sys.stderr)
        sys.exit(1)

    ucr = ConfigRegistry()
    ucr.load()

    details = _SHOW_EMPTY | _SHOW_DESCRIPTION
    if opts.get('non-empty'):
        details &= ~_SHOW_EMPTY
    if opts.get('brief') or ucr.is_true('ucr/output/brief', False):
        details &= ~_SHOW_DESCRIPTION
    if ucr.is_true('ucr/output/scope', False):
        details |= _SHOW_SCOPE
    if opts.get('verbose'):
        details |= _SHOW_CATEGORIES | _SHOW_DESCRIPTION

    all_vars: dict[str, tuple[str | None, cri.Variable | None, int | None]] = {}  # key: (value, vinfo, scope)
    for key, var in info.get_variables(category).items():
        all_vars[key] = (None, var, None)
    for key, (scope, value) in ucr.items(getscope=True):
        try:
            all_vars[key] = (value, all_vars[key][1], scope)
        except LookupError:
            all_vars[key] = (value, None, scope)

    for key, (value2, vinfo, _scope2) in all_vars.items():
        if any((
                search_keys and search(key),
                search_values and value2 and search(value2),
                search_all and vinfo and search(vinfo.get('description', '')),
        )):
            yield variable_info_string(key, value2, vinfo, details=details)

    if _SHOW_EMPTY & details and not OPT_FILTERS['shell'][2]:
        patterns: dict = {}
        for arg in args or ('',):
            patterns.update(info.describe_search_term(arg))
        for pattern, vinfo in patterns.items():
            yield variable_info_string(pattern, None, vinfo, details=details)


def handler_get(args: list[str], opts: dict[str, Any] = {}) -> Iterator[str]:
    """
    Return config registry variable.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = ConfigRegistry()
    ucr.load()
    key = args[0]
    value = ucr.get(key)
    if value is None:
        return
    elif OPT_FILTERS['shell'][2]:
        yield '%s: %s' % (key, value)
    else:
        yield value


def variable_info_string(key: str, value: str | None, variable_info: cri.Variable | None, scope: int | None = None, details: int = _SHOW_DESCRIPTION) -> str:
    """
    Format UCR variable key, value, description, scope, categories and default value.

    :param key: UCR variable name.
    :param value: UCR variable value.
    :param variable_info: Description object.
    :param scope: UCS layer.
    :param details: bit-field for detail-level.
    :returns: formatted string
    """
    if value is None and not variable_info:
        raise UnknownKeyException(key)
    elif value in (None, '') and not _SHOW_EMPTY & details:
        return ''
    elif value is None:
        # if not shell filter option is set
        value_string = "<empty>" if not OPT_FILTERS["shell"][2] else ""
    else:
        value_string = '%s' % value

    if scope is None or not 0 <= scope < len(SCOPE) or not _SHOW_SCOPE & details or OPT_FILTERS['shell'][2]:  # Do not display scope in shell export
        key_value = '%s: %s' % (key, value_string)
    else:
        key_value = '%s (%s): %s' % (key, SCOPE[scope], value_string)

    info = [key_value]
    if variable_info and _SHOW_DESCRIPTION & details:
        # info.append(' ' + variable_info.get('description',
        #   'no description available'))
        # <https://forge.univention.org/bugzilla/show_bug.cgi?id=15556>
        # Workaround:
        description = variable_info.get('description')
        if not description or not description.strip():
            description = 'no description available'
        info.append(' ' + description)

    if variable_info and _SHOW_CATEGORIES & details:
        info.append(' Categories: ' + variable_info.get('categories', 'none'))

    if variable_info and _SHOW_DEFAULT & details:
        info.append(' Default: ' + variable_info.get('default', '(not set)'))

    if variable_info and _SHOW_TYPE & details:
        try:
            validator = Type(variable_info)
            info.append(' Type: %s' % (validator,))
        except ValueError as exc:
            info.append(' Type: %s' % exc)

    if (_SHOW_CATEGORIES | _SHOW_DESCRIPTION) & details:
        info.append('')

    return '\n'.join(info)


def handler_info(args: list[str], opts: dict[str, Any] = {}) -> Iterator[str]:
    """
    Print variable info.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    ucr = ConfigRegistry()
    ucr.load()
    info = _get_config_registry_info()

    for arg in args:
        try:
            yield variable_info_string(
                arg, ucr.get(arg, None),
                info.get_variable(arg),
                details=_SHOW_EMPTY | _SHOW_DESCRIPTION | _SHOW_CATEGORIES | _SHOW_DEFAULT | _SHOW_TYPE)
        except UnknownKeyException as ex:
            print(ex, file=sys.stderr)


def handler_version(args: list[str], opts: dict[str, Any] = {}) -> NoReturn:
    """
    Print version info.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    print('univention-config-registry @%@package_version@%@')
    sys.exit(0)


def handler_help(args: list[str], opts: dict[str, Any] = {}, out: IO = sys.stdout) -> None:
    """
    Print config registry command line usage.

    :param args: Command line arguments.
    :param opts: Command line options.
    """
    print('''
univention-config-registry: base configuration for UCS
copyright (c) 2001-2025 Univention GmbH, Germany

Syntax:
  univention-config-registry [options] <action> [options] [parameters]

Options:

  -h | --help | -?:
    print this usage message and exit program

  --version | -v:
    print version information and exit program

  --shell (valid actions: dump, search):
    convert key/value pair into shell compatible format, e.g.
    `version/version: 1.0` => `version_version="1.0"`

  --keys-only (valid actions: dump, search):
    print only the keys

Actions:
  set [--force|--schedule|--ldap-policy] [--ignore-check] <key>=<value> [... <key>=<value>]:
    set one or more keys to specified values; if a key is non-existent
    in the configuration registry it will be created
    --ignore-check: ignore check if given value is compatible with type of the key

  get <key>:
    retrieve the value of the specified key from the configuration
    database

  unset [--force|--schedule|--ldap-policy] <key> [... <key>]:
    remove one or more keys (and its associated values) from
    configuration database

  dump:
    display all key/value pairs which are stored in the
    configuration database

  search [--key|--value|--all] [--category <category>] [--brief|-verbose] \\
          [--non-empty] [... <regex>]:
    displays all key/value pairs and their descriptions that match at
    least one of the given regular expressions
    --key: only search the keys (default)
    --value: only search the values
    --all: search keys, values and descriptions
    --category: limit search to variables of <category>
    --brief: don't print descriptions (default controlled via ucr/output/brief)
    --verbose: also print category for each variable
    --non-empty: only search in non-empty variables
    no <regex> given: display all variables

  info <key> [... <key>]:
    display verbose information for the specified variable(s)

  shell [key]:
    convert key/value pair into shell compatible format, e.g.
    `version/version: 1.0` => `version_version="1.0"`
    (deprecated: use --shell dump instead)

  commit [file1 ...]:
    rebuild configuration file from univention template; if
    no file is specified ALL configuration files are rebuilt

  filter [file]:
    evaluate a template file, expects Python inline code in UTF-8 or US-ASCII

Description:
  univention-config-registry is a tool to handle the basic configuration for
  Univention Corporate Server (UCS)
''', file=out)
    sys.exit(0)


def missing_parameter(action: str) -> NoReturn:
    """Print missing parameter error."""
    print('E: too few arguments for command [%s]' % (action,), file=sys.stderr)
    print('try `univention-config-registry --help` for more information', file=sys.stderr)
    sys.exit(1)


def _get_config_registry_info() -> cri.ConfigRegistryInfo:
    cri.set_language('en')
    return cri.ConfigRegistryInfo(install_mode=False)


def _register_variable_default_values(ucr: ConfigRegistry) -> None:
    """Create base-default.conf layer containig all default values"""
    info = _get_config_registry_info()
    _ucr = ConfigRegistry(write_registry=ConfigRegistry.DEFAULTS)
    _ucr.load()
    defaults: dict[str, str | None] = {}
    default_variables = info.get_variables()
    for key, variable in default_variables.items():
        value = variable.get('default')
        if value:
            defaults[key] = value
    for key in _ucr:
        if key not in default_variables:
            defaults[key] = None

    changed = {key: (old, new) for key, (old, new) in _ucr.update(defaults).items() if old != new}
    _ucr.save()
    ucr.load()
    _run_changed(ucr, changed, 'I: %s will be set in scope "%s"')


HANDLERS: dict[str, tuple[Callable[[list[str], dict[str, Any]], Iterator[str] | None], int]] = {
    'set': (handler_set, 1),
    'unset': (handler_unset, 1),
    'dump': (handler_dump, 0),
    'update': (handler_update, 0),
    'commit': (handler_commit, 0),
    'register': (handler_register, 1),
    'unregister': (handler_unregister, 1),
    'filter': (handler_filter, 0),
    'search': (handler_search, 0),
    'get': (handler_get, 1),
    'info': (handler_info, 1),
}

# action options: each of these options perform an action
OPT_ACTIONS: dict[str, list] = {
    # name: [function, state, (alias list)]
    'help': [handler_help, False, ('-h', '-?')],
    'version': [handler_version, False, ('-v',)],
    'debug': [lambda args: None, False, ()],
}

# filter options: these options define filter for the output
OPT_FILTERS: dict[str, list] = {
    # name: [prio, function, state, (valid actions)]
    'keys-only': [0, filter_keys_only, False, ('dump', 'search')],
    'sort': [10, filter_sort, False, ('dump', 'search', 'info')],
    'shell': [99, filter_shell, False, ('dump', 'search', 'get')],
}

BOOL, STRING = range(2)

OPT_COMMANDS: dict[str, dict[str, Any]] = {
    'set': {
        'force': [BOOL, False],
        'ldap-policy': [BOOL, False],
        'schedule': [BOOL, False],
        'ignore-check': [BOOL, False],
    },
    'unset': {
        'force': [BOOL, False],
        'ldap-policy': [BOOL, False],
        'schedule': [BOOL, False],
    },
    'search': {
        'key': [BOOL, False],
        'value': [BOOL, False],
        'all': [BOOL, False],
        'brief': [BOOL, False],
        'category': [STRING, None],
        'non-empty': [BOOL, False],
        'verbose': [BOOL, False],
    },
    'filter': {
        'encode-utf8': [BOOL, False],
        'disallow-execution': [BOOL, False],
    },
}


def main(args: list[str]) -> int:
    """Run config registry."""
    try:
        # close your eyes ...
        if not args:
            args.append('--help')
        # search for options in command line arguments
        while args and args[0].startswith('-'):
            arg = args.pop(0)
            # is action option?
            for key, opt in OPT_ACTIONS.items():
                if arg[2:] == key or arg in opt[2]:
                    opt[1] = True
                    break
            else:
                # not an action option; is a filter option?
                try:
                    OPT_FILTERS[arg[2:]][2] = True
                except LookupError:
                    print('E: unknown option %s' % (arg,), file=sys.stderr)
                    sys.exit(1)

        # is action already defined by global option?
        for name, (func, state, _aliases) in OPT_ACTIONS.items():
            if state:
                func(args)

        # find action
        try:
            action = args.pop(0)
        except IndexError:
            print('E: missing action, see --help', file=sys.stderr)
            sys.exit(1)
        # COMPAT: the 'shell' command is now an option and equivalent to
        # --shell search
        if action == 'shell':
            action = 'search'
            # activate shell option
            OPT_FILTERS['shell'][2] = True
            # switch to old, brief output
            OPT_COMMANDS['search']['brief'][1] = True

            tmp = []
            if not args:
                tmp.append('')
            else:
                for arg in args:
                    if not arg.startswith('--'):
                        tmp.append('^%s$' % arg)
                    else:
                        tmp.append(arg)
            args = tmp

        # set 'sort' option by default for dump and search
        if action in ['dump', 'search', 'info']:
            OPT_FILTERS['sort'][2] = True

        # set brief option when generating shell output
        if OPT_FILTERS['shell'][2]:
            OPT_COMMANDS['search']['brief'][1] = True

        # if a filter option is set: verify that a valid command is given
        for name, (_prio, func, state, actions) in OPT_FILTERS.items():
            if state and action not in actions:
                print('E: invalid option --%s for command %s' % (name, action), file=sys.stderr)
                sys.exit(1)

        # check command options
        cmd_opts = OPT_COMMANDS.get(action, {})
        while args and args[0].startswith('--'):
            arg = args.pop(0)
            if action in ('set', 'unset') and arg == '--forced':
                arg = '--force'
            try:
                cmd_opt_tuple = cmd_opts[arg[2:]]
            except LookupError:
                print('E: invalid option %s for command %s' % (arg, action), file=sys.stderr)
                sys.exit(1)
            else:
                if cmd_opt_tuple[0] == BOOL:
                    cmd_opt_tuple[1] = True
                else:  # STRING
                    try:
                        cmd_opt_tuple[1] = args.pop(0)
                    except IndexError:
                        msg = 'E: option %s for command %s expects an argument'
                        print(msg % (arg, action), file=sys.stderr)
                        sys.exit(1)

        # Drop type
        cmd_opts = {key: value for key, (typ, value) in cmd_opts.items()}

        # action!
        try:
            handler_func, min_args = HANDLERS[action]
        except LookupError:
            print('E: unknown action "%s", see --help' % (action,), file=sys.stderr)
            sys.exit(1)
        else:
            # enough arguments?
            if len(args) < min_args:
                missing_parameter(action)

            # if any filter option is set
            cmd_opts['exit_code'] = 0
            result = handler_func(args, cmd_opts)
            if result is None:
                return cmd_opts['exit_code']

            results = result
            # let the filter options do their job
            for (_prio, filter_func, state, _actions) in sorted(OPT_FILTERS.values()):
                if not state:
                    continue
                results = filter_func(args, results)

            for line in results:
                print(line)

    except (OSError, TypeError):
        if OPT_ACTIONS['debug'][1]:
            raise
        exception_occured()
    return cmd_opts['exit_code']
