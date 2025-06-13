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
"""Univention Update tools."""

from __future__ import annotations

import base64
import copy
import errno
import functools
import json
import logging
import os
import re
import socket
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from http import client as httplib
from tempfile import TemporaryDirectory
from typing import TYPE_CHECKING, Any, Literal

from univention.config_registry import ConfigRegistry
from univention.lib.ucs import UCS_Version


try:
    import univention.debug as ud
except ImportError:
    import univention.debug2 as ud  # type: ignore

from .commands import cmd_dist_upgrade, cmd_dist_upgrade_sim, cmd_update
from .errors import (
    CannotResolveComponentServerError, ConfigurationError, DownloadError, PreconditionError, ProxyError,
    RequiredComponentError, UnmetDependencyError, VerificationError,
)
from .repo_url import UcsRepoUrl


if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator
    from typing import Self  # type: ignore[attr-defined]


RE_ALLOWED_DEBIAN_PKGNAMES = re.compile('^[a-z0-9][a-z0-9.+-]+$')
RE_SPLIT_MULTI = re.compile('[ ,]+')
RE_COMPONENT = re.compile(r'^repository/online/component/([^/]+)$')
RE_CREDENTIALS = re.compile(r'^repository/credentials/(?:(?P<realm>[^/]+)/)?(?P<key>[^/]+)$')

MIN_GZIP = 100  # size of non-empty gzip file
UUID_NULL = '00000000-0000-0000-0000-000000000000'


def verify_script(script: bytes, signature: bytes) -> bytes | None:
    """
    Verify detached signature of script:

    .. code-block: sh

        gpg -a -u 6B6E7E3259A9F44F1452D1BE36602BA86B8BFD3C --passphrase-file /etc/archive-keys/ucs4.0.txt -o script.sh.gpg -b script.sh
        repo-ng-sign-release-file --debug -k 6B6E7E3259A9F44F1452D1BE36602BA86B8BFD3C -p /etc/archive-keys/ucs4.0.txt  -i script.sh -o script.sh.gpg

    .. code-block: python

        verify_script(open("script.sh", "r").read(), open("script.sh.gpg", "r").read())

    :param str script: The script text to verify.
    :param str signature: The detached signature.
    :return: None or the error output.
    :rtype: None or str
    """
    # write signature to temporary file
    sig_fd, sig_name = tempfile.mkstemp()
    os.write(sig_fd, signature)
    os.close(sig_fd)

    # verify script
    cmd = ["apt-key", "verify", sig_name, "-"]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, close_fds=True)
    stdout, _stderr = proc.communicate(script)
    ret = proc.wait()
    return stdout if ret != 0 else None


class _UCSRepo(UCS_Version):  # noqa: PLW1641
    """Super class to build URLs for APT repositories."""

    ARCHS = {'all', 'amd64'}

    def __init__(self, release: UCS_Version | None = None, **kwargs: Any) -> None:
        if release:
            super().__init__(release)
        for (k, v) in kwargs.items():
            if isinstance(v, str) and '%(' in v:
                self.__dict__[k] = _UCSRepo._substitution(v, self.__dict__)
            else:
                self.__dict__[k] = v

    def __repr__(self) -> str:
        return '%s(**%r)' % (self.__class__.__name__, self.__dict__)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _UCSRepo) and self.path() == other.path()

    def __ne__(self, other: object) -> bool:
        return not isinstance(other, _UCSRepo) or self.path() != other.path()

    def _format(self, format: str) -> str:
        """Format longest path for directory/file access."""
        while True:
            try:
                return format % self
            except KeyError as ex:
                (k,) = ex.args
                # strip missing part
                i = format.index('%%(%s)' % k)
                format = format[:i]
                # strip partial part
                try:
                    i = format.rindex('/') + 1
                except ValueError:
                    i = 0
                format = format[:i]

    class _substitution:
        """
        Helper to print dynamically substituted variable.

        >>> h={'major':2}
        >>> h['version'] = _UCSRepo._substitution('%(major)d.%(minor)d', h)
        >>> h['minor'] = 3
        >>> '%(version)s' % h
        '2.3'
        """

        def __init__(self, format: str, values: Any) -> None:
            self.format = format
            self.values = values

        def __str__(self) -> str:
            try:
                return self.format % self.values
            except KeyError as e:
                for (k, v) in self.values.items():
                    if self == v:
                        raise KeyError(k)
                raise e

        def __repr__(self) -> str:
            return repr(self.format)

    def deb(self, server: _UCSServer, type: str = "deb") -> str:
        """
        Format for :file:`/etc/apt/sources.list`.

        :param str server: The URL of the repository server.
        :param str type: The repository type, e.g. `deb` for a binary and `deb-src` for source package repository.
        :returns: The APT repository stanza.
        :rtype: str
        """
        raise NotImplementedError()

    def path(self, filename: str | None = None) -> str:
        """
        Format pool for directory/file access.

        :param filename: The name of a file in the repository.
        :returns: relative path.
        :rtype: str
        """
        raise NotImplementedError()

    def clean(self, server: _UCSServer) -> str:
        """
        Format for :file:`/etc/apt/mirror.list`

        :param str server: The URL of the repository server.
        :returns: The APT repository stanza.
        :rtype: str
        """
        raise NotImplementedError()


class UCSRepoPool5(_UCSRepo):
    """APT repository using the debian pool structure (ucs5 and above)."""

    def __init__(self, release: UCS_Version = None, **kwargs: Any) -> None:
        kwargs.setdefault('version', UCS_Version.FORMAT)
        kwargs.setdefault('patch', UCS_Version.FULLFORMAT)
        kwargs.setdefault('errata', False)
        super().__init__(release, **kwargs)

    @property
    def _suite(self) -> str:
        """
        Format suite.

        :returns: UCS suite name.
        :rtype: str

        >>> UCSRepoPool5(major=5, minor=1, patchlevel=0)._suite
        'ucs510'
        >>> UCSRepoPool5(major=5, minor=1, patchlevel=0, errata=True)._suite
        'errata510'
        """
        return "{1}{0.major}{0.minor}{0.patchlevel}".format(self, "errata" if self.errata else "ucs")

    def deb(self, server: _UCSServer, type: str = "deb", mirror: bool = False) -> str:
        """
        Format for :file:`/etc/apt/sources.list`.

        :param str server: The URL of the repository server.
        :param str type: The repository type, e.g. `deb` for a binary and `deb-src` for source package repository.
        :param bool mirror: Also mirror files for Debian installer.
        :returns: The APT repository stanza.
        :rtype: str

        >>> r=UCSRepoPool5(major=5, minor=1, patchlevel=0)
        >>> r.deb('https://updates.software-univention.de/')
        'deb https://updates.software-univention.de/ ucs510 main'
        >>> r.deb('https://updates.software-univention.de/', mirror=True)
        'deb https://updates.software-univention.de/ ucs510 main main/debian-installer'
        >>> r=UCSRepoPool5(major=5, minor=1, patchlevel=0, errata=True)
        >>> r.deb('https://updates.software-univention.de/')
        'deb https://updates.software-univention.de/ errata510 main'
        """
        components = "main main/debian-installer" if mirror and not self.errata and type == "deb" else "main"
        return "%s %s %s %s" % (type, server, self._suite, components)

    def path(self, filename: str | None = None) -> str:
        """
        Format pool for directory/file access.

        :param filename: The name of a file in the repository.
        :returns: relative path.
        :rtype: str

        >>> UCSRepoPool5(major=5, minor=1, patchlevel=0).path()
        'dists/ucs510/InRelease'
        >>> UCSRepoPool5(major=5, minor=1, patchlevel=0, errata=True).path()
        'dists/errata510/InRelease'
        """
        return "dists/{}/{}".format(self._suite, filename or 'InRelease')


class UCSRepoPool(_UCSRepo):
    """Flat Debian APT repository."""

    def __init__(self, **kw: Any) -> None:
        kw.setdefault('version', UCS_Version.FORMAT)
        kw.setdefault('patch', UCS_Version.FULLFORMAT)
        super().__init__(**kw)

    def deb(self, server: _UCSServer, type: str = "deb") -> str:
        """
        Format for :file:`/etc/apt/sources.list`.

        :param str server: The URL of the repository server.
        :param str type: The repository type, e.g. `deb` for a binary and `deb-src` for source package repository.
        :returns: The APT repository stanza.
        :rtype: str

        >>> r=UCSRepoPool(major=2,minor=3,patchlevel=1,part='maintained',arch='amd64')
        >>> r.deb('https://updates.software-univention.de/')
        'deb https://updates.software-univention.de/2.3/maintained/ 2.3-1/amd64/'
        """
        fmt = "%(version)s/%(part)s/ %(patch)s/%(arch)s/"
        return "%s %s%s" % (type, server, super()._format(fmt))

    def path(self, filename: str | None = None) -> str:
        """
        Format pool for directory/file access.

        :param filename: The name of a file in the repository.
        :returns: relative path.
        :rtype: str

        >>> UCSRepoPool(major=2,minor=3).path()
        '2.3/'
        >>> UCSRepoPool(major=2,minor=3,part='maintained').path()
        '2.3/maintained/'
        >>> UCSRepoPool(major=2,minor=3,patchlevel=1,part='maintained').path()
        '2.3/maintained/2.3-1/'
        >>> UCSRepoPool(major=2,minor=3,patchlevel=1,part='maintained',arch='amd64').path()
        '2.3/maintained/2.3-1/amd64/Packages.gz'
        """
        fmt = "%(version)s/%(part)s/%(patch)s/%(arch)s/" + (filename or 'Packages.gz')
        return super()._format(fmt)

    def clean(self, server: _UCSServer) -> str:
        """
        Format for :file:`/etc/apt/mirror.list`

        :param str server: The URL of the repository server.
        :returns: The APT repository stanza.
        :rtype: str
        """
        fmt = "%(version)s/%(part)s/%(patch)s/"  # %(arch)s/
        return "clean %s%s" % (server, super()._format(fmt))


class UCSRepoPoolNoArch(_UCSRepo):
    """Flat Debian APT repository without explicit architecture subdirectory."""

    ARCHS = {''}

    def __init__(self, **kw: Any) -> None:
        kw.setdefault('version', UCS_Version.FORMAT)
        kw.setdefault('patch', UCS_Version.FULLFORMAT)
        super().__init__(**kw)

    def deb(self, server: _UCSServer, type: str = "deb") -> str:
        """
        Format for :file:`/etc/apt/sources.list`.

        :param str server: The URL of the repository server.
        :param str type: The repository type, e.g. `deb` for a binary and `deb-src` for source package repository.
        :returns: The APT repository stanza.
        :rtype: str

        >>> r=UCSRepoPoolNoArch(major=2,minor=3,patch='comp',part='maintained/component',arch='all')
        >>> r.deb('https://updates.software-univention.de/')
        'deb https://updates.software-univention.de/2.3/maintained/component/comp/ ./'
        """
        fmt = "%(version)s/%(part)s/%(patch)s/ ./"
        return "%s %s%s" % (type, server, super()._format(fmt))

    def path(self, filename: str | None = None) -> str:
        """
        Format pool for directory/file access. Returns relative path.

        :param filename: The name of a file in the repository.
        :returns: relative path.
        :rtype: str

        >>> UCSRepoPoolNoArch(major=2,minor=3).path()
        '2.3/'
        >>> UCSRepoPoolNoArch(major=2,minor=3,part='maintained/component').path()
        '2.3/maintained/component/'
        >>> UCSRepoPoolNoArch(major=2,minor=3,part='maintained/component',patch='comp').path()
        '2.3/maintained/component/comp/Packages.gz'
        >>> UCSRepoPoolNoArch(major=2,minor=3,part='maintained/component',patch='comp',arch='all').path()
        '2.3/maintained/component/comp/Packages.gz'
        """
        fmt = "%(version)s/%(part)s/%(patch)s/" + (filename or 'Packages.gz')
        return super()._format(fmt)

    def clean(self, server: _UCSServer) -> str:
        """
        Format for :file:`/etc/apt/mirror.list`

        :param str server: The URL of the repository server.
        :returns: The APT repository stanza.
        :rtype: str
        """
        fmt = "%(version)s/%(part)s/%(patch)s/"
        return "clean %s%s" % (server, super()._format(fmt))


class _UCSServer:  # noqa: PLW1641
    """Abstrace base class to access UCS compatible update server."""

    @classmethod
    def load_credentials(self, ucr: ConfigRegistry) -> None:
        """
        Load credentials from UCR.

        :param ConfigRegistry ucr: An UCR instance.
        """

    def join(self, rel: str) -> str:
        """
        Return joined URI without credential.

        :param str rel: relative URI.
        :return: The joined URI.
        :rtype: str
        """
        raise NotImplementedError()

    def access(self, repo: _UCSRepo | None, filename: str | None = None, get: bool = False) -> tuple[int, int, bytes]:
        """
        Access URI and optionally get data.

        :param _UCSRepo repo: the URI to access as an instance of :py:class:`_UCSRepo`.
        :param str filename: An optional relative path.
        :param bool get: Fetch data if True - otherwise check only.
        :return: a 3-tuple (code, size, content) or None on errors.
        :rtype: tuple(int, int, bytes)
        :raises DownloadError: if the server is unreachable.
        :raises ValueError: if the credentials use an invalid encoding.
        :raises ConfigurationError: if a permanent error in the configuration occurs, e.g. the credentials are invalid or the host is unresolvable.
        :raises ProxyError: if the HTTP proxy returned an error.
        """
        raise NotImplementedError()

    def __add__(self: Self, rel: str) -> Self:
        """
        Append relative path component.

        :param str rel: Relative path.
        :return: A clone of this instance using the new base path.
        :rtype: UCSHttpServer
        """
        raise NotImplementedError()

    @property
    def prefix(self) -> str:
        raise NotImplementedError()

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _UCSServer) and self.prefix == other.prefix

    def __ne__(self, other: object) -> bool:
        return not isinstance(other, _UCSServer) or self.prefix != other.prefix


class UCSHttpServer(_UCSServer):
    """Access to UCS compatible remote update server."""

    class HTTPHeadHandler(urllib.request.BaseHandler):
        """Handle fallback from HEAD to GET if unimplemented."""

        def http_error_501(self, req: urllib.request.Request, fp: Any, code: int, msg: str, headers: dict) -> Any:  # httplib.NOT_IMPLEMENTED
            m = req.get_method()
            if m == 'HEAD' == UCSHttpServer.http_method:
                ud.debug(ud.NETWORK, ud.INFO, "HEAD not implemented at %s, switching to GET." % req)
                UCSHttpServer.http_method = 'GET'
                return self.parent.open(req, timeout=req.timeout)
            else:
                return None

    def __init__(self, baseurl: UcsRepoUrl, user_agent: str | None = None, timeout: float | None = None) -> None:
        """
        Setup URL handler for accessing a UCS repository server.

        :param UcsRepoUrl baseurl: the base URL.
        :param str user_agent: optional user agent string.
        :param int timeout: optional timeout for network access.
        """
        self.log.addHandler(logging.NullHandler())
        self.baseurl = baseurl
        self.user_agent = user_agent
        self.timeout = timeout

    log = logging.getLogger('updater.UCSHttp')

    http_method = 'HEAD'
    head_handler = HTTPHeadHandler()
    password_manager = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    auth_handler = urllib.request.HTTPBasicAuthHandler(password_manager)
    proxy_handler = urllib.request.ProxyHandler()
    # No need for ProxyBasicAuthHandler, since ProxyHandler parses netloc for @
    opener = urllib.request.build_opener(head_handler, auth_handler, proxy_handler)
    failed_hosts: set[str] = set()

    @property
    def prefix(self) -> str:
        return self.baseurl.path.lstrip('/')

    @classmethod
    def reinit(self) -> None:
        """Reload proxy settings and reset failed hosts."""
        self.proxy_handler = urllib.request.ProxyHandler()
        self.opener = urllib.request.build_opener(self.head_handler, self.auth_handler, self.proxy_handler)
        self.failed_hosts.clear()

    @classmethod
    def load_credentials(self, ucr: ConfigRegistry) -> None:
        """
        Load credentials from UCR.

        :param ConfigRegistry ucr: An UCR instance.
        """
        uuid = ucr.get('uuid/license', UUID_NULL)

        groups: dict[str, dict[str, str]] = {}
        for key, value in ucr.items():
            match = RE_CREDENTIALS.match(key)
            if match:
                realm, key = match.groups()
                cfg = groups.setdefault(realm, {})
                cfg[key] = value

        for realm, cfg in groups.items():
            try:
                uris = cfg.pop('uris').split()
            except KeyError:
                self.log.error('Incomplete credentials for realm "%s": %r', realm, cfg)
                continue
            username = cfg.pop('username', uuid)
            password = cfg.pop('password', uuid)
            if cfg:
                self.log.warning('Extra credentials for realm "%s": %r', realm, cfg)

            self.password_manager.add_password(realm, uris, username, password)
            self.log.info('Loaded credentials for realm "%s"', realm)

    def __str__(self) -> str:
        """URI with credentials."""
        return self.baseurl.private()

    def __repr__(self) -> str:
        """Return canonical string representation."""
        return '%s(%r, timeout=%r)' % (
            self.__class__.__name__,
            self.baseurl,
            self.timeout,
        )

    def __add__(self, rel: str) -> UCSHttpServer:
        """
        Append relative path component.

        :param str rel: Relative path.
        :return: A clone of this instance using the new base path.
        :rtype: UCSHttpServer
        """
        uri = copy.copy(self)
        uri.baseurl += rel
        return uri

    def join(self, rel: str) -> str:
        """
        Return joined URI without credential.

        :param str rel: relative URI.
        :return: The joined URI.
        :rtype: str
        """
        return (self.baseurl + rel).public()

    def access(self, repo: _UCSRepo | None, filename: str | None = None, get: bool = False) -> tuple[int, int, bytes]:
        """
        Access URI and optionally get data.

        :param _UCSRepo repo: the URI to access as an instance of :py:class:`_UCSRepo`.
        :param str filename: An optional relative path.
        :param bool get: Fetch data if True - otherwise check only.
        :return: a 3-tuple (code, size, content)
        :rtype: tuple(int, int, bytes)
        :raises DownloadError: if the server is unreachable.
        :raises ValueError: if the credentials use an invalid encoding.
        :raises ConfigurationError: if a permanent error in the configuration occurs, e.g. the credentials are invalid or the host is unresolvable.
        :raises ProxyError: if the HTTP proxy returned an error.
        """
        rel = filename if repo is None else repo.path(filename)
        assert rel is not None
        if self.user_agent:
            UCSHttpServer.opener.addheaders = [('User-agent', self.user_agent)]
        uri = self.join(rel)
        if self.baseurl.username and self.baseurl.password:
            UCSHttpServer.password_manager.add_password(realm=None, uri=uri, user=self.baseurl.username, passwd=self.baseurl.password)
        req = urllib.request.Request(uri)  # noqa: S310

        def get_host() -> str:
            return req.host

        if get_host() in self.failed_hosts:
            self.log.error('Already failed %s', get_host())
            raise DownloadError(uri, -1)
        if not get and UCSHttpServer.http_method != 'GET':
            # Overwrite get_method() to return "HEAD"
            def get_method(self, orig=req.get_method):
                method = orig()
                if method == 'GET':
                    return UCSHttpServer.http_method
                else:
                    return method
            req.get_method = functools.partial(get_method, req)  # type: ignore[method-assign]

        self.log.info('Requesting %s', req.get_full_url())
        ud.debug(ud.NETWORK, ud.ALL, "updater: %s %s" % (req.get_method(), req.get_full_url()))
        try:
            res = UCSHttpServer.opener.open(req, timeout=self.timeout)
            assert res
            try:
                # <http://tools.ietf.org/html/rfc2617#section-2>
                try:
                    auth = req.unredirected_hdrs['Authorization']
                    scheme, credentials = auth.split(' ', 1)
                    if scheme.lower() != 'basic':
                        raise ValueError('Only "Basic" authorization is supported')
                    try:
                        basic = base64.b64decode(credentials).decode('ISO8859-1')
                    except Exception:
                        raise ValueError('Invalid base64')
                    self.baseurl.username, self.baseurl.password = basic.split(':', 1)
                except KeyError:
                    pass
                except ValueError as ex:
                    self.log.info("Failed to decode %s: %s", auth, ex)
                code = res.getcode()
                assert code
                size = int(res.info().get('content-length', 0))
                content = res.read()
                self.log.info("Got %s %s: %d %d", req.get_method(), req.get_full_url(), code, size)
                return (code, size, content)
            finally:
                res.close()
        # direct   | proxy                                        | Error cause
        #          | valid     closed   filter   DNS     auth     |
        # HTTP:200 | HTTP:200  URL:111  URL:110  GAI:-2  HTTP:407 | OK
        # HTTP:404 | HTTP:404  URL:111  URL:110  GAI:-2  HTTP:407 | Path unknown
        # ---------+----------------------------------------------+----------------------
        # URL:111  | HTTP:404  URL:111  URL:110  GAI:-2  HTTP:407 | Port closed
        # URL:110  | HTTP:404  URL:111  URL:110  GAI:-2  HTTP:407 | Port filtered
        # GAI:-2   | HTTP:502/4URL:111  URL:110  GAI:-2  HTTP:407 | Host name unknown
        # HTTP:401 | HTTP:401  URL:111  URL:110  GAI:-2  HTTP:407 | Authorization required
        except urllib.error.HTTPError as res:
            self.log.debug("Failed %s %s: %s", req.get_method(), req.get_full_url(), res, exc_info=True)
            if res.code == httplib.UNAUTHORIZED:  # 401
                raise ConfigurationError(uri, 'credentials not accepted')
            if res.code == httplib.PROXY_AUTHENTICATION_REQUIRED:  # 407
                raise ProxyError(uri, 'credentials not accepted')
            if res.code in (httplib.BAD_GATEWAY, httplib.GATEWAY_TIMEOUT):  # 502 504
                self.failed_hosts.add(get_host())
                raise ConfigurationError(uri, 'host is unresolvable')
            raise DownloadError(uri, res.code)
        except urllib.error.URLError as e:
            self.log.debug("Failed %s %s: %s", req.get_method(), req.get_full_url(), e, exc_info=True)
            if isinstance(e.reason, str):
                reason = e.reason
            elif isinstance(e.reason, socket.timeout):
                raise ConfigurationError(uri, 'timeout in network connection')
            else:
                try:
                    reason = e.reason.args[1]  # default value for error message
                except IndexError:
                    reason = str(e)  # unknown
                if isinstance(e.reason, socket.gaierror):
                    if e.reason.args[0] == socket.EAI_NONAME:  # -2
                        reason = 'host is unresolvable'
                else:
                    if e.reason.args[0] == errno.ETIMEDOUT:  # 110
                        reason = 'port is blocked'
                    elif e.reason.args[0] == errno.ECONNREFUSED:  # 111
                        reason = 'port is closed'

            selector = req.selector
            if selector.startswith('/'):  # direct
                self.failed_hosts.add(get_host())
                raise ConfigurationError(uri, reason)
            else:  # proxy
                raise ProxyError(uri, reason)
        except TimeoutError as ex:
            self.log.debug("Failed %s %s: %s", req.get_method(), req.get_full_url(), ex, exc_info=True)
            raise ConfigurationError(uri, 'timeout in network connection')


class UCSLocalServer(_UCSServer):
    """Access to UCS compatible local update server."""

    def __init__(self, prefix: str) -> None:
        """
        Setup URL handler for accessing a UCS repository server.

        :param str prefix: The local path of the repository.
        """
        self.log = logging.getLogger('updater.UCSFile')
        self.log.addHandler(logging.NullHandler())
        prefix = str(prefix).strip('/')
        self._prefix = '%s/' % prefix if prefix else ''

    @property
    def prefix(self) -> str:
        return self._prefix

    def __str__(self) -> str:
        """Absolute file-URI."""
        return 'file:///%s' % self.prefix

    def __repr__(self) -> str:
        """Return canonical string representation."""
        return 'UCSLocalServer(prefix=%r)' % (self.prefix,)

    def __add__(self, rel: str) -> UCSLocalServer:
        """
        Append relative path component.

        :param str rel: Relative path.
        :return: A clone of this instance using the new base path.
        :rtype: UCSLocalServer
        """
        uri = copy.copy(self)
        uri._prefix += str(rel).lstrip('/')
        return uri

    def join(self, rel: str) -> str:
        """
        Return joined URI without credential.

        :param str rel: relative URI.
        :return: The joined URI.
        :rtype: str
        """
        uri = self.__str__()
        uri += str(rel).lstrip('/')
        return uri

    def access(self, repo: _UCSRepo | None, filename: str | None = None, get: bool = False) -> tuple[int, int, bytes]:
        """
        Access URI and optionally get data.

        :param _UCSRepo repo: the URI to access as an instance of :py:class:`_UCSRepo`.
        :param str filename: An optional relative path.
        :param bool get: Fetch data if True - otherwise check only.
        :return: a 3-tuple (code, size, content)
        :rtype: tuple(int, int, bytes)
        :raises DownloadError: if the server is unreachable.
        :raises ValueError: if the credentials use an invalid encoding.
        :raises ConfigurationError: if a permanent error in the configuration occurs, e.g. the credentials are invalid or the host is unresolvable.
        :raises ProxyError: if the HTTP proxy returned an error.
        """
        rel = filename if repo is None else repo.path(filename)
        assert rel is not None
        uri = self.join(rel)
        ud.debug(ud.NETWORK, ud.ALL, "updater: %s" % (uri,))
        # urllib.request.urlopen() doesn't work for directories
        assert uri.startswith('file://')
        path = uri[len('file://'):]
        if os.path.exists(path):
            if os.path.isdir(path):
                self.log.info("Got %s", path)
                return (httplib.OK, 0, b'')  # 200
            elif os.path.isfile(path):
                with open(path, 'rb') as f:
                    data = f.read()
                self.log.info("Got %s: %d", path, len(data))
                return (httplib.OK, len(data), data)  # 200
        self.log.error("Failed %s", path)
        raise DownloadError(uri, -1)


class Component:
    FN_APTSOURCES = '/etc/apt/sources.list.d/20_ucs-online-component.list'
    UCRV = "repository/online/component/{}/{}"
    AVAILABLE = 'available'
    NOT_FOUND = 'not_found'
    DISABLED = 'disabled'
    UNKNOWN = 'unknown'
    PERMISSION_DENIED = 'permission_denied'

    def __init__(self, updater: UniventionUpdater, name: str) -> None:
        self.updater = updater
        self.name = name

    def __lt__(self, other) -> bool:
        return self.name < other.name if isinstance(other, Component) else NotImplemented

    def __le__(self, other) -> bool:
        return self.name <= other.name if isinstance(other, Component) else NotImplemented

    def __eq__(self, other) -> bool:
        return isinstance(other, Component) and self.name == other.name

    def __ne__(self, other) -> bool:
        return not isinstance(other, Component) or self.name != other.name

    def __ge__(self, other) -> bool:
        return self.name >= other.name if isinstance(other, Component) else NotImplemented

    def __gt__(self, other) -> bool:
        return self.name > other.name if isinstance(other, Component) else NotImplemented

    def __hash__(self) -> int:
        return hash(self.name)

    def __str__(self) -> str:
        return f"Component({self.name})"

    def ucrv(self, key: str = "") -> str:
        return "/".join(filter(None, ("repository", "online", "component", self.name, key)))

    def __getitem__(self, key: str) -> str:
        return self.updater.configRegistry.get(self.ucrv(key)) or ""

    def __bool__(self) -> bool:
        return self.updater.configRegistry.is_true(self.ucrv())

    __nonzero__ = __bool__

    def _versions(self, start: UCS_Version | None = None, end: UCS_Version | None = None) -> set[UCS_Version]:
        version = self["version"]
        versions = set(RE_SPLIT_MULTI.split(version))
        return {
            UCS_Version((*ver.mm, 0))
            for ver, _data in self.updater.get_releases(start, end)
            if {ver.FORMAT % ver, "current", ""} & versions
        }

    @property
    def current(self) -> bool:
        version = self["version"]
        versions = set(RE_SPLIT_MULTI.split(version))
        return bool(versions & {"current"})

    @property
    def default_packages(self) -> set[str]:
        """
        Returns a set of (meta) package names to be installed for this component.

        :returns: a set of package names.
        """
        return {
            pkg
            for var in ('defaultpackages', 'defaultpackage')
            for pkg in RE_SPLIT_MULTI.split(self[var])
        } - {""}

    def defaultpackage_installed(self, ignore_invalid_package_names: bool = True) -> bool | None:
        """
        Returns installation status of component's default packages

        :param bool ignore_invalid_package_names: Ignore invalid package names.
        :returns: On of the values:

            None
                no default packages are defined
            True
                all default packages are installed
            False
                at least one package is not installed

        :rtype: None or bool
        :raises ValueError: if UCR variable contains invalid package names if ignore_invalid_package_names=False
        """
        pkglist = self.default_packages
        if not pkglist:
            return None

        # check package names
        for pkg in pkglist:
            match = RE_ALLOWED_DEBIAN_PKGNAMES.search(pkg)
            if not match:
                if ignore_invalid_package_names:
                    continue
                raise ValueError('invalid package name (%s)' % pkg)

        cmd = ['/usr/bin/dpkg-query', '-W', '-f', '${Status}\\n']
        cmd.extend(pkglist)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, _stderr = (data.decode("UTF-8", errors="replace") for data in p.communicate())
        # count number of "Status: install ok installed" lines
        installed_correctly = [x for x in stdout.splitlines() if x.endswith(' ok installed')]
        # if pkg count and number of counted lines match, all packages are installed
        return len(pkglist) == len(installed_correctly)

    def baseurl(self, for_mirror_list: bool = False) -> UcsRepoUrl:
        r"""
        Calculate the base URL for a component.

        :param bool for_mirror_list: Use external or local repository.

        CS (component server)
            value of `repository/online/component/%s/server`
        MS (mirror server)
            value of `repository/mirror/server`
        RS (repository server)
            value of `repository/online/server`
        \-
            value is unset or no entry
        /blank/
            value is irrelevant

        +-------------+----------+------------+---------+------------+------------+-------------+
        | UCR configuration                             |Result                   |             |
        +-------------+----------+------------+---------+------------+------------+             |
        | isRepoServer|enabled   |localmirror |server   |sources.list mirror.list |             |
        +=============+==========+============+=========+============+============+=============+
        | False       |False     |False       |\-       |\-          |\-          |no           |
        +             +----------+------------+---------+------------+------------+local        |
        |             |True      |            |\-       |RS          |\-          |repository   |
        +             +----------+------------+---------+------------+------------+mirror       |
        |             |True      |            |CS       |CS          |\-          |             |
        +-------------+----------+------------+---------+------------+------------+-------------+
        | True        |False     |False       |         |\-          |\-          |local        |
        +             +----------+------------+---------+------------+------------+repository   |
        |             |False     |True        |\-       |\-          |MS          |mirror       |
        +             +----------+------------+---------+------------+------------+             |
        |             |False     |True        |CS       |\-          |CS          |             |
        +             +----------+------------+---------+------------+------------+             |
        |             |True      |False       |\-       |MS          |\-          |             |
        +             +----------+------------+---------+------------+------------+             |
        |             |True      |False       |CS       |CS          |\-          |             |
        +             +----------+------------+---------+------------+------------+             |
        |             |True      |True        |\-       |RS          |MS          |             |
        +             +----------+------------+---------+------------+------------+             |
        |             |True      |True        |CS       |RS          |CS          |             |
        +             +----------+------------+---------+------------+------------+-------------+
        |             |False     |\-          |\-       |\-          |\-          |backward     |
        +             +----------+            +---------+------------+------------+compabibility|
        |             |True      |            |\-       |RS          |MS          |[1]_         |
        +             +----------+            +---------+------------+------------+             |
        |             |True      |            |CS       |RS          |CS          |             |
        +-------------+----------+------------+---------+------------+------------+-------------+

        .. [1] if `repository/online/component/%s/localmirror` is unset, then the value of `repository/online/component/%s` will be used to achieve backward compatibility.
        """
        c_prefix = self.ucrv()
        if self.updater.is_repository_server:
            m_url = UcsRepoUrl(self.updater.configRegistry, 'repository/mirror')
            c_enabled = bool(self)
            c_localmirror = self.updater.configRegistry.is_true(self.ucrv("localmirror"), c_enabled)

            if for_mirror_list:  # mirror.list
                if c_localmirror:
                    return UcsRepoUrl(self.updater.configRegistry, c_prefix, m_url)
            else:  # sources.list
                if c_enabled:
                    if c_localmirror:
                        return self.updater.repourl
                    else:
                        return UcsRepoUrl(self.updater.configRegistry, c_prefix, m_url)
        else:
            return UcsRepoUrl(self.updater.configRegistry, c_prefix, self.updater.repourl)

        raise CannotResolveComponentServerError(self.name, for_mirror_list)

    def server(self, for_mirror_list: bool = False) -> UCSHttpServer:
        """
        Return :py:class:`UCSHttpServer` for component as configures via UCR.

        :param bool for_mirror_list: component entries for `mirror.list` will be returned, otherwise component entries for local `sources.list`.
        :returns: The repository server for the component.
        :rtype: UCSHttpServer
        :raises ConfigurationError: if the configured server is not usable.
        """
        c_url = copy.copy(self.baseurl(for_mirror_list))
        prefix = c_url.path or self['prefix']
        c_url.path = ''

        user_agent = self.updater._get_user_agent_string()

        server = UCSHttpServer(
            baseurl=c_url,
            user_agent=user_agent,
            timeout=self.updater.timeout,
        )
        try:
            # if prefix.lower() == 'none' ==> use no prefix
            if prefix and prefix.lower().strip('/') == 'none':
                try:
                    assert server.access(None, '')
                except DownloadError as e:
                    uri, _code = e.args
                    raise ConfigurationError(uri, 'absent prefix forced - component %s not found: %s' % (self.name, uri))
            else:
                # FIXME: PMH stop iterating
                for testserver in [
                    server + '/univention-repository/',
                    server + self.updater.repourl.path if self.updater.repourl.path else None,
                    server,
                ]:
                    if not testserver:
                        continue
                    if prefix:  # append prefix if defined
                        testserver = testserver + '%s/' % (prefix.strip('/'),)
                    try:
                        assert testserver.access(None, '')
                        return testserver
                    except DownloadError as e:
                        ud.debug(ud.NETWORK, ud.ALL, "%s" % e)
                        uri, _code = e.args
                raise ConfigurationError(uri, 'non-existing component prefix: %s' % (uri,))

        except ConfigurationError:
            if self.updater.check_access:
                raise
        return server

    def versions(self, start: UCS_Version, end: UCS_Version, for_mirror_list: bool = False) -> Iterator[tuple[UCSHttpServer, _UCSRepo]]:
        """
        Iterate component versions.

        :param start: Minimum requried version.
        :param end: Maximum allowed version.
        :param bool clean: Add additional `clean` statements for `apt-mirror`.
        :param bool for_mirror_list: component entries for `mirror.list` will be returned, otherwise component entries for local `sources.list`.
        :returns: A iterator returning 2-tuples (server, ver).
        """
        server = self.server(for_mirror_list=for_mirror_list)
        struct = self.layout(prefix=server, patch=self.name)
        versions = self._versions(start, end)
        parts = self._parts

        for ver in sorted(versions):
            struct.mmp = ver.mmp
            for struct.part in parts:
                yield server, struct

    def repositories(
        self,
        start: UCS_Version,
        end: UCS_Version,
        clean: bool = False,
        for_mirror_list: bool = False,
        failed: set[tuple[Component, str]] | None = None,
    ) -> Iterator[str]:
        """
        Return list of Debian repository statements for requested component.

        :param start: Minimum requried version.
        :param end: Maximum allowed version.
        :param bool clean: Add additional `clean` statements for `apt-mirror`.
        :param bool for_mirror_list: component entries for `mirror.list` will be returned, otherwise component entries for local `sources.list`.
        :param failed: A set to recive the failed component names.
        :returns: A list of strings with APT statements.
        """
        for server, struct in self.versions(start, end, for_mirror_list):
            try:
                for struct.arch in sorted(struct.ARCHS):
                    assert server.access(struct, "Packages.gz")
                    yield struct.deb(server)

                if clean:
                    yield struct.clean(server)

                if self.updater.sources:
                    struct.arch = "source"
                    assert server.access(struct, "Sources.gz")
                    yield struct.deb(server, "deb-src")
            except DownloadError as ex:
                if failed is not None:
                    failed.add((self, str(ex)))
                else:
                    raise

    def status(self) -> str:
        """
        Returns the current status of specified component based on :file:`/etc/apt/sources.list.d/20_ucs-online-component.list`

        :returns: One of the strings:

            :py:const:`DISABLED`
                component has been disabled via UCR
            :py:const:`AVAILABLE`
                component is enabled and at least one valid repo string has been found in .list file
            :py:const:`NOT_FOUND`
                component is enabled but no valid repo string has been found in .list file
            :py:const:`PERMISSION_DENIED`
                component is enabled but authentication failed
            :py:const:`UNKNOWN`
                component's status is unknown

        :rtype: str
        """
        if not bool(self):
            return self.DISABLED

        try:
            comp_file = open(self.FN_APTSOURCES)
        except OSError:
            return self.UNKNOWN
        rePath = re.compile('(un)?maintained/component/ ?%s/' % self.name)
        reDenied = re.compile('credentials not accepted: %s$' % self.name)
        try:
            # default: file contains no valid repo entry
            result = self.NOT_FOUND
            for line in comp_file:
                if line.startswith('deb ') and rePath.search(line):
                    # at least one repo has been found
                    result = self.AVAILABLE
                elif reDenied.search(line):
                    # stop immediately if at least one repo has authentication problems
                    return self.PERMISSION_DENIED
            # return result
            return result
        finally:
            comp_file.close()

    @property
    def layout(self) -> type[_UCSRepo]:
        value = self["layout"]
        layouts: dict[str, type[_UCSRepo]] = {
            "": UCSRepoPool,
            "arch": UCSRepoPool,
            "flat": UCSRepoPoolNoArch,
        }
        try:
            return layouts[value]
        except LookupError:
            raise ValueError(value)

    @property
    def _parts(self) -> list[str]:
        parts = ["maintained"] + ["unmaintained"][:self.updater.configRegistry.is_true(self.ucrv('unmaintained'))]
        return ['%s/component' % (part,) for part in parts]


class UniventionUpdater:
    """Handle UCS package repositories."""

    def __init__(self, check_access: bool = True) -> None:
        """
        Create new updater with settings from UCR.

        :param bool check_access: Check if repository server is reachable on init.
        :raises ConfigurationError: if configured server is not available immediately.
        """
        self.log = logging.getLogger('updater.Updater')
        self.log.addHandler(logging.NullHandler())
        self.check_access = check_access
        self.connection = None

        self.configRegistry = ConfigRegistry()
        self.ucr_reinit()

    def config_repository(self) -> None:
        """Retrieve configuration to access repository. Overridden by :py:class:`univention.updater.UniventionMirror`."""
        self.online_repository = self.configRegistry.is_true('repository/online', True)
        self.repourl = UcsRepoUrl(self.configRegistry, 'repository/online')
        self.sources = self.configRegistry.is_true('repository/online/sources', False)
        self.timeout = float(self.configRegistry.get('repository/online/timeout', 30))
        self.script_verify = self.configRegistry.is_true('repository/online/verify', True)
        UCSHttpServer.http_method = self.configRegistry.get('repository/online/httpmethod', 'HEAD').upper()

    def ucr_reinit(self) -> None:
        """Re-initialize settings."""
        self.configRegistry.load()

        self.is_repository_server = self.configRegistry.is_true('local/repository', False)

        reinitUCSHttpServer = False
        if self.configRegistry.get('proxy/http'):
            os.environ['http_proxy'] = self.configRegistry['proxy/http']
            os.environ['https_proxy'] = self.configRegistry['proxy/http']
            reinitUCSHttpServer = True
        if self.configRegistry.get('proxy/https'):
            os.environ['https_proxy'] = self.configRegistry['proxy/https']
            reinitUCSHttpServer = True
        if self.configRegistry.get('proxy/no_proxy'):
            os.environ['no_proxy'] = self.configRegistry['proxy/no_proxy']
            reinitUCSHttpServer = True
        if reinitUCSHttpServer:
            UCSHttpServer.reinit()

        # UCS version
        self.current_version = UCS_Version("%(version/version)s-%(version/patchlevel)s" % self.configRegistry)
        self.erratalevel = int(self.configRegistry.get('version/erratalevel', 0))

        # UniventionMirror needs to provide its own settings
        self.config_repository()

        if not self.online_repository:
            self.log.info('Disabled')
            self.server: _UCSServer = UCSLocalServer('')
            self.releases: dict[str, Any] = {"error": "offline"}
            return

        # generate user agent string
        user_agent = self._get_user_agent_string()
        UCSHttpServer.load_credentials(self.configRegistry)

        self.server = UCSHttpServer(
            baseurl=self.repourl,
            user_agent=user_agent,
            timeout=self.timeout,
        )
        self._get_releases()

    def _get_releases(self) -> None:
        """Detect server prefix and download `ucs-releases.json` file."""
        try:
            if not self.repourl.path:
                try:
                    _code, _size, data = self.server.access(None, '/univention-repository/ucs-releases.json', get=True)
                    self.server += '/univention-repository/'
                    self.log.info('Using detected prefix /univention-repository/')
                    self.releases = json.loads(data)
                except DownloadError as e:
                    self.log.info('No prefix /univention-repository/ detected, using /')
                    ud.debug(ud.NETWORK, ud.ALL, "%s" % e)
            # Validate server settings
            try:
                _code, _size, data = self.server.access(None, 'ucs-releases.json', get=True)
                self.log.info('Using configured prefix %s', self.repourl.path)
                self.releases = json.loads(data)
            except DownloadError as e:
                self.log.exception('Failed configured prefix %s', self.repourl.path)
                uri, _code = e.args
                raise ConfigurationError(uri, 'non-existing prefix "%s": %s' % (self.repourl.path, uri))
        except ConfigurationError as e:
            if self.check_access:
                self.log.fatal('Failed server detection: %s', e, exc_info=True)
                raise
            self.releases = {"error": str(e)}
        except (ValueError, LookupError) as exc:
            ud.debug(ud.NETWORK, ud.ERROR, 'Querying maintenance information failed: %s' % (exc,))
            self.releases = {"error": str(exc)}

    def get_releases(self, start: UCS_Version | None = None, end: UCS_Version | None = None) -> Iterator[tuple[UCS_Version, dict[str, Any]]]:
        """
        Return UCS releases in range.

        :param start: Minimum requried version.
        :param end: Maximum allowed version.
        :returns: Iterator of 2-tuples (UCS_Version, data).
        """
        for major_release in self.releases.get('releases', []):
            for minor_release in major_release['minors']:
                for patchlevel_release in minor_release['patchlevels']:
                    ver = UCS_Version((
                        major_release['major'],
                        minor_release['minor'],
                        patchlevel_release['patchlevel'],
                    ))
                    if start and ver < start:
                        continue
                    if end and ver > end:
                        continue
                    yield (ver, dict(patchlevel_release, major=major_release['major'], minor=minor_release['minor']))

    def get_next_version(self, version: UCS_Version, components: Iterable[Component] = [], errorsto: Literal["stderr", "exception", "none"] = 'stderr') -> UCS_Version | None:
        """
        Check if a new patchlevel, minor or major release is available for the given version.
        Components must be available for the same major.minor version.

        :param UCS_Version version: A UCS release version.
        :param components: A list of components, which must be available for the next release.
        :param str errorsto: Select method of reporting errors; on of 'stderr', 'exception', 'none'.
        :returns: The next UCS release or None.
        :rtype: UCS_Version or None
        :raises RequiredComponentError: if a required component is missing
        """
        try:
            ver = min(ver for ver, _data in self.get_releases() if ver > version)
        except ValueError:
            return None

        self.log.info('Found version %s', ver)

        failed: set[tuple[Component, str]] = set()
        for component in components:
            self.log.info('Checking for component %s', component.name)
            any(component.repositories(ver, ver, failed=failed if component.current else set()))

        if failed:
            ex = RequiredComponentError(str(ver), {comp.name for comp, ex in failed})
            if errorsto == 'exception':
                raise ex
            elif errorsto == 'stderr':
                print(ex, file=sys.stderr)
            return None

        self.log.info('Going for version %s', ver)
        return ver

    def get_all_available_release_updates(self, ucs_version: UCS_Version | None = None) -> tuple[list[UCS_Version], set[str] | None]:
        """
        Returns a list of all available release updates - the function takes required components into account
        and stops if a required component is missing

        :param ucs_version: starts travelling through available version from version.
        :type ucs_version: UCS_Version or None
        :returns: a list of 2-tuple `(versions, blocking_component)`, where `versions` is a list of UCS release and `blocking_component` is the first missing component blocking the update.
        :rtype: tuple(list[str], str or None)
        """
        ucs_version = ucs_version or self.current_version
        components = self.get_components(only_current=True)

        result: list[UCS_Version] = []
        while ucs_version:
            try:
                ucs_version = self.get_next_version(ucs_version, components, errorsto='exception')
            except RequiredComponentError as ex:
                self.log.warning('Update blocked by components %s', ', '.join(ex.components))
                # ex.components blocks update to next version ==> return current list and blocking component
                return result, ex.components

            if not ucs_version:
                break
            result.append(ucs_version)
        self.log.info('Found release updates %r', result)
        return result, None

    def release_update_available(self, ucs_version: UCS_Version | None = None, errorsto: Literal["stderr", "exception", "none"] = 'stderr') -> UCS_Version | None:
        """
        Check if an update is available for the `ucs_version`.

        :param str ucs_version: The UCS release to check.
        :param str errorsto: Select method of reporting errors; on of 'stderr', 'exception', 'none'.
        :returns: The next UCS release or None.
        :rtype: str or None
        """
        ucs_version = ucs_version or self.current_version
        components = self.get_components(only_current=True)
        return self.get_next_version(UCS_Version(ucs_version), components, errorsto)

    def release_update_temporary_sources_list(self, version: UCS_Version) -> list[str]:
        """
        Return list of Debian repository statements for the release update including all enabled components.

        :param version: The UCS release.
        :returns: A list of Debian APT `sources.list` lines.
        :rtype: list[str]
        """
        result = [UCSRepoPool5(version).deb(self.server)]
        for comp in self.get_components():
            try:
                result += list(comp.repositories(version, version, failed=set()))
            except (ConfigurationError, ProxyError):
                if comp.current:
                    raise

        return result

    def component(self, name: str) -> Component:
        return Component(self, name)

    def get_components(self, only_localmirror_enabled: bool = False, all: bool = False, only_current: bool = False) -> set[Component]:
        """
        Retrieve all (enabled) components from registry as set().
        By default, only "enabled" components will be returned (repository/online/component/%s=$TRUE).

        :param bool only_localmirror_enabled:
            Only the components enabled for local mirroring.
            If only_`localmirror`_enabled is `True`, then all components with `repository/online/component/%s/localmirror=$TRUE` will be returned.
            If `repository/online/component/%s/localmirror` is not set, then the value of `repository/online/component/%s` is used for backward compatibility.
        :param bool all: Also return not enabled components.
        :param bool only_current: Only return components marked as "current".
        :returns: The set of (enabled) components.
        """
        components = set()
        for key in self.configRegistry:
            match = RE_COMPONENT.match(key)
            if not match:
                continue
            component, = match.groups()
            comp = self.component(component)
            enabled = bool(comp)
            if only_localmirror_enabled:
                enabled = self.configRegistry.is_true(comp.ucrv("localmirror"), enabled)
            if only_current and not comp.current:
                continue
            if all or enabled:
                components.add(comp)
        return components

    def component_update_get_packages(self) -> tuple[list[tuple[str, str]], list[tuple[str, str, str]], list[tuple[str, str]]]:
        """
        Return tuple with list of (new, upgradeable, removed) packages.

        :return: A 3-tuple (new, upgraded, removed).
        :rtype: tuple(list[str], list[str], list[str])
        """
        env = dict(os.environ, LC_ALL="C.UTF-8")

        proc = subprocess.Popen(("univention-config-registry", "commit", Component.FN_APTSOURCES), stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = (data.decode("UTF-8", errors="replace") for data in proc.communicate())
        if stderr:
            ud.debug(ud.NETWORK, ud.PROCESS, 'stderr=%s' % stderr)
        if stdout:
            ud.debug(ud.NETWORK, ud.INFO, 'stdout=%s' % stdout)
        # FIXME: error handling

        proc = subprocess.Popen(cmd_update, shell=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = (data.decode("UTF-8", errors="replace") for data in proc.communicate())
        if stderr:
            ud.debug(ud.NETWORK, ud.PROCESS, 'stderr=%s' % stderr)
        if stdout:
            ud.debug(ud.NETWORK, ud.INFO, 'stdout=%s' % stdout)
        # FIXME: error handling

        proc = subprocess.Popen(cmd_dist_upgrade_sim, shell=True, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = (data.decode("UTF-8", errors="replace") for data in proc.communicate())
        if stderr:
            ud.debug(ud.NETWORK, ud.PROCESS, 'stderr=%s' % stderr)
        if stdout:
            ud.debug(ud.NETWORK, ud.INFO, 'stdout=%s' % stdout)

        if proc.returncode == 100:
            raise UnmetDependencyError(stderr)

        new_packages: list[tuple[str, str]] = []
        upgraded_packages: list[tuple[str, str, str]] = []
        removed_packages: list[tuple[str, str]] = []
        for line in stdout.splitlines():
            line_split = line.split(' ')
            if line.startswith('Inst '):
                # upgrade:
                #    Inst univention-updater [3.1.1-5] (3.1.1-6.408.200810311159 192.168.0.10)
                # inst:
                #    Inst mc (1:4.6.1-6.12.200710211124 oxae-update.open-xchange.com)
                if len(line_split) > 3:
                    if line_split[2].startswith('[') and line_split[2].endswith(']'):
                        ud.debug(ud.NETWORK, ud.PROCESS, 'Added %s to the list of upgraded packages' % line_split[1])
                        upgraded_packages.append((line_split[1], line_split[2].replace('[', '').replace(']', ''), line_split[3].replace('(', '')))
                    else:
                        ud.debug(ud.NETWORK, ud.PROCESS, 'Added %s to the list of new packages' % line_split[1])
                        new_packages.append((line_split[1], line_split[2].replace('(', '')))
                else:
                    ud.debug(ud.NETWORK, ud.WARN, 'unable to parse the update line: %s' % line)
                    continue
            elif line.startswith('Remv '):
                if len(line_split) > 3:
                    ud.debug(ud.NETWORK, ud.PROCESS, 'Added %s to the list of removed packages' % line_split[1])
                    removed_packages.append((line_split[1], line_split[2].replace('(', '')))
                elif len(line_split) > 2:
                    ud.debug(ud.NETWORK, ud.PROCESS, 'Added %s to the list of removed packages' % line_split[1])
                    removed_packages.append((line_split[1], 'unknown'))
                else:
                    ud.debug(ud.NETWORK, ud.WARN, 'unable to parse the update line: %s' % line)
                    continue

        return (new_packages, upgraded_packages, removed_packages)

    def run_dist_upgrade(self) -> int:
        """
        Run `apt-get dist-upgrade` command.

        :returns: a 3-tuple (return_code, stdout, stderr)
        :rtype: tuple(int, str, str)
        """
        env = dict(os.environ, DEBIAN_FRONTEND="noninteractive")
        with open("/var/log/univention/updater.log", "a") as log:
            return subprocess.call(cmd_dist_upgrade, shell=True, env=env, stdout=log, stderr=log)

    def print_component_repositories(self, clean: bool = False, start: UCS_Version | None = None, end: UCS_Version | None = None, for_mirror_list: bool = False) -> str:
        """
        Return a string of Debian repository statements for all enabled components.

        :param bool clean: Add additional `clean` statements for `apt-mirror` if enabled by UCRV `repository/online/component/%s/clean`.
        :param UCS_Version start: optional smallest UCS release to return.
        :param UCS_Version end: optional largest UCS release to return.
        :param bool for_mirror_list: component entries for `mirror.list` will be returned, otherwise component entries for local `sources.list`.
        :returns: A string with APT statement lines.
        :rtype: str
        """
        if not self.online_repository:
            return ''

        if clean:
            clean = self.configRegistry.is_true('online/repository/clean', False)

        result: list[str] = []
        failed: set[tuple[Component, str]] = set()
        for comp in sorted(self.get_components(only_localmirror_enabled=for_mirror_list)):
            result += comp.repositories(start, end, clean=clean, for_mirror_list=for_mirror_list, failed=failed)
        result += ["# Component %s: %s" % (comp.name, ex) for comp, ex in failed]

        return '\n'.join(result)

    def _get_user_agent_string(self) -> str:
        """
        Return the HTTP user agent string encoding the enabled components.

        :returns: A HTTP user agent string.
        :rtype: str
        """
        # USER_AGENT='updater/identify - version/version-version/patchlevel errata version/erratalevel - uuid/system - uuid/license'
        # USER_AGENT='UCS updater - 3.1-0 errata28 - 77e6406d-7a3e-40b3-a398-81cf119c9ef7 - 4c52d2da-d04d-4b05-a593-1974ee851fc8'
        # USER_AGENT='UCS updater - 3.1-0 errata28 - 77e6406d-7a3e-40b3-a398-81cf119c9ef7 - 00000000-0000-0000-0000-000000000000'
        return '%s - %s-%s errata%s - %s - %s - %s - %s' % (
            self.configRegistry.get('updater/identify', 'UCS'),
            self.configRegistry.get('version/version'), self.configRegistry.get('version/patchlevel'),
            self.configRegistry.get('version/erratalevel'),
            self.configRegistry.get('uuid/system', UUID_NULL),
            self.configRegistry.get('uuid/license', UUID_NULL),
            ','.join(self.configRegistry.get('repository/app_center/installed', '').split('-')),
            self.configRegistry.get('updater/statistics', ''),
        )

    @staticmethod
    def call_sh_files(scripts: Iterable[tuple[_UCSServer, _UCSRepo, str | None, str, bytes]], logname: str, *args: str) -> Iterator[tuple[str, str]]:
        """
        Get pre- and postup.sh files and call them in the right order::

            u = UniventionUpdater()
            ver = u.get_next_version(u.current_version)
            scripts = u.get_sh_files(ver, ver)
            for phase, order in u.call_sh_files(scripts, '/var/log/univention/updater.log', ver):
              if (phase, order) == ('update', 'main'):
                pass

        :param scripts: A generator returning the script to call, e.g. :py:meth:`get_sh_files`
        :param str logname: The file name of the log file.
        :param args: Additional arguments to pass through to the scripts.
        :returns: A generator returning 2-tuples (phase, part)
        """

        def call(*cmd: str) -> int:
            """
            Execute script.

            :param cmd: The command to execute in a sub-process.
            :type cmd: list(str)
            :returns: The exit code of the child process.
            :rtype: int
            """
            commandline = ' '.join(["'%s'" % a.replace("'", "'\\''") for a in cmd])
            ud.debug(ud.NETWORK, ud.INFO, "Calling %s" % commandline)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            tee = subprocess.Popen(('tee', '-a', logname), stdin=p.stdout)
            # Order is important! See bug #16454
            tee.wait()
            p.wait()
            return p.returncode

        # download scripts
        yield "update", "pre"
        main: dict[str, list[tuple[str, str]]] = {'preup': [], 'postup': []}
        comp: dict[str, list[tuple[str, str]]] = {'preup': [], 'postup': []}
        # save scripts to temporary files
        with TemporaryDirectory() as tempdir:
            for server, struct, phase, path, data in scripts:
                if phase is None:
                    continue
                assert data is not None
                uri = server.join(path)
                name = os.path.join(tempdir, uri.replace("/", "_"))
                try:
                    with open(name, "wb") as fd:
                        fd.write(data)
                        os.fchmod(fd.fileno(), 0o744)

                    ud.debug(ud.NETWORK, ud.INFO, "%s saved to %s" % (uri, name))
                    is_component = hasattr(struct, 'part') and struct.part.endswith('/component')
                    memo = comp if is_component else main
                    memo[phase].append((name, str(struct.patch)))
                except OSError as ex:
                    ud.debug(ud.NETWORK, ud.ERROR, "Error saving %s to %s: %s" % (uri, name, ex))

            # call component/preup.sh pre $args
            yield "preup", "pre"
            for (script, patch) in comp['preup']:
                if call(script, 'pre', *args) != 0:
                    raise PreconditionError('preup', 'pre', patch, script)

            # call $next_version/preup.sh
            yield "preup", "main"
            for (script, patch) in main['preup']:
                if call(script, *args) != 0:
                    raise PreconditionError('preup', 'main', patch, script)

            # call component/preup.sh post $args
            yield "preup", "post"
            for (script, patch) in comp['preup']:
                if call(script, 'post', *args) != 0:
                    raise PreconditionError('preup', 'post', patch, script)

            # call $update/commands/distupgrade or $update/commands/upgrade
            yield "update", "main"

            # call component/postup.sh pos $args
            yield "postup", "pre"
            for (script, patch) in comp['postup']:
                if call(script, 'pre', *args) != 0:
                    raise PreconditionError('postup', 'pre', patch, script)

            # call $next_version/postup.sh
            yield "postup", "main"
            for (script, patch) in main['postup']:
                if call(script, *args) != 0:
                    raise PreconditionError('postup', 'main', patch, script)

            # call component/postup.sh post $args
            yield "postup", "post"
            for (script, patch) in comp['postup']:
                if call(script, 'post', *args) != 0:
                    raise PreconditionError('postup', 'post', patch, script)

        # clean up
        yield "update", "post"

    def get_sh_files(self, start: UCS_Version, end: UCS_Version, mirror: bool = False) -> Iterator[tuple[_UCSServer, _UCSRepo, str | None, str, bytes]]:
        """
        Return all preup- and postup-scripts of repositories.

        :param UCS_Version start: The UCS release to start from.
        :param UCS_Version end: The UCS release where to stop.
        :param bool mirror: Use the settings for mirroring.
        :returns: iteratable (server, struct, phase, path, script)
        :raises VerificationError: if the PGP signature is invalid.

        See :py:meth:`call_sh_files` for an example.
        """
        def all_repos() -> Iterator[tuple[_UCSServer, _UCSRepo, bool]]:
            self.log.info('Searching releases [%s..%s]', start, end)
            for ver, _data in self.get_releases(start, end):
                yield self.server, UCSRepoPool5(release=ver, prefix=self.server), True

            self.log.info('Searching components [%s..%s]', start, end)
            components = self.get_components(only_localmirror_enabled=mirror)
            for comp in components:
                for server, struct in comp.versions(start, end, mirror):
                    struct.arch = "all"
                    self.log.info('Component %s from %s versions %r', comp.name, server, struct)
                    yield server, struct, comp.current

        for server, struct, critical in all_repos():
            uses_proxy = hasattr(server, "proxy_handler") and server.proxy_handler.proxies  # type: ignore
            for phase in ('preup', 'postup'):
                name = '%s.sh' % phase
                path = struct.path(name)
                ud.debug(ud.NETWORK, ud.ALL, "Accessing %s" % path)
                try:
                    _code, _size, script = server.access(struct, name, get=True)
                    # Bug #37031: dansguarding is lying and returns 200 even for blocked content
                    if not script.startswith(b'#!') and uses_proxy:
                        uri = server.join(path)
                        raise ProxyError(uri, "download blocked by proxy?")
                    if self.script_verify and struct >= UCS_Version((3, 2, 0)):
                        name_gpg = name + '.gpg'
                        path_gpg = struct.path(name_gpg)
                        try:
                            _code, _size, signature = server.access(struct, name_gpg, get=True)
                            if not signature.startswith(b"-----BEGIN PGP SIGNATURE-----") and uses_proxy:
                                uri = server.join(path_gpg)
                                raise ProxyError(uri, "download blocked by proxy?")
                        except DownloadError:
                            raise VerificationError(path_gpg, "Signature download failed")
                        error = verify_script(script, signature)
                        if error is not None:
                            raise VerificationError(path, "Invalid signature: %r" % error)
                        yield server, struct, None, path_gpg, signature
                    yield server, struct, phase, path, script
                except DownloadError as e:
                    ud.debug(ud.NETWORK, ud.ALL, "%s" % e)
                except ConfigurationError:
                    if critical:
                        raise


class LocalUpdater(UniventionUpdater):
    """Direct file access to local repository."""

    def __init__(self) -> None:
        UniventionUpdater.__init__(self)
        self.log = logging.getLogger('updater.LocalUpdater')
        self.log.addHandler(logging.NullHandler())
        repository_path = self.configRegistry.get('repository/mirror/basepath', '/var/lib/univention-repository')
        self.server: _UCSServer = UCSLocalServer("%s/mirror/" % repository_path)
