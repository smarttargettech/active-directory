"""Univention Configuration Registry output filters."""
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

from univention.config_registry.misc import escape_value, key_shell_escape


try:
    from collections.abc import Iterable
    from typing import Any
except ImportError:  # pragma: no cover
    pass

__all__ = ['filter_keys_only', 'filter_shell', 'filter_sort']


def filter_shell(args: Any, text: Iterable[str]) -> Iterable[str]:  # pylint: disable-msg=W0613
    """
    Filter output for shell: escape keys.

    :param args: UNUSED.
    :param text: Text as list of lines.
    :returns: Filteres list of lines.
    """
    out = []
    for line in text:
        try:
            var, value = line.split(': ', 1)
        except ValueError:
            var = line
            value = ''
        out.append('%s=%s' % (key_shell_escape(var), escape_value(value)))
    return out


def filter_keys_only(args: Any, text: Iterable[str]) -> Iterable[str]:  # pylint: disable-msg=W0613
    """
    Filter output: strip values.

    :param args: UNUSED.
    :param text: Text as list of lines.
    :returns: Filteres list of lines.
    """
    out = []
    for line in text:
        out.append(line.split(': ', 1)[0])
    return out


def filter_sort(args: Any, text: Iterable[str]) -> Iterable[str]:  # pylint: disable-msg=W0613
    """
    Filter output: sort by key.

    :param args: UNUSED.
    :param text: Text as list of lines.
    :returns: Filteres list of lines.
    """
    return sorted(text)
