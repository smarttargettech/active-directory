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

"""command line frontend to univention-directory-manager (module)"""


import base64
import getopt
import os
import subprocess
import sys
from collections.abc import Sequence  # noqa: F401
from ipaddress import IPv4Address, IPv4Network
from logging import getLogger
from typing import TypeVar, overload


try:
    from typing import Literal  # noqa: F401
except ImportError:
    pass

import ldap

import univention.admin.modules
import univention.admin.objects
import univention.admin.uexceptions
import univention.admin.uldap
import univention.config_registry
import univention.logging
from univention.admin.layout import Group
from univention.admin.syntax import ldapFilter


log = getLogger('ADMIN')

univention.admin.modules.update()


class OperationFailed(Exception):

    def __init__(self, msg=None):  # type: (Optional[str]) -> None
        self.msg = msg

    def __str__(self):  # type: () -> str
        return self.msg or ''


def usage(stream):  # type: (IO[str]) -> None
    print('univention-directory-manager: command line interface for managing UCS', file=stream)
    print('copyright (c) 2001-@%@copyright_lastyear@%@ Univention GmbH, Germany', file=stream)
    print('', file=stream)
    print('Syntax:', file=stream)
    print('  univention-directory-manager module action [options]', file=stream)
    print('  univention-directory-manager [--help] [--version]', file=stream)
    print('', file=stream)
    print('actions:', file=stream)
    print('  %-32s %s' % ('create:', 'Create a new object'), file=stream)
    print('  %-32s %s' % ('modify:', 'Modify an existing object'), file=stream)
    print('  %-32s %s' % ('remove:', 'Remove an existing object'), file=stream)
    print('  %-32s %s' % ('list:', 'List objects'), file=stream)
    print('  %-32s %s' % ('move:', 'Move object in directory tree'), file=stream)
    print('', file=stream)
    print('  %-32s %s' % ('-h | --help | -?:', 'print this usage message'), file=stream)
    print('  %-32s %s' % ('--version:', 'print version information'), file=stream)
    print('', file=stream)
    print('general options:', file=stream)
    print('  --%-30s %s' % ('binddn', 'bind DN'), file=stream)
    print('  --%-30s %s' % ('bindpwd', 'bind password'), file=stream)
    print('  --%-30s %s' % ('bindpwdfile', 'file containing bind password'), file=stream)
    print('  --%-30s %s' % ('logfile', 'path and name of the logfile to be used'), file=stream)
    print('  --%-30s %s' % ('tls', '0 (no); 1 (try); 2 (must)'), file=stream)
    print('', file=stream)
    print('create options:', file=stream)
    print('  --%-30s %s' % ('position', 'Set position in tree'), file=stream)
    print('  --%-30s %s' % ('set', 'Set variable to value, e.g. foo=bar'), file=stream)
    print('  --%-30s %s' % ('superordinate', 'Use superordinate module'), file=stream)
    print('  --%-30s %s' % ('option', 'Use only given module options'), file=stream)
    print('  --%-30s %s' % ('append-option', 'Append the module option'), file=stream)
    print('  --%-30s %s' % ('remove-option', 'Remove the module option'), file=stream)
    print('  --%-30s %s' % ('policy-reference', 'Reference to policy given by DN'), file=stream)
    print('  --%-30s   ' % ('ignore_exists'), file=stream)
    print('', file=stream)
    print('modify options:', file=stream)
    print('  --%-30s %s' % ('dn', 'Edit object with DN'), file=stream)
    print('  --%-30s %s' % ('set', 'Set variable to value, e.g. foo=bar'), file=stream)
    print('  --%-30s %s' % ('append', 'Append value to variable, e.g. foo=bar'), file=stream)
    print('  --%-30s %s' % ('remove', 'Remove value from variable, e.g. foo=bar'), file=stream)
    print('  --%-30s %s' % ('option', 'Use only given module options'), file=stream)
    print('  --%-30s %s' % ('append-option', 'Append the module option'), file=stream)
    print('  --%-30s %s' % ('remove-option', 'Remove the module option'), file=stream)
    print('  --%-30s %s' % ('policy-reference', 'Reference to policy given by DN'), file=stream)
    print('  --%-30s %s' % ('policy-dereference', 'Remove reference to policy given by DN'), file=stream)
    print('  --%-30s   ' % ('ignore_not_exists'), file=stream)
    print('', file=stream)
    print('remove options:', file=stream)
    print('  --%-30s %s' % ('dn', 'Remove object with DN'), file=stream)
    print('  --%-30s %s' % ('superordinate', 'Use superordinate module'), file=stream)
    print('  --%-30s %s' % ('filter', 'Lookup filter e.g. foo=bar'), file=stream)
    print('  --%-30s %s' % ('remove_referring', 'remove referring objects'), file=stream)
    print('  --%-30s   ' % ('ignore_not_exists'), file=stream)
    print('', file=stream)
    print('list options:', file=stream)
    print('  --%-30s %s' % ('filter', 'Lookup filter e.g. foo=bar'), file=stream)
    print('  --%-30s %s' % ('properties', 'object properties to list'), file=stream)
    print('  --%-30s %s' % ('position', 'Search underneath of position in tree'), file=stream)
    print('  --%-30s %s' % ('policies', 'List policy-based settings:'), file=stream)
    print('    %-30s %s' % ('', '0:short, 1:long (with policy-DN)'), file=stream)
    print('', file=stream)
    print('move options:', file=stream)
    print('  --%-30s %s' % ('dn', 'Move object with DN'), file=stream)
    print('  --%-30s %s' % ('position', 'Move to position in tree'), file=stream)
    print('', file=stream)
    print('Description:', file=stream)
    print('  univention-directory-manager is a tool to handle the configuration for UCS', file=stream)
    print('  on command line level.', file=stream)
    print('  Use "univention-directory-manager modules" for a list of available modules.', file=stream)
    print('', file=stream)


def version(stream):  # type: (IO[str]) -> None
    print('univention-directory-manager @%@package_version@%@', file=stream)


def _print_property(
    module,  # type: univention.admin.modules.UdmModule
    action,  # type: str
    name,  # type: str
    stream,  # type: IO[str]
):  # type: (...) -> None
    property = module.property_descriptions.get(name)
    if property is None:
        print('E: unknown property %s of module %s' % (name, univention.admin.modules.name(module)), file=stream)
        return

    required = {
        'create': False,
        'modify': False,
        'remove': False,
        'editable': True,
    }

    if property.required:
        required['create'] = True
    if property.identifies:
        required['modify'] = True
        required['remove'] = True
    if not property.editable:
        required['modify'] = False
        required['remove'] = False
        required['editable'] = False

    op = ''
    if required.get(action):
        op = '*'
    elif action not in required:
        if required['create']:
            op += 'c'
        if required['modify']:
            op += 'm'
        if required['remove']:
            op += 'r'
        if not required['editable']:
            op += 'e'
    flags = [op] if op else []
    if property.options:
        flags.extend(property.options)
    if property.multivalue:
        flags.append('[]')
    flag = ' (%s)' % (','.join(flags),) if flags else ''

    print('\t\t%-40s %s' % (name + flag, property.short_description), file=stream)


def module_usage(
    information,  # type: Dict[univention.admin.modules.UdmModule, Tuple[Dict[str, univention.admin.property], Dict[str, univention.admin.option]]]
    action='',  # type: str
    stream=sys.stdout,  # type: IO[str]
):  # type: (...) -> None
    """Print properties and options of module and its superordinates."""
    for module, (_properties, options) in information.items():
        if options:
            print('', file=stream)
            print('%s options:' % module.module, file=stream)
            for name, option in options.items():
                print('  %-32s %s' % (name, option.short_description), file=stream)

        print('', file=stream)
        print('%s variables:' % module.module, file=stream)

        if not hasattr(module, "layout"):
            continue
        for moduletab in module.layout:
            print('  %s:' % (moduletab.label), file=stream)

            for row in moduletab.layout:
                if isinstance(row, Group):
                    print('\t%s' % row.label, file=stream)
                    for row in row.layout:
                        if isinstance(row, str):
                            _print_property(module, action, row, stream)
                            continue
                        for item in row:
                            _print_property(module, action, item, stream)
                else:
                    if isinstance(row, str):
                        _print_property(module, action, row, stream)
                        continue
                    for item in row:
                        _print_property(module, action, item, stream)


def module_information(
    module,  # type: univention.admin.modules.UdmModule
    identifies_only=False,  # type: bool
):  # type: (...) -> Dict[univention.admin.modules.UdmModule, Tuple[Dict[str, univention.admin.property], Dict[str, univention.admin.option]]]
    """Collect properties and options of module itself and its superordinates."""
    information = {module: ({}, {})}  # type: Dict[univention.admin.modules.UdmModule, Tuple[Dict[str, univention.admin.property], Dict[str, univention.admin.option]]]
    for superordinate in univention.admin.modules.superordinates(module):
        information.update(module_information(superordinate, identifies_only=True))

    if not identifies_only:
        for name, property in module.property_descriptions.items():
            information[module][0][name] = property
        if hasattr(module, 'options'):
            for name, option in module.options.items():
                information[module][1][name] = option

    return information


_V = TypeVar("_V")  # noqa: PYI018


# FIXME: for the automatic IP address assignment, we need to make sure that
# the network is set before the IP address (see Bug #24077, comment 6)
# The following code is a workaround to make sure that this is the
# case, however, this should be fixed correctly.
# This workaround has been documented as Bug #25163.
def _tmp_cmp(i):  # type: (Tuple[str, _V]) -> Tuple[str, _V]
    if i[0] == 'mac':  # must be set before network, dhcpEntryZone
        return ("\x00", i[1])
    if i[0] == 'network':  # must be set before ip, dhcpEntryZone, dnsEntryZoneForward, dnsEntryZoneReverse
        return ("\x01", i[1])
    if i[0] in ('ip', 'mac'):  # must be set before dnsEntryZoneReverse, dnsEntryZoneForward
        return ("\x02", i[1])
    return i


def object_input(
    module,  # type: univention.admin.modules.UdmModule
    object,
    input,  # type: Dict[str, Union[str, List[str]]]
    append=None,  # type: Optional[Dict[str, List[str]]]
    remove=None,  # type: Optional[Dict[str, List[str]]]
    stderr=None,  # type: Optional[IO[str]]
):  # type: (...) -> None
    if append:
        for key, values in sorted(append.items(), key=_tmp_cmp):
            if key in object and not object.has_property(key):
                opts = module.property_descriptions[key].options
                if len(opts) == 1:
                    object.options.extend(opts)
                    print('WARNING: %s was set without --append-option. Automatically appending %s.' % (key, ', '.join(opts)), file=stderr)

            if module.property_descriptions[key].syntax.name == 'file':
                if os.path.exists(values):
                    with open(values) as fh:
                        object[key] = fh.read()
                else:
                    print('WARNING: file not found: %s' % values, file=stderr)
            else:
                values = [module.property_descriptions[key].syntax.parse_command_line(x) for x in values]
                current_values = list(object[key] or [])
                if current_values == ['']:
                    current_values = []

                for val in values:
                    if val in current_values:
                        print('WARNING: cannot append %s to %s, value exists' % (val, key), file=stderr)
                    else:
                        current_values.append(val)

                if not module.property_descriptions[key].multivalue:
                    try:
                        current_values = current_values[-1]
                    except IndexError:
                        current_values = None

                try:
                    object[key] = current_values
                except univention.admin.uexceptions.valueInvalidSyntax as errmsg:
                    raise OperationFailed('E: %s' % (errmsg,))

    if remove:
        for key, values in remove.items():
            current_values = [object[key]] if not module.property_descriptions[key].multivalue else list(object[key])
            if values is None:
                current_values = []
            else:
                vallist = [values] if isinstance(values, str) else values
                vallist = [module.property_descriptions[key].syntax.parse_command_line(x) for x in vallist]

                for val in vallist:
                    try:
                        normalized_val = module.property_descriptions[key].syntax.parse(val)
                    except (univention.admin.uexceptions.valueInvalidSyntax, univention.admin.uexceptions.valueError):
                        normalized_val = None

                    if val in current_values:
                        current_values.remove(val)
                    elif normalized_val is not None and normalized_val in current_values:
                        current_values.remove(normalized_val)
                    else:
                        print("WARNING: cannot remove %s from %s, value does not exist" % (val, key), file=stderr)
            if not module.property_descriptions[key].multivalue:
                try:
                    current_values = current_values[0]
                except IndexError:
                    current_values = None
            object[key] = current_values

    if input:
        for key, value in sorted(input.items(), key=_tmp_cmp):
            if key in object and not object.has_property(key):
                opts = module.property_descriptions[key].options
                if len(opts) == 1:
                    object.options.extend(opts)
                    print('WARNING: %s was set without --append-option. Automatically appending %s.' % (key, ', '.join(opts)), file=stderr)

            if module.property_descriptions[key].syntax.name == 'binaryfile':
                if value == '':
                    object[key] = value
                elif os.path.exists(value):
                    with open(value) as fh:
                        content = fh.read()
                        if "----BEGIN CERTIFICATE-----" in content:
                            content = content.replace('----BEGIN CERTIFICATE-----', '')
                            content = content.replace('----END CERTIFICATE-----', '')
                            object[key] = base64.b64decode(content.encode("utf-8")).decode("utf-8")
                        else:
                            object[key] = content
                else:
                    print('WARNING: file not found: %s' % value, file=stderr)

            else:
                if isinstance(value, list) and len(value) > 1:
                    print('WARNING: multiple values for %s given via --set. Use --append instead!' % (key,), file=stderr)

                values = value if isinstance(value, list) else [value]
                values = [module.property_descriptions[key].syntax.parse_command_line(x) for x in values]
                value = values if module.property_descriptions[key].multivalue else values[-1]

                try:
                    object[key] = value
                except univention.admin.uexceptions.ipOverridesNetwork as exc:
                    print('WARNING: %s' % (exc,), file=stderr)
                except univention.admin.uexceptions.valueMayNotChange:
                    raise univention.admin.uexceptions.valueMayNotChange(key)  # upstream exception is formatted bad


def list_available_modules(stream):  # type: (IO[str]) -> None
    print("Available Modules are:", file=stream)
    for mod in sorted(univention.admin.modules.modules):
        print("  %s" % mod, file=stream)


def main(
    arglist,  # type: List[str]
    stdout=sys.stdout,  # type: IO[str]
    stderr=sys.stderr,  # type: IO[str]
):  # type: (...) -> None
    try:
        _doit(arglist, stdout=stdout, stderr=stderr)
    except ldap.SERVER_DOWN:
        raise OperationFailed("E: The LDAP Server is currently not available.")
    except univention.admin.uexceptions.base as exc:
        msg = str(exc)
        log.warning('%s', msg)
        raise OperationFailed(msg)


def _doit(
    arglist,  # type: List[str]
    stdout=sys.stdout,  # type: IO[str]
    stderr=sys.stderr,  # type: IO[str]
):  # type: (...) -> None
    # parse module and action
    if len(arglist) < 2:
        usage(stderr)
        raise OperationFailed()

    module_name = arglist[1]
    if module_name in ['-h', '--help', '-?']:
        usage(stdout)
        return

    if module_name == '--version':
        version(stdout)
        return

    if module_name == 'modules':
        list_available_modules(stdout)
        return

    remove_referring = False
    recursive = True
    # parse options
    longopts = ['position=', 'dn=', 'set=', 'append=', 'remove=', 'superordinate=', 'option=', 'append-option=', 'remove-option=', 'filter=', 'tls=', 'ignore_exists', 'ignore_not_exists', 'logfile=', 'policies=', 'binddn=', 'bindpwd=', 'bindpwdfile=', 'policy-reference=', 'policy-dereference=', 'remove_referring', 'recursive', 'properties=']
    try:
        opts, args = getopt.getopt(arglist[3:], '', longopts)
    except getopt.error as msg:
        raise OperationFailed(str(msg))

    if args and isinstance(args, list):
        msg = "WARNING: the following arguments are ignored:"
        for argument in args:
            msg = '%s "%s"' % (msg, argument)
        print(msg, file=stderr)

    position_dn = ''
    dn = ''
    binddn = None  # type: Optional[str]
    bindpwd = None  # type: Optional[str]
    list_policies = False
    policies_with_DN = False
    policyOptions = []  # type: List[str]
    logfile = '/var/log/univention/directory-manager-cmd.log'
    tls = 2
    ignore_exists = False
    ignore_not_exists = False
    superordinate_dn = ''
    parsed_append_options = []  # type: List[str]
    parsed_remove_options = []  # type: List[str]
    parsed_options = []  # type: List[str]
    filter = ''
    input = {}  # type: Dict[str, Union[str, List[str]]]
    append = {}  # type: Dict[str, List[str]]
    remove = {}  # type: Dict[str, List[str]]
    policy_reference = []  # type: List[str]
    policy_dereference = []  # type: List[str]
    properties = []  # type: List[str]
    for opt, val in opts:
        if opt == '--position':
            position_dn = val
        elif opt == '--logfile':
            logfile = val
        elif opt == '--policies':
            list_policies = True
            if val == "1":
                policies_with_DN = True
            else:
                policyOptions = ['-s']
        elif opt == '--binddn':
            binddn = val
        elif opt == '--bindpwd':
            bindpwd = val
        elif opt == '--bindpwdfile':
            try:
                with open(val) as fp:
                    bindpwd = fp.read().strip()
            except OSError as exc:
                raise OperationFailed('E: could not read bindpwd from file (%s)' % (exc,))
        elif opt == '--dn':
            dn = val
        elif opt == '--tls':
            tls = val
        elif opt == '--ignore_exists':
            ignore_exists = True
        elif opt == '--ignore_not_exists':
            ignore_not_exists = True
        elif opt == '--superordinate':
            superordinate_dn = val
        elif opt == '--option':
            parsed_options.append(val)
        elif opt == '--append-option':
            parsed_append_options.append(val)
        elif opt == '--remove-option':
            parsed_remove_options.append(val)
        elif opt == '--filter':
            ldapFilter.parse(val)
            filter = val
        elif opt == '--policy-reference':
            policy_reference.append(val)
        elif opt == '--policy-dereference':
            policy_dereference.append(val)

    configRegistry = univention.config_registry.ConfigRegistry()
    configRegistry.load()

    debug_level = int(configRegistry.get('directory/manager/cmd/debug/level', 0))

    if logfile:
        univention.logging.basicConfig(filename=logfile, univention_debug_level=debug_level)
    else:
        print("WARNING: no logfile specified", file=stderr)

    if not binddn or not bindpwd:
        for _binddn, secret_filename in (
                ('cn=admin,' + configRegistry['ldap/base'], '/etc/ldap.secret'),
                (configRegistry['ldap/hostdn'], '/etc/machine.secret'),
        ):
            if os.path.exists(secret_filename):
                binddn = _binddn
                try:
                    with open(secret_filename) as secretFile:
                        bindpwd = secretFile.read().strip('\n')
                except OSError:
                    raise OperationFailed('E: Permission denied, try --binddn and --bindpwd')
                policyOptions.extend(['-D', binddn, '-y', secret_filename])
                break
    else:
        policyOptions.extend(['-D', binddn, '-w', bindpwd])  # FIXME: not so nice

    log.debug("using %s account", binddn)

    try:
        module = univention.admin.modules._get(module_name)
    except LookupError:
        print("unknown module %s." % module_name, file=stderr)
        print("", file=stderr)
        list_available_modules(stderr)
        raise OperationFailed()

    try:
        lo = univention.admin.uldap.access(host=configRegistry['ldap/master'], port=int(configRegistry.get('ldap/master/port', '7389')), base=module.object.ldap_base, binddn=binddn, start_tls=tls, bindpw=bindpwd)
    except Exception as exc:
        log.warning('authentication error: %s', exc)
        raise OperationFailed('authentication error: %s' % (exc,))

    if not position_dn and superordinate_dn:
        position_dn = superordinate_dn
    elif not position_dn:
        position_dn = module.object.ldap_base

    try:
        position = univention.admin.uldap.position(module.object.ldap_base)
        position.setDn(position_dn)
    except univention.admin.uexceptions.noObject:
        raise OperationFailed('E: Invalid position')

    # initialise modules
    if module_name == 'settings/usertemplate':
        univention.admin.modules.init(lo, position, univention.admin.modules._get('users/user'))
    univention.admin.modules.init(lo, position, module)

    information = module_information(module)

    superordinate = None
    if superordinate_dn and univention.admin.modules.superordinate(module):
        # the superordinate itself also has a superordinate, get it!
        superordinate = univention.admin.objects.get_superordinate(module, None, lo, superordinate_dn)
        if superordinate is None:
            raise OperationFailed('E: %s is not a superordinate for %s.' % (superordinate_dn, univention.admin.modules.name(module)))

    if len(arglist) == 2:
        usage(stdout)
        module_usage(information, stream=stdout)
        raise OperationFailed()

    action = arglist[2]

    if len(arglist) == 3 and action != 'list':
        usage(stdout)
        module_usage(information, action, stdout)
        raise OperationFailed()

    for opt, val in opts:
        if opt == '--set':
            name, _delim, value = val.partition('=')

            for (properties, _options) in information.values():
                if name in properties:
                    if not properties[name].cli_enabled:
                        continue
                    if properties[name].multivalue:
                        input.setdefault(name, [])
                        if value:
                            input[name].append(value)
                    else:
                        input[name] = value

            if name not in input:
                print("WARNING: No attribute with name '%s' in this module, value not set." % name, file=stderr)
        elif opt == '--append':
            name, _delim, value = val.partition('=')
            for (properties, _options) in information.values():
                if name in properties:
                    if not properties[name].cli_enabled:
                        continue
                    if not properties[name].multivalue:
                        print('WARNING: using --append on a single value property (%s). Use --set instead!' % (name,), file=stderr)

                    append.setdefault(name, [])
                    if value:
                        append[name].append(value)
            if name not in append:
                print("WARNING: No attribute with name %s in this module, value not appended." % name, file=stderr)

        elif opt == '--remove':
            name, _delim, value = val.partition('=')
            value = value or None
            for (properties, _options) in information.values():
                if name in properties:
                    if not properties[name].cli_enabled:
                        continue
                    if properties[name].multivalue:
                        if value is None:
                            remove[name] = value
                        elif value:
                            remove.setdefault(name, [])
                            if remove[name] is not None:
                                remove[name].append(value)
                    else:
                        remove[name] = value
            if name not in remove:
                print("WARNING: No attribute with name %s in this module, value not removed." % name, file=stderr)
        elif opt == '--remove_referring':
            remove_referring = True
        elif opt == '--recursive':
            recursive = True
        elif opt == '--properties':
            properties.append(val)

    if not properties:
        properties = ['*']

    cli = CLI(module_name, module, dn, lo, position, superordinate, stdout=stdout, stderr=stderr)
    if action in ('create', 'new'):
        cli.create(input, append, ignore_exists, parsed_options, parsed_append_options, parsed_remove_options, policy_reference)
    elif action in ('modify', 'edit'):
        cli.modify(input, append, remove, parsed_append_options, parsed_remove_options, parsed_options, policy_reference, policy_dereference, ignore_not_exists=ignore_not_exists)
    elif action == 'move':
        cli.move(position_dn)
    elif action in ('remove', 'delete'):
        cli.remove(remove_referring=remove_referring, recursive=recursive, ignore_not_exists=ignore_not_exists, filter=filter)
    elif action in ('list', 'lookup'):
        cli.list(list_policies, filter, superordinate_dn, policyOptions, policies_with_DN, properties)
    else:
        print("Unknown or no action defined", file=stderr)
        print('', file=stderr)
        raise OperationFailed()


class CLI:

    def __init__(
        self,
        module_name,  # type: str
        module,  # type: univention.admin.modules.UdmModule
        dn,  # type: str
        lo,  # type: univention.admin.uldap.access
        position,  # type: univention.admin.uldap.position
        superordinate,  # type: Optional[univention.admin.handlers.simpleLdap]
        stdout=sys.stdout,  # type: IO[str]
        stderr=sys.stderr,  # type: IO[str]
    ):  # type: (...) -> None
        self.module_name = module_name
        self.module = module
        self.dn = dn
        self.lo = lo
        self.position = position
        self.superordinate = superordinate
        self.stdout = stdout
        self.stderr = stderr

    def create(self, *args, **kwargs):  # type: (*Any, **Any) -> Any
        return self._create(self.module_name, self.module, self.dn, self.lo, self.position, self.superordinate, *args, **kwargs)

    def modify(self, *args, **kwargs):  # type: (*Any, **Any) -> Any
        return self._modify(self.module_name, self.module, self.dn, self.lo, self.position, self.superordinate, *args, **kwargs)

    def move(self, *args, **kwargs):  # type: (*Any, **Any) -> Any
        return self._move(self.module_name, self.module, self.dn, self.lo, self.position, self.superordinate, *args, **kwargs)

    def remove(self, *args, **kwargs):  # type: (*Any, **Any) -> Any
        return self._remove(self.module_name, self.module, self.dn, self.lo, self.position, self.superordinate, *args, **kwargs)

    def list(self, *args, **kwargs):  # type: (*Any, **Any) -> Any
        return self._list(self.module_name, self.module, self.dn, self.lo, self.position, self.superordinate, *args, **kwargs)

    def _create(
        self,
        module_name,  # type: str
        module,  # type: univention.admin.modules.UdmModule
        dn,  # type: str
        lo,  # type: univention.admin.uldap.access
        position,  # type: univention.admin.uldap.position
        superordinate,  # type: Optional[univention.admin.handlers.simpleLdap]
        input,  # type: Dict[str, Union[str, List[str]]]
        append,  # type: Dict[str, List[str]]
        ignore_exists,  # type: bool
        parsed_options,  # type: List[str]
        parsed_append_options,  # type: List[str]
        parsed_remove_options,  # type: List[str]
        policy_reference,  # type: List[str]
    ):  # type: (...) -> None
        if not univention.admin.modules.supports(module_name, 'add'):
            raise OperationFailed('Create %s not allowed' % module_name)

        try:
            object = module.object(None, lo, position=position, superordinate=superordinate)
        except univention.admin.uexceptions.insufficientInformation as exc:
            raise OperationFailed('E: %s' % (exc,))

        if parsed_options:
            object.options = parsed_options
        for option in parsed_append_options:
            object.options.append(option)
        for option in parsed_remove_options:
            try:
                object.options.remove(option)
            except ValueError:
                pass

        object.open()
        try:
            object_input(module, object, input, append=append, stderr=self.stderr)
        except univention.admin.uexceptions.nextFreeIp:
            if not ignore_exists:
                raise OperationFailed('E: No free IP address found')
        except univention.admin.uexceptions.valueInvalidSyntax as err:
            raise OperationFailed('E: %s' % (err,))

        default_containers = object.get_default_containers(lo)
        if default_containers and position.isBase() and not any(lo.compare_dn(default_container, position.getDn()) for default_container in default_containers):
            print('WARNING: The object is not going to be created underneath of its default containers.', file=self.stderr)

        object.policy_reference(*policy_reference)

        exists_msg = None
        created = False
        try:
            dn = object.create()
            created = True
        except univention.admin.uexceptions.objectExists as exc:
            exists_msg = '%s' % (exc.dn,)
        except univention.admin.uexceptions.uidAlreadyUsed as user:
            exists_msg = '(uid) %s' % user
        except univention.admin.uexceptions.groupNameAlreadyUsed as group:
            exists_msg = '(group) %s' % group
        except univention.admin.uexceptions.dhcpServerAlreadyUsed as name:
            exists_msg = '(dhcpserver) %s' % name
        except univention.admin.uexceptions.macAlreadyUsed as mac:
            exists_msg = '(mac) %s' % mac
        except univention.admin.uexceptions.noLock as e:
            exists_msg = '(nolock) %s' % (e,)
        except univention.admin.uexceptions.invalidOptions as e:
            print('E: invalid Options: %s' % e, file=self.stderr)
            if not ignore_exists:
                raise OperationFailed()
        except (univention.admin.uexceptions.invalidDhcpEntry, univention.admin.uexceptions.insufficientInformation, univention.admin.uexceptions.noObject, univention.admin.uexceptions.circularGroupDependency, univention.admin.uexceptions.invalidChild) as exc:
            raise OperationFailed('E: %s' % (exc,))

        if exists_msg and not ignore_exists:
            raise OperationFailed('E: Object exists: %s' % exists_msg)
        elif exists_msg:
            print('Object exists: %s' % exists_msg, file=self.stdout)
        elif created:
            print('Object created: %s' % dn, file=self.stdout)

    def _move(
        self,
        module_name,  # type: str
        module,  # type: univention.admin.modules.UdmModule
        dn,  # type: str
        lo,  # type: univention.admin.uldap.access
        position,  # type: univention.admin.uldap.position
        superordinate,  # type: Optional[univention.admin.handlers.simpleLdap]
        position_dn,  # type: str
    ):  # type: (...) -> None
        if not dn:
            raise OperationFailed('E: DN is missing')

        object_modified = 0

        if not univention.admin.modules.supports(module_name, 'edit'):
            raise OperationFailed('Modify %s not allowed' % module_name)

        try:
            object = univention.admin.objects.get(module, None, lo, position='', dn=dn)
        except univention.admin.uexceptions.noObject:
            raise OperationFailed('E: object not found')

        object.open()

        if not univention.admin.modules.supports(module_name, 'move'):
            raise OperationFailed('Move %s not allowed' % module_name)

        if not position_dn:
            print("need new position for moving object", file=self.stderr)
        else:
            try:  # check if destination exists
                lo.get(position_dn, required=True)
            except (univention.admin.uexceptions.noObject, ldap.INVALID_DN_SYNTAX):
                raise OperationFailed("position does not exists: %s" % position_dn)
            rdn = ldap.dn.dn2str([ldap.dn.str2dn(dn)[0]])
            newdn = "%s,%s" % (rdn, position_dn)
            try:
                object.move(newdn)
                object_modified += 1
            except (univention.admin.uexceptions.noObject, univention.admin.uexceptions.ldapError, univention.admin.uexceptions.nextFreeIp, univention.admin.uexceptions.valueInvalidSyntax, univention.admin.uexceptions.invalidOperation) as exc:
                raise OperationFailed('E: %s' % (exc,))

        if object_modified > 0:
            print('Object modified: %s' % dn, file=self.stdout)
        else:
            print('No modification: %s' % dn, file=self.stdout)

    def _modify(
        self,
        module_name,  # type: str
        module,  # type: univention.admin.modules.UdmModule
        dn,  # type: str
        lo,  # type: univention.admin.uldap.access
        position,  # type: univention.admin.uldap.position
        superordinate,  # type: Optional[univention.admin.handlers.simpleLdap]
        input,  # type: Dict[str, Union[str, List[str]]]
        append,  # type: Dict[str, List[str]]
        remove,  # type: Dict[str, List[str]]
        parsed_append_options,  # type: List[str]
        parsed_remove_options,  # type: List[str]
        parsed_options,  # type: List[str]
        policy_reference,  # type: List[str]
        policy_dereference,  # type: List[str]
        ignore_not_exists,  # type: bool
    ):  # type: (...) -> None
        if not dn:
            raise OperationFailed('E: DN is missing')

        object_modified = 0

        if not univention.admin.modules.supports(module_name, 'edit'):
            raise OperationFailed('Modify %s not allowed' % module_name)

        try:
            object = univention.admin.objects.get(module, None, lo, position='', dn=dn)
        except univention.admin.uexceptions.noObject:
            if ignore_not_exists:
                print('Object not found: %s' % (dn or filter,), file=self.stdout)
                return
            raise OperationFailed('E: object not found')

        object.open()

        if any((input, append, remove, parsed_append_options, parsed_remove_options, parsed_options, policy_reference, policy_dereference)):
            if parsed_options:
                object.options = parsed_options
            for option in parsed_append_options:
                object.options.append(option)
            for option in parsed_remove_options[:]:
                try:
                    object.options.remove(option)
                except ValueError:
                    parsed_remove_options.remove(option)
                    print('WARNING: option %r is not set. Ignoring.' % (option,), file=self.stderr)

            try:
                object_input(module, object, input, append, remove, stderr=self.stderr)
            except univention.admin.uexceptions.valueMayNotChange as exc:
                raise OperationFailed(str(exc))

            object.policy_reference(*policy_reference)
            object.policy_dereference(*policy_dereference)

            if object.hasChanged(input.keys()) or object.hasChanged(append.keys()) or object.hasChanged(remove.keys()) or parsed_append_options or parsed_remove_options or parsed_options or object.policiesChanged():  # noqa: PLR0916
                try:
                    dn = object.modify()
                    object_modified += 1
                except (univention.admin.uexceptions.noObject, univention.admin.uexceptions.invalidDhcpEntry, univention.admin.uexceptions.circularGroupDependency, univention.admin.uexceptions.valueInvalidSyntax) as exc:
                    raise OperationFailed('E: %s' % (exc,))

        if object_modified > 0:
            print('Object modified: %s' % dn, file=self.stdout)
        else:
            print('No modification: %s' % dn, file=self.stdout)

    def _remove(
        self,
        module_name,  # type: str
        module,  # type: univention.admin.modules.UdmModule
        dn,  # type: str
        lo,  # type: univention.admin.uldap.access
        position,  # type: univention.admin.uldap.position
        superordinate,  # type: Optional[univention.admin.handlers.simpleLdap]
        recursive,  # type: bool
        remove_referring,  # type: bool
        ignore_not_exists,  # type: bool
        filter,  # type: str
    ):  # type: (...) -> None
        if not univention.admin.modules.supports(module_name, 'remove'):
            raise OperationFailed('Remove %s not allowed' % module_name)

        try:
            if dn and filter:
                object = univention.admin.modules.lookup(module, None, lo, scope='sub', superordinate=superordinate, base=dn, filter=filter, required=True, unique=True)[0]
            elif dn:
                object = univention.admin.modules.lookup(module, None, lo, scope='base', superordinate=superordinate, base=dn, filter=filter, required=True, unique=True)[0]
            elif filter:
                object = univention.admin.modules.lookup(module, None, lo, scope='sub', superordinate=superordinate, base=position.getDn(), filter=filter, required=True, unique=True)[0]
            else:
                raise OperationFailed('E: dn or filter needed')
        except (univention.admin.uexceptions.noObject, IndexError):
            if ignore_not_exists:
                print('Object not found: %s' % (dn or filter,), file=self.stdout)
                return
            raise OperationFailed('E: object not found')

        object.open()

        if remove_referring and univention.admin.objects.wantsCleanup(object):
            univention.admin.objects.performCleanup(object)

        if recursive:
            try:
                object.remove(recursive)
            except univention.admin.uexceptions.ldapError as msg:
                raise OperationFailed(str(msg))
        else:
            try:
                object.remove()
            except univention.admin.uexceptions.primaryGroupUsed as msg:
                raise OperationFailed('E: object in use: %s' % (msg,))
        print('Object removed: %s' % (dn or object.dn,), file=self.stdout)

    def _list(
        self,
        module_name,  # type: str
        module,  # type: univention.admin.modules.UdmModule
        dn,  # type: str
        lo,  # type: univention.admin.uldap.access
        position,  # type: univention.admin.uldap.position
        superordinate,  # type: Optional[univention.admin.handlers.simpleLdap]
        list_policies,  # type: bool
        filter,  # type: str
        superordinate_dn,  # type: str
        policyOptions,  # type: List[str]
        policies_with_DN,  # type: bool
        properties,  # type: List[str]
    ):  # type: (...) -> None
        if not univention.admin.modules.supports(module_name, 'search'):
            raise OperationFailed('Search %s not allowed' % module_name)

        print(filter, file=self.stdout)

        try:
            for object in univention.admin.modules.lookup(module, None, lo, scope='sub', superordinate=superordinate, base=position.getDn(), filter=filter):
                print('DN: %s' % univention.admin.objects.dn(object), file=self.stdout)
                if not univention.admin.modules.virtual(module_name):
                    object.open()
                    for key in object.keys():
                        if module.property_descriptions[key].lazy_loading_fn and key in properties:
                            module.property_descriptions[key].lazy_load(object)
                    for key, value in sorted(object.items()):
                        if not module.property_descriptions[key].show_in_lists:
                            continue
                        if key not in properties and '*' not in properties:
                            continue

                        s = module.property_descriptions[key].syntax
                        if module.property_descriptions[key].multivalue:
                            for v in value:
                                if s.tostring(v):
                                    print('  %s: %s' % (key, s.tostring(v)), file=self.stdout)
                                else:
                                    print('  %s: %s' % (key, None), file=self.stdout)
                        else:
                            if s.tostring(value):
                                print('  %s: %s' % (key, s.tostring(value)), file=self.stdout)
                            else:
                                print('  %s: %s' % (key, None), file=self.stdout)

                    for el in object.policies:
                        print('  %s: %s' % ('univentionPolicyReference', el), file=self.stdout)

                if list_policies:
                    print("  Policy-based Settings:", file=self.stdout)
                    client = get_policy(univention.admin.objects.dn(object), self.stdout, policyOptions, policies_with_DN)
                    print('', file=self.stdout)

                    if module_name == 'dhcp/host':
                        subnet_module = univention.admin.modules._get('dhcp/subnet')
                        # TODO: sharedsubnet_module = univention.admin.modules._get('dhcp/sharedsubnet')
                        ips = object['fixedaddress']
                        for ip in ips:
                            ip_ = IPv4Address("%s" % (ip,))
                            for subnet in univention.admin.modules.lookup(subnet_module, None, lo, scope='sub', superordinate=superordinate, base=superordinate_dn, filter=''):
                                if ip_ in IPv4Network("%(subnet)s/%(subnetmask)s" % subnet, strict=False):
                                    print("  Subnet-based Settings:", file=self.stdout)
                                    ddict = get_policy(subnet.dn, self.stdout, policyOptions, policies_with_DN)
                                    print('', file=self.stdout)
                                    print("  Merged Settings:", file=self.stdout)

                                    for key in ddict.keys():
                                        if key not in client:
                                            client[key] = ddict[key]

                                    if policies_with_DN:
                                        for key in client.keys():
                                            print("    Policy: " + client[key][0], file=self.stdout)
                                            print("    Attribute: " + key, file=self.stdout)
                                            for val in client[key][1]:
                                                print("    Value: " + val, file=self.stdout)
                                    else:
                                        for key in client.keys():
                                            for val in client[key]:
                                                print("    %s=%s" % (key, val), file=self.stdout)
                                    print('', file=self.stdout)

                print('', file=self.stdout)
        except (univention.admin.uexceptions.ldapError, univention.admin.uexceptions.valueInvalidSyntax) as errmsg:
            raise OperationFailed('%s' % (errmsg,))


@overload
def get_policy(
    dn,  # type: str
    stream,  # type: IO[str]
    policyOptions=None,  # type: Optional[Sequence[str]]
    policies_with_DN=False,  # type: Literal[False]
):  # type: (...) -> Dict[str, List[str]]
    pass


@overload
def get_policy(
    dn,  # type: str
    stream,  # type: IO[str]
    policyOptions,  # type: Optional[Sequence[str]]
    policies_with_DN,  # type: Literal[True]
):  # type: (...) -> Dict[str, Tuple[str, List[str]]]
    pass


def get_policy(
    dn,  # type: str
    stream=sys.stdout,  # type: IO[str]
    policyOptions=None,  # type: Optional[Sequence[str]]
    policies_with_DN=True,  # type: bool
):  # type: (...) -> Dict[str, Any]
    cmd = ['univention_policy_result']
    if policyOptions:
        cmd.extend(policyOptions)
    cmd.append(dn)

    policy = ''
    attribute = ''
    value = []  # type: List[str]
    client = {}  # type: Dict[str, Any]

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    assert proc.stdout is not None
    for line_ in proc.stdout:
        line = line_.decode('utf-8').strip()
        if not line or line.startswith(("DN: ", "POLICY ")):
            continue
        print("    %s" % line, file=stream)

        if not policies_with_DN:
            ckey, cval = line.split('=', 1)
            client.setdefault(ckey, []).append(cval)
            continue

        ckey, cval = line.split(': ', 1)
        if ckey == 'Policy':
            if policy:
                client[attribute] = (policy, value)
                value = []
            policy = cval
        elif ckey == 'Attribute':
            attribute = cval
        elif ckey == 'Value':
            value.append(cval)

    proc.wait()

    if policies_with_DN:
        client[attribute] = [policy, value]
        value = []
    return client


if __name__ == '__main__':
    main(sys.argv, sys.stdout, sys.stderr)
