# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2013-2025 Univention GmbH
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

"""Internal functions for test finding and setup."""

from __future__ import annotations

import logging
import operator
import os
import re
import sys
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable, Iterable


__all__ = [
    'LOG_BASE',
    'TEST_BASE',
    'UCSVersion',
    'get_sections',
    'get_tests',
    'setup_debug',
    'setup_environment',
    'strip_indent',
]

TEST_BASE = os.environ.get('UCS_TESTS', '/usr/share/ucs-test')
RE_SECTION = re.compile(r'^[0-9]{2}_(.+)$')
RE_PREFIX = re.compile(r'^[0-9]{2,3}_?(.+)')
RE_SUFFIX = re.compile(r'(?:~|\.(?:lib|sh|py[co]|bak|mo|po|png|jpg|jpeg|xml|csv|inst|uinst))$')
LOG_BASE = '/var/log/univention/test_%d.log'
S4CONNECTOR_INIT_SCRIPT = '/etc/init.d/univention-s4-connector'
INF = sys.maxsize


def setup_environment() -> None:
    """Setup runtime environment."""
    os.environ['TESTLIBPATH'] = '/usr/share/ucs-test/lib'
    os.environ['PYTHONUNBUFFERED'] = '1'


def setup_debug(level: int) -> None:
    """Setup Python logging."""
    level = _TAB.get(level, logging.DEBUG)
    FORMAT = '%(asctime)-15s ' + logging.BASIC_FORMAT
    logging.basicConfig(stream=sys.stderr, level=level, format=FORMAT)


_TAB = {  # pylint: disable-msg=W0612
    None: logging.WARNING,
    0: logging.WARNING,
    1: logging.INFO,
    2: logging.DEBUG,
}


def strip_indent(text: str) -> str:
    """Strip common indent."""
    lines = text.splitlines()
    while lines and not lines[0].strip():
        del lines[0]
    while lines and not lines[-1].strip():
        del lines[-1]
    indent = min(len(line) - len(line.lstrip()) for line in lines if line.lstrip())
    return '\n'.join(line[indent:] for line in lines)


def get_sections() -> dict[str, str]:
    """Return dictionary section-name -> section-directory."""
    section_dirs = os.listdir(TEST_BASE)
    sections = {dirname[3:]: TEST_BASE + os.path.sep + dirname for dirname in section_dirs if RE_SECTION.match(dirname)}
    return sections


def get_tests(sections: Iterable[str]) -> dict[str, list[str]]:
    """Return dictionary of section -> [filenames]."""
    result = {}
    logger = logging.getLogger('test.find')

    all_sections = get_sections()

    for section in sections:
        dirname = all_sections[section]
        logger.debug(f'Processing directory {dirname}')
        tests = []

        files = os.listdir(dirname)
        for filename in sorted(files):
            fname = os.path.join(dirname, filename)
            if not RE_PREFIX.match(filename):
                logger.debug(f'Skipped file {fname}')
                continue
            if RE_SUFFIX.search(filename):
                logger.debug(f'Skipped file {fname}')
                continue
            if not os.path.exists(fname):
                logger.debug(f'Skipped file {fname}')
                continue
            logger.debug(f'Adding file {fname}')
            tests.append(fname)

        if tests:
            result[section] = tests
    return result


class UCSVersion:  # pylint: disable-msg=R0903  # noqa: PLW1641
    """
    UCS version.

    >>> UCSVersion("1.0") < UCSVersion("2.0")
    True
    >>> UCSVersion("1.0") < UCSVersion("1.0")
    False
    >>> UCSVersion("1.0") <= UCSVersion("1.0")
    True
    >>> UCSVersion("2.0") <= UCSVersion("1.0")
    False
    >>> UCSVersion("1.0") == UCSVersion("1.0")
    True
    >>> UCSVersion("1.0") == UCSVersion("2.0")
    False
    >>> UCSVersion("1.0") != UCSVersion("2.0")
    True
    >>> UCSVersion("1.0") != UCSVersion("1.0")
    False
    >>> UCSVersion("1.0") >= UCSVersion("1.0")
    True
    >>> UCSVersion("1.0") >= UCSVersion("2.0")
    False
    >>> UCSVersion("2.0") > UCSVersion("1.0")
    True
    >>> UCSVersion("1.0") > UCSVersion("1.0")
    False
    >>> UCSVersion("1.0") == UCSVersion((1, 0, INF, INF))
    True
    >>> UCSVersion("1.0-0-0") == UCSVersion((1, 0, 0, 0))
    True
    >>> UCSVersion("")
    Traceback (most recent call last):
            ...
    ValueError: Version does not match: ""
    >>> UCSVersion("0")
    Traceback (most recent call last):
            ...
    ValueError: Version does not match: "0"
    >>> UCSVersion("1")
    Traceback (most recent call last):
            ...
    ValueError: Version does not match: "1"
    >>> UCSVersion("1.2")
    UCSVersion('=1.2')
    >>> UCSVersion("1.2-3")
    UCSVersion('=1.2-3')
    >>> UCSVersion("1.2-3-4")
    UCSVersion('=1.2-3-4')
    >>> UCSVersion("1.2-3-4-5")
    Traceback (most recent call last):
            ...
    ValueError: Version does not match: "1.2-3-4-5"
    >>> UCSVersion(None)
    Traceback (most recent call last):
            ...
    TypeError: None
    >>> UCSVersion(1)
    Traceback (most recent call last):
            ...
    TypeError: 1
    >>> UCSVersion(1.5)
    Traceback (most recent call last):
            ...
    TypeError: 1.5
    """

    RE_VERSION = re.compile(r"^(<|<<|<=|=|==|>=|>|>>)?([1-9][0-9]*)\.([0-9]+)(?:-([0-9]*)(?:-([0-9]+))?)?$")

    @classmethod
    def _parse(cls, ver: str, default_op: str = '=') -> tuple[Callable[[Any, Any], Any], tuple[int, int, int, int]]:
        """
        Parse UCS-version range and return two-tuple (operator, version)
        >>> UCSVersion._parse('11.22')  # doctest: +ELLIPSIS
        (<built-in function eq>, (11, 22, ..., ...))
        >>> UCSVersion._parse('11.22-33')  # doctest: +ELLIPSIS
        (<built-in function eq>, (11, 22, 33, ...))
        >>> UCSVersion._parse('11.22-33-44')
        (<built-in function eq>, (11, 22, 33, 44))
        >>> UCSVersion._parse('<1.2-3')  # doctest: +ELLIPSIS
        (<built-in function lt>, (1, 2, 3, ...))
        >>> UCSVersion._parse('<<1.2-3')  # doctest: +ELLIPSIS
        (<built-in function lt>, (1, 2, 3, ...))
        >>> UCSVersion._parse('<=1.2-3')  # doctest: +ELLIPSIS
        (<built-in function le>, (1, 2, 3, ...))
        >>> UCSVersion._parse('=1.2-3')  # doctest: +ELLIPSIS
        (<built-in function eq>, (1, 2, 3, ...))
        >>> UCSVersion._parse('==1.2-3')  # doctest: +ELLIPSIS
        (<built-in function eq>, (1, 2, 3, ...))
        >>> UCSVersion._parse('>=1.2-3')  # doctest: +ELLIPSIS
        (<built-in function ge>, (1, 2, 3, ...))
        >>> UCSVersion._parse('>>1.2-3')  # doctest: +ELLIPSIS
        (<built-in function gt>, (1, 2, 3, ...))
        >>> UCSVersion._parse('>1.2-3')  # doctest: +ELLIPSIS
        (<built-in function gt>, (1, 2, 3, ...))
        """
        match = cls.RE_VERSION.match(ver)
        if not match:
            raise ValueError(f'Version does not match: "{ver}"')
        rel = match.group(1) or default_op
        parts: tuple[int, int, int, int] = tuple(int(_) if _ else INF for _ in match.groups()[1:])  # type: ignore
        if rel in ('<', '<<'):
            return (operator.lt, parts)
        if rel in ('<=',):
            return (operator.le, parts)
        if rel in ('=', '=='):
            return (operator.eq, parts)
        if rel in ('>=',):
            return (operator.ge, parts)
        if rel in ('>', '>>'):
            return (operator.gt, parts)
        raise ValueError(f'Unknown version match: "{ver}"')

    def __init__(self, ver: str | tuple[int, int, int, int]) -> None:
        if isinstance(ver, str):
            self.rel, self.ver = self._parse(ver)
        elif isinstance(ver, tuple):
            self.rel = operator.eq
            assert all(isinstance(_, int) for _ in ver)
            self.ver = ver
        else:
            raise TypeError(ver)

    def __str__(self) -> str:
        rel = {
            operator.lt: '<',
            operator.le: '<=',
            operator.eq: '=',
            operator.ge: '>=',
            operator.gt: '>',
        }[self.rel]
        ver = '%d.%d' % self.ver[0:2]  # type: ignore
        skipped = 0
        for part in self.ver[2:]:
            skipped += 1
            if part != INF:
                ver += '%s%d' % ('-' * skipped, part)
                skipped = 0
        return f'{rel}{ver}'

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}({self.__str__()!r})'

    def __lt__(self, other: object) -> object:
        return self.ver < other.ver if isinstance(other, UCSVersion) else NotImplemented

    def __le__(self, other: object) -> object:
        return self.ver <= other.ver if isinstance(other, UCSVersion) else NotImplemented

    def __eq__(self, other: object) -> bool:
        return self.ver == other.ver if isinstance(other, UCSVersion) else False

    def __ne__(self, other: object) -> bool:
        return self.ver != other.ver if isinstance(other, UCSVersion) else False

    def __ge__(self, other: object) -> object:
        return self.ver >= other.ver if isinstance(other, UCSVersion) else NotImplemented

    def __gt__(self, other: object) -> object:
        return self.ver > other.ver if isinstance(other, UCSVersion) else NotImplemented

    def match(self, other: UCSVersion) -> bool:
        """
        Check if other matches the criterion.
        >>> UCSVersion('>1.2-3').match(UCSVersion('1.2-4'))
        True
        >>> UCSVersion('>1.2-3').match(UCSVersion('1.2-3-4'))
        False
        >>> UCSVersion('>1.2-3-5').match(UCSVersion('1.2-3-4'))
        False
        >>> UCSVersion('>=1.2-3').match(UCSVersion('1.2-3-4'))
        True
        """
        parts = [
            (other_ver, self_ver)
            for self_ver, other_ver in zip(self.ver, other.ver)
            if INF not in (self_ver, other_ver)
        ]
        return self.rel(*zip(*parts))  # pylint: disable-msg=W0142


if __name__ == '__main__':
    import doctest
    doctest.testmod()
