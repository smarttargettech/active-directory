#!/usr/bin/python3
#
# Univention Management Console
#  module: manages Univention Config Registry variables
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2006-2025 Univention GmbH
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

import re
from io import StringIO
from re import Pattern
from typing import Any

import univention.info_tools as uit
from univention.config_registry import ConfigRegistry, handler_set, handler_unset, validate_key
from univention.config_registry_info import ConfigRegistryInfo, Variable
from univention.lib.i18n import Translation
from univention.management.console.base import Base, UMC_Error
from univention.management.console.config import ucr
from univention.management.console.modules.decorators import sanitize, simple_response
from univention.management.console.modules.sanitizers import (
    ChoicesSanitizer, DictSanitizer, PatternSanitizer, StringSanitizer,
)


_ = Translation('univention-management-console-module-ucr').translate


ONLINE_BASE = 'repository/online'
COMPONENT_BASE = f'{ONLINE_BASE}/component'
DEPRECATED_VARS = ['prefix', 'username', 'password', 'unmaintained', 'port']
DEPRECATED_GEN = [f'{ONLINE_BASE}/{dep}' for dep in DEPRECATED_VARS]
RE_KEY = re.compile(f'{COMPONENT_BASE}/([^/]+)/({"|".join(DEPRECATED_VARS)})')


class UCRKeySanitizer(StringSanitizer):

    def _sanitize(self, value: str, name: str, further_arguments: list[Any]) -> str | None:
        """
        sanitizing UCR keys

        :param value: Value to be sanitized
        :param name: name of the key
        :param further_arguments: List of further arguments
        :return: sanitized value or None if an Error is raised
        """
        value = super()._sanitize(value, name, further_arguments)
        b = StringIO()
        if not validate_key(value, b):
            error_message = b.getvalue()
            pre_error_message = _('A valid UCR variable name must contain at least one character and can only contain letters, numerals, "/", ".", ":", "_" and "-".')
            self.raise_validation_error(f'{pre_error_message} {error_message}')
            return
        return value


class Instance(Base):

    def init(self):
        # set the language in order to return the correctly localized labels/descriptions
        uit.set_language(self.locale.language)

    def __create_variable_info(self, options: dict) -> None:
        """
        creating variable infos

        :param options: List of options
        """
        all_info = ConfigRegistryInfo(registered_only=False)
        info = ConfigRegistryInfo(install_mode=True)
        info.read_customized()
        var = Variable()

        # description
        for line in options['descriptions']:
            text = line['text']
            if not text:
                continue
            if 'lang' in line:
                var[f'description[{line["lang"]}]'] = text
            else:
                var['description'] = text
        # categories
        if options['categories']:
            var['categories'] = ','.join(options['categories'])

        # type
        var['type'] = options['type']

        # are there any modifications?
        old_value = all_info.get_variable(options['key'])
        if old_value != var:
            # save
            info.add_variable(options['key'], var)
            info.write_customized()

    def is_readonly(self, key: str) -> bool:
        ucrinfo_system = ConfigRegistryInfo(registered_only=False, load_customized=False)
        var = ucrinfo_system.get_variable(key)
        if var:
            return var.get('readonly') in ('yes', '1', 'true')
        return False

    @sanitize(DictSanitizer({
        'object': DictSanitizer({
            'key': UCRKeySanitizer(required=True),
            'value': StringSanitizer(default=''),
        }),
    }))
    def add(self, request) -> None:
        # does the same as put
        ucr.load()
        already_set = set(ucr.keys()) & {v['object']['key'] for v in request.options}
        if already_set:
            raise UMC_Error(_('The UCR variable %s is already set.') % ('", "'.join(already_set)))

        self.put(request)

    @sanitize(DictSanitizer({
        'object': DictSanitizer({
            'key': UCRKeySanitizer(required=True),
            'value': StringSanitizer(default=''),
        }),
    }))
    def put(self, request) -> None:
        for _var in request.options:
            var = _var['object']
            value = var['value'] or ''
            key = var['key']
            if self.is_readonly(key):
                raise UMC_Error(_('The UCR variable %s is read-only and can not be changed!') % (key,))
            arg = [f'{key}={value}']
            opts = {}
            handler_set(arg, opts)
            if 'exit_code' in opts and opts['exit_code'] != 0:
                if 'type_errors' in opts and len(opts['type_errors']) > 0:
                    key, value = opts['type_errors'][0]
                    raise UMC_Error(_('The value %s is not valid for the UCR variable %s!') % (value, key))
                if 'type_def_error' in opts and len(opts['type_def_errors']) > 0:
                    type_, key, value = opts['type_def_errors'][0]
                    raise UMC_Error(_('Invalid UCR type definition for type %r of %r, value %r not set') % (type_, key, value))

            # handle descriptions, type, and categories
            if 'descriptions' in var or 'type' in var or 'categories' in var:
                self.__create_variable_info(var)
        self.finished(request.id, True)

    def remove(self, request) -> None:
        variables = [x for x in [x.get('object') for x in request.options] if x is not None]
        for var in variables:
            if self.is_readonly(var):
                raise UMC_Error(_('The UCR variable %s is read-only and can not be removed!') % (var,))

        handler_unset(variables)
        self.finished(request.id, True)

    def get(self, request) -> None:
        ucrReg = ConfigRegistry()
        ucrReg.load()
        ucrInfo = ConfigRegistryInfo(registered_only=False)

        # iterate over all requested variables
        results = []
        for key in request.options:
            info = ucrInfo.get_variable(str(key))
            value = ucrReg.get(str(key))
            if not info and (value or value == ''):
                # only the value available
                results.append({'key': key, 'value': value})
            elif info:
                # info (categories etc.) available
                info['value'] = value
                info['key'] = key
                results.append(info.normalize())
            else:
                # variable not available, request failed
                raise UMC_Error(_('The UCR variable %(key)s could not be found') % {'key': key})
        self.finished(request.id, results)

    def categories(self, request) -> None:
        ucrInfo = ConfigRegistryInfo(registered_only=False)
        categories = []
        for id, obj in ucrInfo.categories.items():
            name = obj['name']
            if ucrInfo.get_variables(id):
                categories.append({
                    'id': id,
                    'label': name,
                })
        self.finished(request.id, categories)

    @sanitize(pattern=PatternSanitizer(default='.*'), key=ChoicesSanitizer(['all', 'key', 'value', 'description'], required=True))
    @simple_response
    def query(self, pattern: str, key: str, category: list[str] | None = None) -> dict:
        """
        Returns a dictionary of configuration registry variables
        found by searching for the (wildcard) expression defined by the
        HTTP request. Additionally a list of configuration registry
        categories can be defined.

        The dictionary returned is compatible with the Dojo data store
        format.
        """
        variables = []
        if category == 'all':
            # load _all_ config registry variables
            base_info = ConfigRegistryInfo(registered_only=False)
        else:
            # load _all registered_ config registry variables
            base_info = ConfigRegistryInfo()

        if category in ('all', 'all-registered'):
            category = None

        def _hidden(name: str, reg: Pattern) -> bool:
            if name in DEPRECATED_GEN:
                return True
            return bool(reg.fullmatch(name))

        def _match_value(name, var):
            return var.value and pattern.match(var.value)

        def _match_key(name, var):
            return pattern.match(name)

        def _match_description(name, var):
            descr = var.get('description')
            return descr and pattern.match(descr)

        def _match_all(name, var):
            return _match_value(name, var) or _match_description(name, var) or _match_key(name, var)

        func = locals().get(f'_match_{key}')
        for name, var in base_info.get_variables(category).items():
            if func(name, var) and not _hidden(name, RE_KEY):
                variables.append({
                    'key': name,
                    'value': var.value,
                    'description': var.get('description', None),
                })

        return variables
