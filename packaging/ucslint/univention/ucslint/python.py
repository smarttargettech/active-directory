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

import re
from collections.abc import Iterator
from pathlib import Path
from re import Pattern

from univention.ucslint.base import FilteredDirWalkGenerator


def _or(*disjunct: str, name: str | None = None) -> str:
    return r'(?{}{})'.format(':' if name is None else f'P<{name}>', '|'.join(disjunct))


RE_HASHBANG = re.compile(r"^#!.*[ /]python[0-9.]*\b")
ESCAPE_LENIENT = r"\\."
ESCAPE_RAW = r"\\(?:$|.)"
ESCAPE_BYTES = r"""\\(?:$|[\\'"abfnrtv]|[0-7]{1,3}|x[0-9a-fA-F]{2})"""
ESCAPE_UNIICODE = _or(ESCAPE_BYTES, r"\\(?:N\{[^}]+\}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})")
LITERALS = _or(
    r"'''(?:[^'\\]|%(esc)s|'[^']|''[^'])*?'''",
    r'"""(?:[^"\\]|%(esc)s|"[^"]|""[^"])*?"""',
    r"'(?:[^'\\\n]|%(esc)s)*?'",
    r'"(?:[^"\\\n]|%(esc)s)*?"',
)
MATCHED_LENIENT = rf"(?:\b[BbFfRrUu]{{1,2}})?{(LITERALS % {'esc': ESCAPE_LENIENT})}"
COMMENT = _or(r"#[^\n]*$", name="cmt")
RE_LENIENT = re.compile(_or(COMMENT, _or(MATCHED_LENIENT, name="str")), re.MULTILINE)


class Base:
    VER = (0, 0)
    MATCHED_RAW = r"\b{}{}".format(
        _or("[Rr]", "[BbFfUu][Rr]", "[Rr][BbFf]"),  # (ur|ru) only in 2, (rb) since 3.3
        LITERALS % {"esc": ESCAPE_RAW},
    )
    MATCHED_BYTES = rf"\b[Bb]{(LITERALS % {'esc': ESCAPE_BYTES})}"
    MATCHED_UNICODE = rf"(?:\b[FfUu])?{(LITERALS % {'esc': ESCAPE_UNIICODE})}"  # [u] not in 3.0-3.2, [f] since 3.6

    @classmethod
    def matcher(cls) -> Pattern[str]:
        MATCHED_STRING = _or(
            cls.MATCHED_RAW, cls.MATCHED_BYTES, cls.MATCHED_UNICODE, name="str",
        )
        RE_STRING = re.compile(_or(COMMENT, MATCHED_STRING), re.MULTILINE)
        return RE_STRING


class Python27(Base):
    VER = (2, 7)
    MATCHED_RAW = r"\b{}{}".format(
        _or("[Rr]", "[BbUu][Rr]", "[Rr][Uu]"),  # (ur|ru) only in 2, (rb) since 3.3
        LITERALS % {"esc": ESCAPE_RAW},
    )


class Python30(Base):
    VER = (3, 0)
    MATCHED_RAW = r"\b{}{}".format(_or("[Rr]", "[Bb][Rr]"), LITERALS % {"esc": ESCAPE_RAW})
    MATCHED_UNICODE = LITERALS % {"esc": ESCAPE_UNIICODE}  # [u] not in 3.0-3.2


class Python33(Base):
    VER = (3, 3)
    MATCHED_RAW = r"\b{}{}".format(
        _or("[Rr]", "[Bb][Rr]", "[Rr][Bb]"),  # 2, (rb) since 3.3
        LITERALS % {"esc": ESCAPE_RAW},
    )
    MATCHED_UNICODE = rf"(?:\b[Uu])?{(LITERALS % {'esc': ESCAPE_UNIICODE})}"


class Python36(Base):
    VER = (3, 6)
    MATCHED_RAW = r"\b{}{}".format(
        _or("[Rr]", "[BbFf][Rr]", "[Rr][BbFf]"),  # (f) since 3.6
        LITERALS % {"esc": ESCAPE_RAW},
    )
    MATCHED_UNICODE = rf"(?:\b[FfUu])?{(LITERALS % {'esc': ESCAPE_UNIICODE})}"  # [f] since 3.6


def python_files(path: Path) -> Iterator[Path]:
    SUFFIXES = ('.py',)

    yield from FilteredDirWalkGenerator(path, suffixes=SUFFIXES, reHashBang=RE_HASHBANG)
