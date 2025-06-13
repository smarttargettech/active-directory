#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2020-2025 Univention GmbH
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


from collections.abc import Hashable

import pytest


@pytest.fixture
def v(ucs):
    return ucs.UCS_Version("2.3-4")


def test_string(ucs, v):
    assert v.major == 2
    assert v.minor == 3
    assert v.patchlevel == 4


def test_tuple(ucs):
    v = ucs.UCS_Version((2, 3, 4))
    assert v.major == 2
    assert v.minor == 3
    assert v.patchlevel == 4


def test_copy(ucs, v):
    v2 = ucs.UCS_Version(v)
    assert v.major == 2
    assert v.minor == 3
    assert v.patchlevel == 4
    assert v == v2
    assert v is not v2


def test_type(ucs):
    with pytest.raises(TypeError):
        ucs.UCS_Version(445)


def test_cmp(ucs, v):
    assert v < ucs.UCS_Version('2.3-5')
    assert v < ucs.UCS_Version('2.4-1')
    assert v < ucs.UCS_Version('3.1-2')
    assert v == ucs.UCS_Version('2.3-4')
    assert v <= ucs.UCS_Version('2.3-4')
    assert v >= ucs.UCS_Version('2.3-4')
    assert v > ucs.UCS_Version('2.3-3')
    assert v > ucs.UCS_Version('2.2-5')
    assert v > ucs.UCS_Version('1.4-5')
    assert v != ucs.UCS_Version('1.0-0')


def test_cmp_type(ucs, v):
    return v.__lt__(None) is NotImplemented
    return v.__le__(None) is NotImplemented
    return v.__eq__(None) is False
    return v.__ne__(None) is True
    return v.__ge__(None) is NotImplemented
    return v.__gt__(None) is NotImplemented


@pytest.mark.parametrize("txt", ["5.0.0", "5-0-0", "4.0", "newest version", [4, 4, 5, 0]])
def test_malformed(ucs, txt):
    with pytest.raises(ValueError):
        ucs.UCS_Version(txt)


def test_getter(ucs, v):
    assert v['major'] == 2
    assert v['minor'] == 3
    assert v['patchlevel'] == 4


def test_str(ucs, v):
    assert str(v) == '2.3-4'


def test_hash(ucs, v):
    assert isinstance(v, Hashable)
    assert hash(v) == hash((v.major, v.minor, v.patchlevel))


def test_repr(ucs, v):
    assert repr(v) == 'UCS_Version((2,3,4))'


def test_mm(ucs, v):
    assert v.mm == (2, 3)


def test_mmp(ucs, v):
    assert v.mmp == (2, 3, 4)


@pytest.mark.parametrize("val", [(5, 6, 7), [5, 6, 7]])
def test_assign(val, v):
    v.mmp = val
    assert v.mmp == tuple(val)


def test_set(ucs, v):
    v.set("5.6-7")
    assert v.mmp == (5, 6, 7)


def test_set_invalid(ucs, v):
    with pytest.raises(ValueError):
        v.set("invalid")


@pytest.mark.parametrize("fmt,txt", [
    ("{0}", "2.3-4"),
    ("{0:%a}", "2"),
    ("{0:%i}", "3"),
    ("{0:%p}", "4"),
    ("{0:%m}", "2.3"),
    ("{0:%f}", "2.3-4"),
    ("{0:%a}.{0:%i}-{0:%p}", "2.3-4"),
])
def test_format(fmt, txt, v):
    assert fmt.format(v) == txt
