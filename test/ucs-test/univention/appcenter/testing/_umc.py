#!/usr/bin/python3
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2017-2025 Univention GmbH
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
"""
Univention common Python library to manage connections to remote |UMC| servers.

>>> umc = Client()
>>> umc.authenticate_with_machine_account()
>>> response = umc.umc_get('session-info')
>>> response.status
2000
>>> umc.umc_logout()
"""

from __future__ import annotations

import base64
import json
import locale
import ssl
from http.client import HTTPException, HTTPSConnection
from http.cookies import SimpleCookie
from typing import TYPE_CHECKING, Any, TypeVar, overload

from univention.config_registry import ConfigRegistry


if TYPE_CHECKING:
    import http.client


_T = TypeVar("_T")


def _get_ucr() -> ConfigRegistry:
    ucr = ConfigRegistry()
    ucr.load()
    return ucr


def _get_useragent() -> str:
    ucr = _get_ucr()
    return 'UCS/%s (univention.lib.umc/%s-errata%s)' % (ucr.get('version/version', '0.0'), ucr.get('version/patchlevel', '0'), ucr.get('version/erratalevel', '0'))


def _get_fqdn() -> str:
    ucr = _get_ucr()
    return '%(hostname)s.%(domainname)s' % ucr


class _HTTPType(type):
    """
    Metaclass for HTTP Error exceptions.
    Sub-classes of this meta class are automatically added to the :py:data:`HTTPError.codes` mapping.
    """

    def __init__(mcs, name, bases, dict):
        try:
            HTTPError.codes[mcs.code] = mcs
        except (NameError, AttributeError):
            pass
        type.__init__(mcs, name, bases, dict)


class ConnectionError(Exception):
    """
    Signal an error during connection setup.

    :param str msg: A message string.
    :param reason: The optional underlying exception.
    """

    def __init__(self, msg: str, reason: Exception | None = None) -> None:
        super().__init__(msg, reason)
        self.reason = reason


class HTTPError(Exception):
    """
    Base class for |HTTP| errors.
    A specialized sub-class if automatically instantiated based on the |HTTP| return code.

    :param request: The |HTTP| request.
    :param http.client.HTTPResponse response: The |HTTP| response.
    :param str hostname: The host name of the failed server.
    """

    __metaclass__ = _HTTPType
    codes: dict[int, type[HTTPError]] = {}
    """Specialized sub-classes for individual |HTTP| error codes."""

    @property
    def status(self) -> int:
        """
        Return the |HTTP| status code.

        :returns: the numerical status code.
        :rtype: int
        """
        return self.response.status

    @property
    def message(self) -> str:
        """
        Return the |HTTP| status message.

        :returns: the textual status message.
        :rtype: str
        """
        return self.response.message

    @property
    def result(self) -> str:
        """
        Return the |HTTP| result.

        :returns: the result data
        :rtype: str
        """
        return self.response.result

    def __new__(cls, request, response, hostname):
        err = cls.codes.get(response.status, cls)
        return super().__new__(err, request, response, hostname)  # type: ignore

    def __init__(self, request, response, hostname):
        self.request = request
        self.hostname = hostname
        self.response = response

    def __repr__(self):
        return f'<HTTPError {self}>'

    def __str__(self) -> str:
        traceback = ''
        data = self.response.data
        if self.status >= 500 and isinstance(self.response.data, dict) and isinstance(self.response.data.get('traceback'), str) and 'Traceback (most recent call last)' in self.response.data['traceback']:
            data = data.copy()
            traceback = '\n{}'.format(data.pop('traceback'))
        return f'{self.status} on {self.hostname} ({self.request.path}): {data}{traceback}'


class HTTPRedirect(HTTPError):
    """:py:data:`http.client.MULTIPLE_CHOICES` |HTTP|/1.1, :rfc:`2616`, Section 10.3.1"""

    code = 300


class MovedPermanently(HTTPRedirect):
    """:py:data:`http.client.MOVED_PERMANENTLY` |HTTP|/1.1, :rfc:`2616`, Section 10.3.2"""

    code = 301


class Found(HTTPRedirect):
    """:py:data:`http.client.FOUND` |HTTP|/1.1, :rfc:`2616`, Section 10.3.3"""

    code = 302


class SeeOther(HTTPRedirect):
    """:py:data:`http.client.SEE_OTHER` |HTTP|/1.1, :rfc:`2616`, Section 10.3.4"""

    code = 303


class NotModified(HTTPRedirect):
    """:py:data:`http.client.NOT_MODIFIED` |HTTP|/1.1, :rfc:`2616`, Section 10.3.5"""

    code = 304


class BadRequest(HTTPError):
    """:py:data:`http.client.BAD_REQUEST` |HTTP|/1.1, :rfc:`2616`, Section 10.4.1"""

    code = 400


class Unauthorized(HTTPError):
    """:py:data:`http.client.UNAUTHORIZED` |HTTP|/1.1, :rfc:`2616`, Section 10.4.2"""

    code = 401


class Forbidden(HTTPError):
    """:py:data:`http.client.UNAUTHORIZED` |HTTP|/1.1, :rfc:`2616`, Section 10.4.4"""

    code = 403


class NotFound(HTTPError):
    """:py:data:`http.client.NOT_FOUND` |HTTP|/1.1, :rfc:`2616`, Section 10.4.5"""

    code = 404


class MethodNotAllowed(HTTPError):
    """:py:data:`http.client.METHOD_NOT_ALLOWED` |HTTP|/1.1, :rfc:`2616`, Section 10.4.6"""

    code = 405


class NotAcceptable(HTTPError):
    """:py:data:`http.client.NOT_ACCEPTABLE` |HTTP|/1.1, :rfc:`2616`, Section 10.4.7"""

    code = 406


class UnprocessableEntity(HTTPError):
    """:py:data:`http.client.UNPROCESSABLE_ENTITY` WEBDAV, :rfc:`22518`, Section 10.3"""

    code = 422


class InternalServerError(HTTPError):
    """:py:data:`http.client.INTERNAL_SERVER_ERROR` |HTTP|/1.1, :rfc:`2616`, Section 10.5.1"""

    code = 500


class BadGateway(HTTPError):
    """:py:data:`http.client.BAD_GATEWAY` |HTTP|/1.1, :rfc:`2616`, Section 10.5.3"""

    code = 502


class ServiceUnavailable(HTTPError):
    """:py:data:`http.client.SERVICE_UNAVAILABLE` |HTTP|/1.1, :rfc:`2616`, Section 10.5.4"""

    code = 503


class Request:
    """
    The |HTTP| request.

    :param str method: `GET` / `POST` / `PUT` / `DELETE`
    :param str path: the relative path to `/univention/`.
    :param str data: either the raw request payload or some data which must be encoded by get_body()
    :param dict headers: a mapping of HTTP headers
    """

    def __init__(self, method: str, path: str, data: str | None = None, headers: dict[str, str] | None = None) -> None:
        self.method = method
        self.path = path
        self.data = data
        self.headers = headers or {}

    def get_body(self) -> bytes | str | None:
        """
        Return the request data.

        :returns: encodes data in JSON if Content-Type wants it
        :rtype: bytes
        """
        if self.headers.get('Content-Type', '').startswith('application/json'):
            return json.dumps(self.data).encode('ASCII')
        return self.data


class Response:
    """
    The |HTTP| response.

    :param int status: |HTTP| status code between 200 and 599.
    :param str reason: string with the reason phrase e.g. 'OK'
    :param bytes body: the raw response body
    :param list headers: the response headers as list of tuples
    :param http.client.HTTPResponse _response: The original |HTTP| response.
    """

    @property
    def result(self) -> Any:
        """
        Return `result` from |JSON| data.

        :returns: The `result`.
        """
        if isinstance(self.data, dict):
            return self.data.get('result')

    @property
    def message(self) -> Any:
        """
        Return `message` from |JSON| data.

        :returns: The `message`.
        """
        if isinstance(self.data, dict):
            return self.data.get('message')

    def __init__(self, status: int, reason: str, body: bytes, headers: list[tuple[str, str]], _response: http.client.HTTPResponse) -> None:
        self.status = status
        self.reason = reason
        self.body = body
        self.headers = headers
        self._response = _response
        self.data = self.decode_body()

    @overload
    def get_header(self, name: str) -> str | None:
        ...

    @overload
    def get_header(self, name: str, default: _T) -> str | _T:
        ...

    def get_header(self, name: str, default: _T | None = None) -> str | _T | None:
        """
        Return original |HTTP| response header.

        :param str name: |HTTP| respone header name, e.g. `Content-Type`.
        :param default: Default value of the header is not set. Defaults to `None`.
        :returns: The header value or `None`.
        :rtype: str or None
        """
        return self._response.getheader(name, default)

    def decode_body(self) -> bytes | dict:
        """
        Decode |HTTP| response and return |JSON| data as dictionary.

        :returns: |JSON| data is returned as a dictionary, all other as raw.
        :rtype: dict or str
        """
        data = self.body
        if self.get_header('Content-Type', '').startswith('application/json'):
            try:
                data = json.loads(data.decode('UTF-8'))
            except ValueError as exc:
                raise ConnectionError(f'Malformed response data: {data!r}', reason=exc)
        return data

    @classmethod
    def _from_httplib_response(cls, response: http.client.HTTPResponse) -> Response:
        """
        Create class instance from |HTTP| response.

        :param http.client.HTTPResponse response: The |HTTP| response.
        """
        data = response.read()
        return cls(response.status, response.reason, data, response.getheaders(), response)


class Client:
    """
    A client capable to speak with a |UMC| server.

    :param str hostname: The name of the host to connect. Defaults to the |FQDN| of the localhost.
    :param str username: A user name.
    :param str password: The password of the user.
    :param str language: The preferred language.
    :param float timeout: Set the default timeout in seconds (float) for new connections.
    :param bool automatic_reauthentication: Automatically re-authenticate and re-do requests if the authentication cookie expires.
    """

    ConnectionType = HTTPSConnection

    def __init__(self, hostname: str | None = None, username: str | None = None, password: str | None = None, language: str | None = None, timeout: float | None = None, automatic_reauthentication: bool = False, useragent: str | None = None) -> None:
        self.hostname = hostname or _get_fqdn()
        self._language = language or locale.getlocale()[0] or ''
        self._headers = {
            'Content-Type': 'application/json; charset=UTF-8',
            'Accept': 'application/json; q=1, text/html; q=0.5; */*; q=0.1',
            'Accept-Language': self._language.replace('_', '-'),
            'X-Requested-With': 'XMLHttpRequest',
            'User-Agent': useragent or _get_useragent(),
        }
        self._base_uri = '/univention/'
        self._timeout = timeout
        self._raise_errors = True
        self._automatic_reauthentication = automatic_reauthentication
        self.cookies: dict[str, str] = {}
        self.username = username or ''
        self.password = password or ''
        if username:
            self.authenticate(self.username, self.password)

    def authenticate(self, username: str, password: str) -> Response:
        """
        Authenticate against the host and preserves the
        cookie. Has to be done only once (but keep in mind that the
        session probably expires after 10 minutes of inactivity)

        :param str username: A user name.
        :param str password: The password of the user.
        """
        self.username = username
        self.password = password
        return self.umc_auth(username, password)

    def reauthenticate(self) -> Response:
        """Re-authenticate using the stored username and password."""
        return self.authenticate(self.username, self.password)

    def set_basic_http_authentication(self, username: str, password: str) -> None:
        """
        Setup authentication using |HTTP| Basic authentication.

        :param str username: A user name.
        :param str password: The password of the user.
        """
        self._headers['Authorization'] = 'Basic %s' % (base64.b64encode(b'%s:%s' % (username.encode('UTF-8'), password.encode('UTF-8'))).decode('ASCII'),)

    def authenticate_saml(self, username: str, password: str) -> None:
        """
        Setup authentication using |SAML|.

        :param str username: A user name.
        :param str password: The password of the user.

        .. warning::
                not implemented.
        """
        raise ConnectionError('SAML authentication currently not supported.')

    def authenticate_with_machine_account(self) -> None:
        """
        Setup authentication using the machine account.

        :raises ConnectionError: if :file:`/etc/machine.secret` cannot be read.
        """
        username = '%s$' % _get_ucr().get('hostname')
        try:
            with open('/etc/machine.secret') as machine_file:
                password = machine_file.readline().strip()
        except OSError as exc:
            raise ConnectionError('Could not read /etc/machine.secret', reason=exc)
        self.authenticate(username, password)

    def umc_command(self, path: str, options: dict | None = None, flavor: str | None = None, headers: dict | None = None) -> Response:
        """
        Perform generic |UMC| command.

        :param str path: The |URL| path of the command after the `command/` prefix.
        :param dict options: The argument for the |UMC| command.
        :param str flavor: Optional name of the |UMC| module flavor, e.g. `users/user` for |UDM| modules.
        :param dict headers: Optional |HTTP| headers.
        :returns: The |UMC| response.
        :rtype: Response
        """
        data = self.__build_data(options, flavor)
        return self.request('POST', f'command/{path}', data, headers)

    def umc_set(self, options: dict | None, headers: dict | None = None) -> Response:
        """
        Perform |UMC| `set` command.

        :param dict options: The argument for the |UMC| `set` command.
        :param dict headers: Optional |HTTP| headers.
        :returns: The |UMC| response.
        :rtype: Response
        """
        data = self.__build_data(options)
        return self.request('POST', 'set', data, headers)

    def umc_get(self, path: str, options: dict | None = None, headers: dict | None = None) -> Response:
        """
        Perform |UMC| `get` command.

        :param str path: The |URL| path of the command after the `get/` prefix.
        :param dict options: The argument for the |UMC| `get` command.
        :param dict headers: Optional |HTTP| headers.
        :returns: The |UMC| response.
        :rtype: Response
        """
        return self.request('POST', 'get/%s' % path, self.__build_data(options), headers)

    def umc_upload(self) -> None:
        """
        Perform |UMC| upload action.

        .. warning::
                not implemented.
        """
        raise NotImplementedError('File uploads currently need to be done manually.')

    def umc_auth(self, username: str, password: str, **data: str) -> Response:
        """
        Perform |UMC| authentication command.

        :param str username: A user name.
        :param str password: The password of the user.
        :param data: Additional argument for the |UMC| `auth` command.
        :returns: The |UMC| response.
        :rtype: Response
        """
        data = self.__build_data(dict({'username': username, 'password': password}, **data))
        return self.request('POST', 'auth', data)

    def umc_logout(self) -> Response:
        """
        Perform |UMC| logout action.

        :returns: The |UMC| response.
        :rtype: Response
        """
        try:
            return self.request('GET', 'logout')
        except (SeeOther, Found, MovedPermanently) as exc:
            return exc.response

    def request(self, method: str, path: str, data: Any = None, headers: dict | None = None) -> Response:
        """
        Send request to |UMC| server handling re-authentication.

        :param str method: The |HTTP| method for the request.
        :param str path: The |URL| of the request.
        :param data: The message body.
        :param dict headers: Optional |HTTP| headers.
        :returns: The |UMC| response.
        :rtype: Response
        :raises Unauthorized: if the session expired and re-authentication was disabled.
        """
        request = Request(method, path, data, headers)
        try:
            return self.send(request)
        except Unauthorized:
            if not self._automatic_reauthentication:
                raise
            self.reauthenticate()
            return self.send(request)

    def send(self, request: Request) -> Response:
        """
        Low-level function to send request to |UMC| server.

        :param Request request: A |UMC| request.
        :returns: The |UMC| response.
        :rtype: Response
        :raises ConnectionError: if the request cannot be send.
        :raises HTTPError: if an |UMC| error occurs.
        """
        cookie = '; '.join(['='.join(x) for x in self.cookies.items()])
        request.headers = dict(self._headers, Cookie=cookie, **request.headers)
        if 'UMCSessionId' in self.cookies:
            request.headers['X-XSRF-Protection'] = self.cookies['UMCSessionId']
        try:
            http_response = self.__request(request)
        except (HTTPException, OSError, ssl.CertificateError) as exc:
            raise ConnectionError('Could not send request.', reason=exc)
        self._handle_cookies(http_response)
        response = Response._from_httplib_response(http_response)
        if self._raise_errors and response.status > 299:
            raise HTTPError(request, response, self.hostname)
        return response

    def _handle_cookies(self, response: http.client.HTTPResponse) -> None:
        """
        Parse cookies from |HTTP| response and store for next request.

        :param http.client.HTTPResponse response: The |HTTP| response.
        """
        # FIXME: this cookie handling doesn't respect path, domain and expiry
        cookies: SimpleCookie = SimpleCookie()
        cookies.load(response.getheader('set-cookie', ''))
        self.cookies.update({cookie.key: cookie.value for cookie in cookies.values()})

    def __request(self, request: Request) -> http.client.HTTPResponse:
        """
        Perform a request to the |UMC| server and return its response.

        :param Request request: The |UMC| request.
        :returns: The |HTTP| response.
        :rtype: http.client.HTTPResponse
        """
        uri = f'{self._base_uri}{request.path}'
        con = self._get_connection()
        con.request(request.method, uri, request.get_body(), headers=request.headers)
        response = con.getresponse()
        if response.status == 404:
            if self._base_uri == '/univention/':
                # UCS 4.1
                self._base_uri = '/univention-management-console/'
                return self.__request(request)
            elif self._base_uri == '/univention-management-console/':
                # UCS 3.X
                self._base_uri = '/umcp/'
                return self.__request(request)
        return response

    def _get_connection(self) -> HTTPSConnection:
        """
        Creates a new connection to the host.

        :returns: A new connection to the stores host.
        :rtype: HTTPSConnection
        """
        # once keep-alive is over, the socket closes
        #   so create a new connection on every request
        return self.ConnectionType(self.hostname, timeout=self._timeout)

    def __build_data(self, data: dict[str, Any] | None, flavor: str | None = None) -> dict[str, Any]:
        """
        Create a dictionary as expected by the |UMC| Server.

        :param dict data: The argument for the |UMC| command.
        :param str flavor: Optional name of the |UMC| module flavor, e.g. `users/user` for |UDM| modules.
        :returns: A dictionary suitable for sending to the |UMC| server.
        :rtype: dict
        """
        data = {'options': data if data is not None else {}}
        if flavor:
            data['flavor'] = flavor
        return data
