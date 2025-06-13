#!/usr/bin/python3
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2008-2025 Univention GmbH
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
"""Univention Updater: UCR Repository Server URL"""

from __future__ import annotations

from copy import copy
from typing import TYPE_CHECKING, TypeVar, overload
from urllib.parse import quote, urlsplit


if TYPE_CHECKING:
    from univention.config_registry import ConfigRegistry


_T = TypeVar("_T")


class UcsRepoUrl:  # noqa: PLW1641
    """UCS repository server base URL."""

    DEFAULT = 'https://updates.software-univention.de/'

    def __init__(self, ucr: ConfigRegistry, component: str, default: str | UcsRepoUrl | None = None) -> None:
        """
        >>> UcsRepoUrl({'_/server': 'hostname'}, '_').path
        ''
        >>> UcsRepoUrl({'_/server': 'hostname', '_/prefix': '/p'}, '_').path
        '/p/'
        >>> UcsRepoUrl({'_/server': 'hostname', '_/prefix': 'path'}, '_').path
        '/path/'
        >>> UcsRepoUrl({}, '', UcsRepoUrl({'_/server': 'https://hostname/'}, '_')).private()
        'https://hostname/'
        >>> UcsRepoUrl({'_/server': 'other'}, '_', UcsRepoUrl({'_/server': 'https://hostname:80/'}, '_')).private()
        'http://other/'
        >>> UcsRepoUrl({'_/server': 'other'}, '_', UcsRepoUrl.DEFAULT).private()
        'http://other/'
        >>> UcsRepoUrl({}, '').private() == UcsRepoUrl.DEFAULT
        True
        """
        @overload
        def ucrv(key: str, default: _T) -> str | _T:
            ...

        @overload
        def ucrv(key: str) -> str | None:
            ...

        def ucrv(key: str, default: _T | None = None) -> str | _T | None:
            return ucr.get('%s/%s' % (component, key), default)

        server = ucrv('server', '')
        url = urlsplit(server)
        if url.scheme:
            self.scheme = url.scheme
            self.username = url.username
            self.password = url.password
            self.hostname = url.hostname
            port: int | str | None = url.port
            prefix: str | None = url.path
        else:
            if default is None:
                default = self.DEFAULT
            elif isinstance(default, UcsRepoUrl):
                default = default.private()
            defaults = urlsplit(default)

            self.username = ucrv('username', defaults.username)
            self.password = ucrv('password', defaults.password)
            if server:
                self.hostname = server
                port = ucrv('port', 80)
                self.scheme = 'https' if port == 443 else 'http'
                prefix = ucrv('prefix', None)
            else:
                self.hostname = defaults.hostname
                port = ucrv('port', defaults.port)
                self.scheme = defaults.scheme
                prefix = ucrv('prefix', defaults.path)

        self.port = int(port or (443 if self.scheme == 'https' else 80))
        if prefix:
            prefix = prefix.strip('/')
            if prefix:
                self.path = '/%s/' % (prefix,)
            else:
                self.path = '/'
        else:
            self.path = ''

    @property
    def cred(self) -> str:
        if self.username:
            # FIXME: http://bugs.debian.org/500560: [@:/] don't work
            return '%s:%s@' % (quote(self.username), quote(self.password or ''))
        return ''

    @property
    def _port(self) -> str:
        return ':%d' % (self.port) if (self.scheme, self.port) not in (
            ('http', 80),
            ('https', 443),
        ) else ''

    @property
    def _path(self) -> str:
        return quote('/%s' % (self.path.lstrip('/'),))

    def public(self) -> str:
        """
        URI without credentials.

        >>> UcsRepoUrl({'_/server': 'hostname'}, '_').public()
        'http://hostname/'
        >>> UcsRepoUrl({'_/server': 'hostname', '_/username': 'user', '_/password': 'pass'}, '_').public()
        'http://hostname/'
        >>> UcsRepoUrl({'_/server': 'https://hostname'}, '_').public()
        'https://hostname/'
        >>> UcsRepoUrl({'_/server': 'https://user:pass@hostname'}, '_').public()
        'https://hostname/'
        """
        return f'{self.scheme}://{self.hostname}{self._port}{self._path}'

    def private(self) -> str:
        """
        URI with credentials.

        >>> UcsRepoUrl({'_/server': 'hostname'}, '_').private()
        'http://hostname/'
        >>> UcsRepoUrl({'_/server': 'hostname', '_/username': 'user', '_/password': 'pass'}, '_').private()
        'http://user:pass@hostname/'
        >>> UcsRepoUrl({'_/server': 'https://hostname'}, '_').private()
        'https://hostname/'
        >>> UcsRepoUrl({'_/server': 'https://user:pass@hostname'}, '_').private()
        'https://user:pass@hostname/'
        """
        return f'{self.scheme}://{self.cred}{self.hostname}{self._port}{self._path}'

    def __repr__(self) -> str:
        """
        >>> repr(UcsRepoUrl({'_/server': 'hostname'}, '_'))
        "UcsRepoUrl({}, '', 'http://hostname/')"
        """
        return '%s(%r, %r, %r)' % (
            self.__class__.__name__,
            {},
            '',
            self.private(),
        )

    def __eq__(self, other: object) -> bool:
        """
        >>> UcsRepoUrl({}, '') == UcsRepoUrl({}, '')
        True
        >>> UcsRepoUrl({}, '') == UcsRepoUrl({'_/server': 'other'}, '_')
        False
        """
        return isinstance(other, UcsRepoUrl) and self.private() == other.private()

    def __add__(self, rel: str) -> UcsRepoUrl:
        """
        Append relative path component.

        >>> (UcsRepoUrl({'_/server': 'http://hostname'}, '_') + '/b').public()
        'http://hostname/b'
        >>> (UcsRepoUrl({'_/server': 'http://hostname/'}, '_') + '/b').public()
        'http://hostname/b'
        >>> (UcsRepoUrl({'_/server': 'http://hostname/a'}, '_') + '/b').public()
        'http://hostname/a/b'
        >>> (UcsRepoUrl({'_/server': 'http://hostname/a/'}, '_') + '/b').public()
        'http://hostname/a/b'
        >>> (UcsRepoUrl({'_/server': 'http://hostname/a/'}, '_') + '/b/').public()
        'http://hostname/a/b/'
        """
        cfg = copy(self)
        cfg.path = '%s/%s' % (self._path.rstrip('/'), str(rel).lstrip('/'))
        return cfg
