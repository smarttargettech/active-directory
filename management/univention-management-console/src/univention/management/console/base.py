#!/usr/bin/python3
#
# Univention Management Console
#  Base class for UMC 2.0 command handlers
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
"""
Python API for UMC modules
==========================

The Python API for UMC modules primary consists of one base class that
must be implemented. As an addition the Python API provides some helper
functions and classes:

* exception classes
* translation support
* logging functions
* UCR access

The XML file defining the UMC module specifies functions for the
commands provided by the module. These functions must be implemented as
methods of a class named *Instance* that inherits :class:`.Base`.

The following Python code example matches the definition in the previous section::

    from univention.management.console import Translation
    from univention.management.console.config import ucr
    from univention.management.console.modules import Base
    from univention.management.console.modules.decorators import sanitize
    from univention.management.console.modules.sanitizers import IntegerSanitizer
    from univention.management.console.log import MODULE

    _ = Translation('univention-management-console-modules-udm').translate

    class Instance(Base):

        @sanitize(end=IntegerSanitizer(minimum=0),)
        def query(self, request):
            end = request.options['end']
            result = list(range(end))
            self.finished(request.id, result)

Each command methods has one parameter that contains the HTTP request of
type
:class:`~univention.management.console.message.Request`. Such
an object has the following properties:

*id*
    is the unique identifier of the request

*options*
    contains the arguments for the command. For most commands it is a
    dictionary.

*flavor*
    is the name of the flavor that was used to invoke the command. This
    might be *None*

* *username*: The username of the owner of this session
* *password*: The password of the user
* *auth_type*: The authentication method which was used to authenticate this user

The *query* method in the example above shows how to retrieve the
command parameters and what to do to send the result back to the
client. Important is that returning a value in a command function does
not send anything back to the client. Therefore the function *finished*
must be invoked. The first parameter is the identifier of the request
that will be answered and the second parameter the data structure
containing the result. As the result is converted to JSON it must just
contain data types that can be converted.

The base class for modules provides some methods that
could be useful when writing UMC modules:

Methods
* *init*: Is invoked after the module process has been initialised. At that moment, the settings, like locale and username and password are available.

"""


import locale
import re
import sys
import traceback
from urllib.parse import urlparse

import ldap

import univention.admin.uexceptions as udm_errors
from univention.lib.i18n import I18N_Error, Locale, Translation
from univention.management.console.config import ucr
from univention.management.console.error import (
    LDAP_ConnectionFailed, LDAP_ServerDown, NotAcceptable, UMC_Error, Unauthorized,
)
from univention.management.console.ldap import reset_cache as reset_ldap_connection_cache
from univention.management.console.log import CORE, MODULE
from univention.management.console.message import Response


_MIMETYPE_JSON = 'application/json'
_MODULE_ERR = 590  # FIXME: HTTP violation
_MODULE_ERR_COMMAND_FAILED = 591  # FIXME: HTTP violation


class Base(Translation):
    """The base class for UMC modules"""

    def __init__(self, domain='univention-management-console'):
        super().__init__(domain)
        self.__current_language = None
        self._current_request = None
        self.__requests = {}
        self._accepted_language = None

    def update_language(self, locales):
        for _locale in locales:
            language = None
            try:
                CORE.info("Setting locale %r" % (_locale,))
                _locale = Locale(_locale)
                language = '%s-%s' % (_locale.language, _locale.territory) if _locale.territory else '%s' % (_locale.language,)
                if language != self.__current_language:
                    self.set_locale(str(_locale))
                self.__current_language = language
                return
            except (locale.Error, I18N_Error) as exc:
                if language in ('en', 'en-US'):  # the system is missing english locale
                    self.set_locale('C')
                    if not self.__current_language:  # only log once!
                        CORE.error('Missing "en_US.UTF-8:UTF-8" in UCR variable "locale"')
                    self.__current_language = language
                    return
                CORE.warn("Locale %r is not available: %s" % (str(_locale), exc))
        CORE.warn('Could not set language. Resetting locale.')
        self.set_locale('C')
        self.__current_language = None
        raise NotAcceptable(self._('Specified locale is not available'))

    def set_locale(self, _locale):
        self.set_language(_locale)
        _locale = str(Locale(_locale))
        locale.setlocale(locale.LC_MESSAGES, _locale)
        locale.setlocale(locale.LC_CTYPE, _locale)

    @property
    def username(self):
        """
        .. deprecated::
                use request.username instead!
        """
        return self._current_request.username

    @property
    def _username(self):
        """
        .. deprecated::
                use request.username instead!
        """
        return self._current_request.username

    @property
    def user_dn(self):
        """
        .. deprecated::
                use request.user_dn instead!
        """
        return self._current_request.user_dn

    @property
    def _user_dn(self):
        """
        .. deprecated::
                use request.user_dn instead!
        """
        return self._current_request.user_dn

    @property
    def password(self):
        """
        .. deprecated::
                use request.password instead!
        """
        return self._current_request.password

    @property
    def _password(self):
        return self._current_request.password

    @property
    def auth_type(self):
        """
        .. deprecated::
                use request.auth_type instead!
        """
        return self._current_request.auth_type

    @property
    def tornado_routes(self):
        return []

    def prepare(self, request):
        """this function is invoked after the module process started."""
        self.init()

    def init(self):
        """this function is invoked after the module process started."""

    def destroy(self):
        """
        this function is invoked before the module process is
        exiting.
        """

    def execute(self, method, request, *args, **kwargs):
        self.__requests[request.id] = (request, method)
        self._current_request = request

        try:
            function = getattr(self, method)
        except AttributeError:
            message = self._('Method %(method)r (%(path)r) in %(module)r does not exist.\n\n%(traceback)s') % {'method': method, 'path': request.arguments, 'module': self.__class__.__module__, 'traceback': traceback.format_exc()}
            self.finished(request.id, None, message=message, status=500)
            return

        try:
            self._parse_accept_language(request)
            if ucr.is_false('umc/server/disable-security-restrictions', True):
                self.security_checks(request, function)
            function.__func__(self, request, *args, **kwargs)
        except (KeyboardInterrupt, SystemExit):
            self.finished(request.id, None, self._('The UMC service is currently shutting down or restarting. Please retry soon.'), status=503)
            raise
        except BaseException:
            self.__error_handling(request, method, *sys.exc_info())

    def _parse_accept_language(self, request):
        """Parses language tokens from Accept-Language, transforms it into locale and set the language."""
        if request.headers.get('X-Requested-With'.title(), '').lower() != 'XMLHTTPRequest'.lower():
            return  # don't change the language if Accept-Language header contains the value of the browser and not those we set in Javascript

        accepted_locales = re.split(r'\s*,\s*', request.headers.get('Accept-Language', ''))
        try:
            accepted_locales.remove('')
        except ValueError:
            pass
        if accepted_locales and accepted_locales != self._accepted_language:
            self._accepted_language = accepted_locales
            self.update_language(re.sub(';.*', '', lang.replace('-', '_')) for lang in accepted_locales)

    def security_checks(self, request, function):
        if request.http_method not in ('POST', 'PUT', 'DELETE') and not getattr(function, 'allow_get', False):
            status = 405 if request.http_method in ('GET', 'HEAD') else 501
            raise UMC_Error(self._('The requested HTTP method is not allowed on this resource.'), status=status, headers={'Allow': 'POST'})

        if getattr(function, 'xsrf_protection', True) and request.cookies.get('UMCSessionId') != request.headers.get('X-Xsrf-Protection'.title()):
            raise UMC_Error(self._('Cross Site Request Forgery attack detected. Please provide the "UMCSessionId" cookie value as HTTP request header "X-Xsrf-Protection".'), status=403)

        if getattr(function, 'referer_protection', True) and request.headers.get('Referer') and not urlparse(request.headers['Referer']).path.startswith('/univention/'):
            # FIXME: we must also check the netloc/hostname/IP
            raise UMC_Error(self._('The "Referer" HTTP header must start with "/univention/".'), status=503)

        content_type = request.headers.get('Content-Type', '')
        allowed_content_types = ('application/json', 'application/x-www-form-urlencoded', 'multipart/form-data')

        if content_type and not re.match(r'^(%s)($|\s*;)' % '|'.join(re.escape(x) for x in allowed_content_types), content_type):
            raise UMC_Error(self._('The requested Content-Type is not acceptable. Please use one of %s.' % (', '.join(allowed_content_types))), status=406)

    def thread_finished_callback(self, thread, result, request):
        if not isinstance(result, BaseException):
            self.finished(request.id, result)
            return
        method = '%s: %s' % (thread.name, ' '.join(request.arguments))
        self.__error_handling(request, method, thread.exc_info[0], thread.exc_info[1], thread.trace)

    def error_handling(self, etype, exc, etraceback):
        """
        Translate generic UDM exceptions back to LDAP exceptions.

        :param etype: The exception class.
        :param exc: The exception instance.
        :param etraceback: The exception traceback instance; may be None.
        """
        if (isinstance(exc, udm_errors.ldapError) and isinstance(getattr(exc, 'original_exception', None), ldap.LDAPError)) or isinstance(exc, ldap.LDAPError):
            # After an exception the ReconnectLDAPObject instance can be in a state without a bind. Which can result
            # in a "ldapError: Insufficient access" exception, because the connection is anonymous. Prevent the usage
            # of a ReconnectLDAPObject instance after an exception by clearing the connection cache.
            # Bug #46089
            reset_ldap_connection_cache()
        if isinstance(exc, udm_errors.ldapError) and isinstance(getattr(exc, 'original_exception', None), ldap.SERVER_DOWN):
            exc = exc.original_exception
        if isinstance(exc, udm_errors.ldapError) and isinstance(getattr(exc, 'original_exception', None), ldap.INVALID_CREDENTIALS):
            exc = exc.original_exception
        if isinstance(exc, ldap.SERVER_DOWN):
            raise LDAP_ServerDown()
        if isinstance(exc, ldap.CONNECT_ERROR):
            raise LDAP_ConnectionFailed(exc)
        if isinstance(exc, ldap.INVALID_CREDENTIALS):
            # Ensure the connection cache is empty to prevent the use of expired saml messages
            # Bug #44621
            reset_ldap_connection_cache()
            CORE.error('Failed to open LDAP connection: %s' % (exc))
            raise Unauthorized

    def __error_handling(self, request, method, etype, exc, etraceback):
        """
        Handle UMC exception.

        As requests are processes in a separate thread, any exception only contains the traceback relative to the thread.
        To make them more usable we want to combine them with the calling part to get a complete stack trace.

        :param request: The original UMC request.
        :param method: The failed UMC command.
        :param etype: The exception class.
        :param exc: The exception instance.
        :param etraceback: The exception traceback instance; may be None.
        """
        message = ''
        result = None
        headers = None
        error = None
        trace = etraceback or []
        if isinstance(etraceback, list):
            etraceback = None
        try:
            try:
                self.error_handling(etype, exc, etraceback)
            except Exception:
                raise
            else:
                raise exc.with_traceback(etraceback)
        except UMC_Error as exc:
            status = exc.status
            result = exc.result
            headers = exc.headers
            reason = exc.reason
            message = str(exc)
            if not exc.traceback and exc.include_traceback:
                exc.traceback = traceback.format_exc()
                if isinstance(exc.traceback, bytes):   # Python 2
                    exc.traceback = exc.traceback.decode('utf-8', 'replace')
            error = {
                'command': method,
                'traceback': exc.traceback,
            }
        except Exception:
            status = _MODULE_ERR_COMMAND_FAILED
            reason = None
            if etraceback is None:  # Bug #47114: thread.exc_info doesn't contain a traceback object anymore
                tb_str = ''.join(['Traceback (most recent call last):\n', *trace, *traceback.format_exception_only(*sys.exc_info()[:2])])
            else:
                tb_str = traceback.format_exc()
            if isinstance(tb_str, bytes):  # Python 2
                tb_str = tb_str.decode('utf-8', 'replace')
            error = {
                'command': ('%s %s' % (' '.join(request.arguments), '(%s)' % (request.flavor,) if request.flavor else '')).strip(),
                'traceback': tb_str,
            }
            if isinstance(error['command'], bytes):  # Python 2
                error['command'] = error['command'].decode('utf-8', 'replace')
            message = self._('Internal server error during "%(command)s".') % error
        MODULE.error('%s: %s', message, error['traceback'])
        self.finished(request.id, result, message, status=status, headers=headers, error=error, reason=reason)

    def default_response_headers(self):
        headers = {
            'Vary': 'Content-Language',
        }
        if self.__current_language:
            headers['Content-Language'] = self.__current_language
        return headers

    def get_user_ldap_connection(self, no_cache=False, **kwargs):
        """
        .. deprecated::
                use request.get_user_ldap_connection() instead!
        """
        return self._current_request.get_user_ldap_connection(no_cache=False, **kwargs)

    def bind_user_connection(self, lo):
        """
        .. deprecated::
                use request.bind_user_connection() instead!
        """
        return self._current_request.bind_user_connection(lo)

    def require_password(self):
        """
        .. deprecated::
                use request.require_password() instead!
        """
        return self._current_request.require_password()

    def finished(self, id, response, message=None, success=True, status=None, mimetype=None, headers=None, error=None, reason=None):
        """Should be invoked by module to finish the processing of a request. 'id' is the request command identifier"""
        if id not in self.__requests:
            return
        request, _method = self.__requests[id]

        if not isinstance(response, Response):
            res = Response(request)

            if mimetype and mimetype != _MIMETYPE_JSON:
                res.mimetype = mimetype
                res.body = response
            else:
                res.result = response
                res.message = message
                res.headers = dict(self.default_response_headers(), **headers or {})
                res.error = error
                res.reason = reason
        else:
            res = response

        if not res.status:
            if status is not None:
                res.status = status
            else:
                res.status = 200 if success else _MODULE_ERR

        self.result(res)

    def result(self, response):
        try:
            request, _method = self.__requests.pop(response.id)
        except KeyError:
            return
        request._request_handler.reply(response)

    def _is_active(self, request):
        return request.id in self.__requests
