#!/usr/bin/python3
#
# Copyright 2024-2025 Univention GmbH
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
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
import sys
from collections.abc import Callable, Iterator
from datetime import datetime
from logging import DEBUG

import pytest

import univention.debug2 as ud


RE = re.compile(
    r'''
    (?P<datetime>[0-3]\d\.[01]\d\.\d{4}\s[0-2]\d:[0-5]\d:[0-5]\d)\.(?P<msec>\d{3})\s(?P<category>\S+)\s+\((?P<level>\S+)\s*\):\s(?P<text>
      (?:UNIVENTION_DEBUG_BEGIN\s:\s(?P<begin>.*)
        |UNIVENTION_DEBUG_END\s{3}:\s(?P<end>.*)
        |(?P<msg>.*)
    ))$
    ''', re.VERBOSE)
LEVEL = ['ERROR', 'WARNING', 'PROCESS', 'INFO', 'ALL']
CATEGORY = [
    'MAIN',
    'LDAP',
    'USERS',
    'NETWORK',
    'SSL',
    'SLAPD',
    'SEARCH',
    'TRANSFILE',
    'LISTENER',
    'POLICY',
    'ADMIN',
    'CONFIG',
    'LICENSE',
    'KERBEROS',
    'DHCP',
    'PROTOCOL',
    'MODULE',
    'ACL',
    'RESOURCES',
    'PARSER',
    'LOCALE',
    'AUTH',
]


@pytest.fixture
def parse() -> Iterator[Callable[[str], Iterator[tuple[str, dict[str, str]]]]]:
    """Setup parser."""
    now = datetime.now()
    start = now.replace(microsecond=now.microsecond - now.microsecond % 1000)

    def f(text: str) -> Iterator[tuple[str, dict[str, str]]]:
        """
        Parse line into componets.

        :param text: Multi-line text.
        :returns: 2-tuple (typ, data) where `data` is a mapping from regular-expression-group-name to value.
        """
        end = datetime.now()

        for line in text.splitlines():
            print(repr(line))
            match = RE.match(line)
            assert match, line
            groups = match.groupdict()

            stamp = groups.get('datetime')
            if stamp is not None:
                assert start <= datetime.strptime(stamp, '%d.%m.%Y %H:%M:%S').replace(microsecond=int(groups['msec']) * 1000) <= end

            if groups.get('begin') is not None:
                yield ('begin', groups)
            elif groups.get('end') is not None:
                yield ('end', groups)
            elif groups.get('msg') == 'DEBUG_INIT':
                yield ('init', groups)
            elif groups.get('msg') == 'DEBUG_REINIT':
                yield ('reinit', groups)
            elif groups.get('msg') == 'DEBUG_EXIT':
                yield ('exit', groups)
            elif groups.get('text') is not None:
                yield ('msg', groups)
            else:
                raise AssertionError(groups)

    return f


@pytest.fixture
def tmplog(tmpdir):
    """Setup temporary logging."""
    tmp = tmpdir.ensure('log')
    fd = ud.init(str(tmp), ud.NO_FLUSH, ud.FUNCTION)
    assert hasattr(fd, 'write')

    return tmp


@pytest.mark.parametrize('stream,idx', [('stdout', 0), ('stderr', 1)])
def test_stdio(stream, idx, capfd, parse):
    fd = ud.init(stream, ud.NO_FLUSH, ud.FUNCTION)
    assert hasattr(fd, 'write')
    ud.exit()

    output = capfd.readouterr()
    assert [typ for typ, groups in parse(output[idx])] == ['init', 'exit']


def test_file(parse, tmplog):
    ud.exit()

    output = tmplog.read()
    assert [typ for typ, groups in parse(output)] == ['init', 'exit']


@pytest.mark.parametrize('function,expected', [(ud.FUNCTION, ['init', 'begin', 'end', 'exit']), (ud.NO_FUNCTION, ['init', 'exit'])])
def test_function(function, expected, parse, tmplog):
    def f():
        _d = ud.function('f')
        _d  # noqa: B018

    ud.set_function(function)
    f()
    ud.exit()

    output = tmplog.read()
    assert [typ for typ, groups in parse(output)] == expected


def test_level_set(tmplog):
    ud.set_level(ud.MAIN, ud.PROCESS)
    level = ud.get_level(ud.MAIN)
    assert level == ud.PROCESS

    ud.exit()


def test_debug_closed():
    ud.debug(ud.MAIN, ud.ALL, "No crash")
    assert True


@pytest.mark.parametrize('name', LEVEL)
def test_level(name, parse, tmplog, caplog):
    caplog.set_level(DEBUG)
    level = getattr(ud, 'WARN' if name == 'WARNING' else name)
    ud.set_level(ud.MAIN, level)
    assert level == ud.get_level(ud.MAIN)

    ud.debug(ud.MAIN, ud.ERROR, "Error in main: %%%")
    ud.debug(ud.MAIN, ud.WARN, "Warning in main: %%%")
    ud.debug(ud.MAIN, ud.PROCESS, "Process in main: %%%")
    ud.debug(ud.MAIN, ud.INFO, "Information in main: %%%")
    ud.debug(ud.MAIN, ud.ALL, "All in main: %%%")
    ud.exit()

    output = tmplog.read()
    assert [groups['level'] for typ, groups in parse(output) if typ == 'msg'] == LEVEL[:1 + LEVEL.index(name)]


@pytest.mark.parametrize('name', CATEGORY)
def test_category(name, parse, tmplog):
    category = getattr(ud, name)
    ud.debug(category, ud.ERROR, "Error in main: %%%")
    ud.debug(category, ud.WARN, "Warning in main: %%%")
    ud.debug(category, ud.PROCESS, "Process in main: %%%")
    ud.debug(category, ud.INFO, "Information in main: %%%")
    ud.debug(category, ud.ALL, "All in main: %%%")
    ud.exit()

    output = tmplog.read()
    assert {groups['category'] for typ, groups in parse(output) if typ == 'msg'} == {name}


def test_reopen(parse, tmplog):
    ud.debug(ud.MAIN, ud.ERROR, '1st')
    tmpbak = tmplog.dirpath('bak')
    tmplog.rename(tmpbak)
    ud.reopen()
    ud.debug(ud.MAIN, ud.ERROR, '2nd')
    ud.exit()

    output = tmpbak.read()
    assert [groups['msg'] for typ, groups in parse(output) if typ == 'msg'] == ['1st']

    output = tmplog.read()
    assert [groups['msg'] for typ, groups in parse(output) if typ == 'msg'] == ['2nd']


def test_unicode(parse, tmplog):
    ud.debug(ud.MAIN, ud.ERROR, '\u2603')
    ud.exit()

    output = tmplog.read()
    for ((c_type, c_groups), (e_type, e_groups)) in zip(parse(output), [
            ('init', {}),
            ('msg', {'msg': '\xe2\x98\x83' if sys.version_info.major < 3 else '\u2603'}),
            ('exit', {}),
    ]):
        assert c_type == e_type
        for key, val in e_groups.items():
            assert c_groups[key] == val


def test_trace_plain(parse, tmplog):
    @ud.trace(with_args=False)
    def f():
        pass

    ud.set_function(ud.FUNCTION)
    assert f() is None
    ud.exit()

    output = tmplog.read()
    for ((c_type, c_groups), (e_type, e_groups)) in zip(parse(output), [
            ('init', {}),
            ('begin', {'begin': 'test_debug2.f(...): ...'}),
            ('end', {'end': 'test_debug2.f(...): ...'}),
            ('exit', {}),
    ]):
        assert c_type == e_type
        for key, val in e_groups.items():
            assert c_groups[key] == val


def test_trace_detail(parse, tmplog):
    @ud.trace(with_args=True, with_return=True, repr=repr)
    def f(args):
        return 42

    ud.set_function(ud.FUNCTION)
    assert f('in') == 42
    ud.exit()

    output = tmplog.read()
    for ((c_type, c_groups), (e_type, e_groups)) in zip(parse(output), [
            ('init', {}),
            ('begin', {'begin': "test_debug2.f('in'): ..."}),
            ('end', {'end': 'test_debug2.f(...): 42'}),
            ('exit', {}),
    ]):
        assert c_type == e_type
        for key, val in e_groups.items():
            assert c_groups[key] == val


def test_trace_exception(parse, tmplog):
    @ud.trace(with_args=False)
    def f():
        raise ValueError(42)

    ud.set_function(ud.FUNCTION)
    with pytest.raises(ValueError):
        f()
    ud.exit()

    output = tmplog.read()
    for ((c_type, c_groups), (e_type, e_groups)) in zip(parse(output), [
            ('init', {}),
            ('begin', {'begin': 'test_debug2.f(...): ...'}),
            ('end', {'end': "test_debug2.f(...): %r(42)" % ValueError}),
            ('exit', {}),
    ]):
        assert c_type == e_type
        for key, val in e_groups.items():
            assert c_groups[key] == val
