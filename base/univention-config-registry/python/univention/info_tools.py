#
# Univention Configuration Registry
#  dictionary class for localized keys
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2007-2025 Univention GmbH
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

import configparser
import re
from typing import TypeVar, overload


_VT = TypeVar('_VT')

# default locale
_locale = 'de'
MYPY = False


if MYPY:  # pragma: no cover
    __LVD = dict[str, str]
else:
    __LVD = dict


class LocalizedValue(__LVD):
    """Localized description entry."""

    def __init__(self, *args, **kwargs):
        tmp = dict(*args, **kwargs)
        self.__default = tmp.pop('__default', '')
        dict.__init__(self, tmp)

    def __repr__(self):
        return '%s(%s, __default=%r)' % (
            self.__class__.__name__,
            dict.__repr__(self),
            self.__default,
        )

    def get(self, locale: str | None = None) -> str:  # type: ignore
        if not locale:
            locale = _locale
        if locale in self:
            return self[locale]
        return self.__default

    def set(self, value: str, locale: str | None = None) -> None:
        self[locale or _locale] = value

    def set_default(self, default: str) -> None:
        self.__default = default

    def get_default(self) -> str:
        return self.__default


if MYPY:  # pragma: no cover
    __LD = dict[str, str]
else:
    __LD = dict


class LocalizedDictionary(__LD):  # noqa: PLW1641
    """Localized descriptions."""

    _LOCALE_REGEX = re.compile(r'(?P<key>[a-zA-Z]*)\[(?P<lang>[a-z]*)\]$')

    def __init__(self) -> None:
        dict.__init__(self)

    def __setitem__(self, key: str, value: str) -> None:
        key = key.lower()
        matches = LocalizedDictionary._LOCALE_REGEX.match(key)
        # localized value?
        if matches:
            key, lang = matches.groups()

        val = self.setdefault(key, LocalizedValue())  # type: ignore
        if matches:
            val.set(value, lang)  # type: ignore
        else:
            val.set_default(value)  # type: ignore

    def __getitem__(self, key: str) -> str:
        key = key.lower()
        lang: str | None = None
        matches = LocalizedDictionary._LOCALE_REGEX.match(key)
        # localized value?
        if matches:
            key, lang = matches.groups()

        return dict.__getitem__(self, key).get(lang)  # type: ignore

    @overload
    def get(self, key: str) -> str | None:  # pragma: no cover
        pass

    @overload
    def get(self, key: str, default: _VT) -> str | _VT:  # pragma: no cover
        pass

    def get(self, key: str, default: _VT | None = None) -> str | _VT:
        try:
            value = self.__getitem__(key) or default
            return value  # type: ignore
        except KeyError:
            return default  # type: ignore

    def __contains__(self, key: str) -> bool:  # type: ignore
        key = key.lower()
        matches = LocalizedDictionary._LOCALE_REGEX.match(key)
        if matches:
            key = matches.group(1)
        return dict.__contains__(self, key)  # type: ignore[operator]
    has_key = __contains__  # type: ignore

    def __normalize_key(self, key: str) -> dict[str, str]:
        if key not in self:
            return {}

        temp = {}
        variable: LocalizedValue = dict.__getitem__(self, key)  # type: ignore
        for locale, value in variable.items():
            temp['%s[%s]' % (key, locale)] = value

        if variable.get_default():  # type: ignore
            temp[key] = variable.get_default()

        return temp

    def normalize(self, key: str | None = None) -> dict[str, str]:
        if key:
            return self.__normalize_key(key)
        temp: dict[str, str] = {}
        for key2 in self.keys():
            temp.update(self.__normalize_key(key2))
        return temp

    def get_dict(self, key: str) -> dict[str, str]:
        if key not in self:
            return {}
        return dict.__getitem__(self, key)  # type: ignore

    def __eq__(self, other):
        if not isinstance(other, dict):
            return False
        me = self.normalize()
        you = other.normalize()
        return dict.__eq__(me, you)

    def __ne__(self, other):
        return not self.__eq__(other)


# my config parser
class UnicodeConfig(configparser.ConfigParser):

    def __init__(self):
        configparser.ConfigParser.__init__(self, strict=False, interpolation=None)

    def read(self, filename, encoding='UTF-8'):
        return configparser.ConfigParser.read(self, filename, encoding=encoding)

    def write(self, fp):
        """Write an .ini-format representation of the configuration state."""
        if self._defaults:
            fp.write("[%s]\n" % configparser.DEFAULTSECT)
            for (key, value) in self._defaults.items():
                fp.write("%s = %s\n" % (key, str(value).replace('\n', '\n\t')))
            fp.write("\n")
        for section in self._sections:
            fp.write("[%s]\n" % section)
            for (key, value) in self._sections[section].items():
                if key != "__name__":
                    fp.write("%s = %s\n" % (key, value.replace('\n', '\n\t')))
            fp.write("\n")


def set_language(lang):
    global _locale
    _locale = lang
