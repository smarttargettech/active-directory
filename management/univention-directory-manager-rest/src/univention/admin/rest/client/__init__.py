#!/usr/bin/python3
#
# Univention Directory Manager
#  REST API client
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2019-2025 Univention GmbH
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
Sample Client for the UDM REST API.

>>> from univention.admin.rest.client import UDM
>>> uri = 'http://localhost/univention/udm/'
>>> udm = UDM.http(uri, 'Administrator', 'univention')
>>> module = udm.get('users/user')
>>> print('Found {}'.format(module))
>>> obj = next(module.search())
>>> if obj:
>>>     obj = obj.open()
>>> print('Object {}'.format(obj))
"""

from __future__ import annotations

import copy
import sys
import time
from typing import TYPE_CHECKING, Any, Self

import requests
import uritemplate


if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

if sys.version_info.major > 2:
    import http.client
    http.client._MAXHEADERS = 1000  # type: ignore
else:
    import httplib
    httplib._MAXHEADERS = 1000


class HTTPError(Exception):

    def __init__(self, code: int, message: str, response: requests.Response | None, error_details: dict | None = None) -> None:
        self.code = code
        self.response = response
        self.error_details = error_details
        super().__init__(message)


class BadRequest(HTTPError):
    pass


class Unauthorized(HTTPError):
    pass


class Forbidden(HTTPError):
    pass


class NotFound(HTTPError):
    pass


class PreconditionFailed(HTTPError):
    pass


class UnprocessableEntity(HTTPError):
    pass


class ServerError(HTTPError):
    pass


class ServiceUnavailable(HTTPError):
    pass


class ConnectionError(Exception):
    pass


class UnexpectedResponse(ConnectionError):
    pass


class _NoRelation(Exception):
    pass


class Response:  # noqa: B903

    def __init__(self, response: requests.Response, data: Any, uri: str) -> None:
        self.response = response
        self.data = data
        self.uri = uri


class Session:

    def __init__(self, credentials: UDM, language: str = 'en-US', reconnect: bool = True, user_agent: str = 'univention.lib/1.0', enable_caching: bool = False) -> None:
        self.language = language
        self.credentials = credentials
        self.reconnect = reconnect
        self.user_agent = user_agent
        self.enable_caching = enable_caching
        self.default_headers = {
            'Accept': 'application/hal+json; q=1, application/json; q=0.9; text/html; q=0.2, */*; q=0.1',
            'Accept-Language': self.language,
            'User-Agent': self.user_agent,
        }
        self.session = self.create_session()

    def create_session(self) -> requests.Session:
        sess = requests.session()
        if self.credentials.bearer_token:
            sess.headers['Authorization'] = 'Bearer %s' % (self.credentials.bearer_token,)
        else:
            sess.auth = (self.credentials.username, self.credentials.password)
        if not self.enable_caching:
            return sess
        try:
            from cachecontrol import CacheControl
        except ImportError:
            pass
        else:
            sess = CacheControl(sess)
        return sess

    def get_method(self, method: str) -> Callable[..., requests.Response]:
        sess = self.session
        return {
            'GET': sess.get,
            'POST': sess.post,
            'PUT': sess.put,
            'DELETE': sess.delete,
            'PATCH': sess.patch,
            'OPTIONS': sess.options,
        }.get(method.upper(), sess.get)

    def request(self, method: str, uri: str, data: dict | None = None, expect_json: bool = False, **headers: str) -> Any:
        return self.make_request(method, uri, data, expect_json=expect_json, **headers).data  # type: ignore # <https://github.com/python/mypy/issues/10008>

    def make_request(self, method: str, uri: str, data: dict | None = None, expect_json: bool = False, allow_redirects: bool = True, custom_redirect_handling: bool = False, **headers: str) -> Response:
        if method in ('GET', 'HEAD'):
            params = data
            json = None
        else:
            params = None
            json = data

        def doit() -> Response:
            try:
                response = self.get_method(method)(uri, params=params, json=json, headers=dict(self.default_headers, **headers), allow_redirects=allow_redirects)
            except requests.exceptions.ConnectionError as exc:
                raise ConnectionError(exc)
            if custom_redirect_handling:
                response = self._follow_redirection(response)
            data = self.eval_response(response, expect_json=expect_json)
            return Response(response, data, uri)

        for _i in range(5):
            try:
                return doit()
            except ServiceUnavailable as exc:  # TODO: same for ConnectionError? python-request does it itself.
                if not self.reconnect:
                    raise
                try:
                    assert exc.response is not None
                    retry_after = min(5, int(exc.response.headers.get('Retry-After', 1)))
                except ValueError:
                    retry_after = 1
                time.sleep(retry_after)

        return doit()

    def _follow_redirection(self, response: Response) -> Response:
        location = response.headers.get('Location')
        # python-requests doesn't follow redirects for 202
        if location and response.status_code in (201, 202):
            response = self.make_request('GET', location, allow_redirects=False).response

        # prevent allow_redirects because it does not wait Retry-After time causing a break up after 30 fast redirections
        while 300 <= response.status_code <= 399 and 'Location' in response.headers:
            location = response.headers['Location']
            if response.headers.get('Retry-After', '').isdigit():
                time.sleep(min(30, max(0, int(response.headers['Retry-After']))))
            response = self.make_request(self._select_method(response), location, allow_redirects=False).response

        return response

    def _select_method(self, response: Response) -> str:
        if response.status_code in (300, 301, 303) and response.request.method != 'HEAD':
            return 'GET'
        return response.request.method

    def eval_response(self, response: requests.Response, expect_json: bool = False) -> Any:
        if response.status_code >= 399:
            msg = f'{response.request.method} {response.url}: {response.status_code}'
            error_details = None
            try:
                json = response.json()
            except ValueError:
                pass
            else:
                if isinstance(json, dict):
                    error_details = json.get('error', {})
                    try:
                        error_details['error'] = list(self.resolve_relations(json, 'udm:error'))
                    except _NoRelation:
                        pass
                    if error_details:
                        server_message = error_details.get('message')
                        # traceback = error_details.get('traceback')
                        if server_message:
                            msg += f'\n{server_message}'
            errors = {400: BadRequest, 404: NotFound, 403: Forbidden, 401: Unauthorized, 412: PreconditionFailed, 422: UnprocessableEntity, 500: ServerError, 503: ServiceUnavailable}
            cls = HTTPError
            cls = errors.get(response.status_code, cls)
            raise cls(response.status_code, msg, response, error_details=error_details)
        if response.headers.get('Content-Type') in ('application/json', 'application/hal+json'):
            return response.json()
        elif expect_json:
            raise UnexpectedResponse(response.text)
        if response.status_code == 204:
            return {}
        return response.text

    def get_relations(self, entry: dict, relation: str, name: str | None = None, template: dict[str, Any] | None = None) -> Iterator[dict[str, str]]:
        links = copy.deepcopy(entry.get('_links', {}))
        links = links.get(relation, [None])
        links = links if links and isinstance(links, list) else [links]
        links = [link for link in links if isinstance(link, dict) and (not name or link.get('name') == name)]
        for link in sorted(links, key=lambda x: not x.get('templated', False) if template else x.get('templated', False)):
            if link.get('deprecation'):
                pass  # TODO: log warning
            if link.get('templated'):
                link['href'] = uritemplate.expand(link['href'], template)
            yield link

    def get_relation(self, entry: dict, relation: str, name: str | None = None, template: dict[str, Any] | None = None) -> dict[str, str]:
        try:
            return next(self.get_relations(entry, relation, name, template))
        except StopIteration:
            raise _NoRelation(relation)

    def resolve_relations(self, entry: dict, relation: str, name: str | None = None, template: dict[str, Any] | None = None) -> Iterator[Any]:
        embedded = entry.get('_embedded', {})
        if isinstance(embedded, dict) and relation in embedded:
            yield from embedded[relation]
            return

        for rel in self.get_relations(entry, relation, name, template):
            yield self.make_request('GET', rel['href']).data

    def resolve_relation(self, entry: dict, relation: str, name: str | None = None, template: dict[str, Any] | None = None) -> Any:
        try:
            return next(self.resolve_relations(entry, relation, name, template))
        except StopIteration:
            raise _NoRelation(relation)


class Client:  # noqa: B903

    def __init__(self, client: Session) -> None:
        self.client = client


class UDM(Client):

    @classmethod
    def http(cls, uri: str, username: str, password: str) -> Self:
        return cls(uri, username, password)

    @classmethod
    def bearer(cls, uri: str, bearer_token: str) -> Self:
        return cls(uri, None, None, bearer_token=bearer_token)

    def __init__(self, uri: str, username: str, password: str, *args: Any, **kwargs: Any) -> None:
        self.uri = uri
        self.username = username
        self.password = password
        self.bearer_token = kwargs.pop('bearer_token', None)
        self._api_version: str | None = None
        self.entry: Any = None
        super().__init__(Session(self, *args, **kwargs))

    def load(self) -> None:
        # FIXME: use HTTP caching instead of memory caching
        if self.entry is None:
            self.reload()

    def reload(self) -> None:
        self.entry = self.client.request('GET', self.uri, expect_json=True)

    def get_ldap_base(self) -> str | None:
        self.load()
        return Object.from_data(self, self.client.resolve_relation(self.entry, 'udm:ldap-base')).dn

    def modules(self, name: str | None = None) -> Iterator[Module]:
        self.load()
        for module in self.client.resolve_relations(self.entry, 'udm:object-modules'):
            for module_info in self.client.get_relations(module, 'udm:object-types', name):
                yield Module(self, module_info['href'], module_info['name'], module_info['title'])

    def version(self, api_version: str) -> Self:
        self._api_version = api_version
        return self

    def obj_by_dn(self, dn: str) -> Object:
        self.load()
        return Object.from_data(self, self.client.resolve_relation(self.entry, 'udm:object/get-by-dn', template={'dn': dn}))

    def obj_by_uuid(self, uuid: str) -> Object:
        self.load()
        return Object.from_data(self, self.client.resolve_relation(self.entry, 'udm:object/get-by-uuid', template={'uuid': uuid}))

    def get(self, name: str) -> Module | None:
        for module in self.modules(name):
            return module

        return None

    def get_object(self, object_type: str, dn: str) -> Object | None:
        mod = self.get(object_type)
        assert mod
        obj = mod.get(dn)
        return obj

    def __repr__(self) -> str:
        return f'UDM(uri={self.uri!r}, username={self.username!r}, password=***)'


class Module(Client):

    def __init__(self, udm: UDM, uri: str, name: str, title: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(udm.client, *args, **kwargs)
        self.udm = udm
        self.uri = uri
        self.username = udm.username
        self.password = udm.password
        self.name = name
        self.title = title
        self.relations: dict = {}

    def load_relations(self) -> None:
        if self.relations:
            return
        self.relations = self.client.request('GET', self.uri)

    def __repr__(self) -> str:
        return f'Module(uri={self.uri!r}, name={self.name!r})'

    def new(self, position: str | None = None, superordinate: str | None = None, template: dict[str, Any] | None = None) -> Object:
        self.load_relations()
        data = {'position': position, 'superordinate': superordinate, 'template': template}
        resp = self.client.resolve_relation(self.relations, 'create-form', template=data)
        return Object.from_data(self.udm, resp)

    def get(self, dn: str, properties: list[str] | None = None) -> Object | None:
        # TODO: use a link relation instead of a search
        for obj in self._search_closed(position=dn, scope='base', properties=properties):
            return obj.open()
        raise NotFound(404, 'Wrong object type!?', None)  # FIXME: object exists but is of different module. should be fixed on the server.

    def get_by_entry_uuid(self, uuid: str, properties: list[str] | None = None) -> Object | None:
        # TODO: use a link relation instead of a search
        # return self.udm.get_by_uuid(uuid)
        for obj in self._search_closed(filter={'entryUUID': uuid}, scope='base', properties=properties):
            return obj.open()
        raise NotFound(404, 'Wrong object type!?', None)  # FIXME: object exists but is of different module. should be fixed on the server.

    def get_by_id(self, dn: str, properties: list[str] | None = None) -> Object | None:
        # TODO: Needed?
        raise NotImplementedError()

    def search(self, filter: dict[str, str] | str | bytes | None = None, position: str | None = None, scope: str | None = 'sub', hidden: bool = False, superordinate: str | None = None, opened: bool = False, properties: list[str] | None = None) -> Iterator[Any]:
        if opened:
            return self._search_opened(filter, position, scope, hidden, superordinate, properties)
        else:
            return self._search_closed(filter, position, scope, hidden, superordinate, properties)

    def _search_opened(self, filter: dict[str, str] | str | bytes | None = None, position: str | None = None, scope: str | None = 'sub', hidden: bool = False, superordinate: str | None = None, properties: list[str] | None = None) -> Iterator[Object]:
        for obj in self._search(filter, position, scope, hidden, superordinate, True, properties):
            yield Object.from_data(self.udm, obj)  # NOTE: this is missing last-modified, therefore no conditional request is done on modification!

    def _search_closed(self, filter: dict[str, str] | str | bytes | None = None, position: str | None = None, scope: str | None = 'sub', hidden: bool = False, superordinate: str | None = None, properties: list[str] | None = None) -> Iterator[ShallowObject]:
        for obj in self._search(filter, position, scope, hidden, superordinate, False, properties):
            objself = self.client.get_relation(obj, 'self')
            uri = objself['href']
            dn = objself['name']
            yield ShallowObject(self.udm, dn, uri)

    def _search(self, filter: dict[str, str] | str | bytes | None = None, position: str | None = None, scope: str | None = 'sub', hidden: bool = False, superordinate: str | None = None, opened: bool = False, properties: list[str] | None = None) -> Iterator[Any]:
        data = {
            'position': position,
            'scope': scope,
            'hidden': '1' if hidden else '0',
        }
        if isinstance(filter, dict):
            for prop, val in filter.items():
                data.setdefault('query', {})[f'query[{prop}]'] = val
        elif isinstance(filter, str):
            data['filter'] = filter
        if superordinate:
            data['superordinate'] = superordinate
        if not opened:
            data['opened'] = '0'
            data['properties'] = ['dn']
        if properties:
            data['properties'] = properties
        self.load_relations()
        entries = self.client.resolve_relation(self.relations, 'search', template=data)
        yield from self.client.resolve_relations(entries, 'udm:object')

    def get_layout(self) -> Any | None:
        self.load_relations()
        return self.udm.client.resolve_relation(self.relations, 'udm:layout').get('layout')

    def get_properties(self) -> Any | None:
        self.load_relations()
        return self.udm.client.resolve_relation(self.relations, 'udm:properties').get('properties')

    def get_property_choices(self, property: str) -> Any | None:
        self.load_relations()
        relations = self.udm.client.resolve_relation(self.relations, 'udm:properties')
        return self.udm.client.resolve_relation(relations, 'udm:property-choices', name=property).get('choices')

    def policy_result(self, policy_module: str, position: str, policy: str | None = None) -> dict:
        self.load_relations()
        policy_result = self.udm.client.resolve_relation(self.relations, 'udm:policy-result', name=policy_module, template={'position': position, 'policy': policy})
        policy_result.pop('_links', None)
        policy_result.pop('_embedded', None)
        return policy_result

    def get_report_types(self) -> list[str]:
        self.load_relations()
        return [x['name'] for x in self.udm.client.get_relations(self.relations, 'udm:report', template={'dn': ''}) if x.get('name')]

    def create_report(self, report_type: str, object_dns: list[str]) -> Any:
        self.load_relations()
        return self.udm.client.resolve_relation(self.relations, 'udm:report', name=report_type, template={'dn': object_dns})


class ShallowObject(Client):

    def __init__(self, udm: UDM, dn: str | None, uri: str, *args: Any, **kwargs: Any) -> None:
        super().__init__(udm.client, *args, **kwargs)
        self.dn = dn
        self.udm = udm
        self.uri = uri

    def open(self) -> Object:
        return Object.from_response(self.udm, self.client.make_request('GET', self.uri))

    def __repr__(self) -> str:
        return f'ShallowObject(dn={self.dn!r})'


class References:

    def __init__(self, obj: Object | None = None) -> None:
        self.obj = obj
        self.udm = self.obj.udm if self.obj is not None else None

    def __getitem__(self, item: str) -> list[ShallowObject]:
        assert self.obj
        assert self.udm
        return [
            ShallowObject(self.obj.udm, x['name'], x['href'])
            for x in self.udm.client.get_relations(self.obj.hal, f'udm:object/property/reference/{item}')
        ]

    def __getattribute__(self, key):
        try:
            return super().__getattribute__(key)
        except AttributeError:
            return self[key]

    def __get__(self, obj: Any, cls: type | None = None) -> References:
        return type(self)(obj)


class Object(Client):

    objects = References()

    @property
    def module(self):
        # FIXME: use "type" relation link
        # object_type = self.udm.get_relation(self.hal, 'type')['href']
        return self.udm.get(self.object_type)

    @property
    def object_type(self) -> str:
        return self.representation['objectType']

    @property
    def dn(self) -> str | None:
        return self.representation.get('dn')

    @property
    def properties(self):
        return self.representation['properties']

    @property
    def options(self) -> dict:
        return self.representation.get('options', {})

    @property
    def policies(self) -> dict:
        return self.representation.get('policies', {})

    @property
    def superordinate(self) -> str | None:
        return self.representation.get('superordinate')

    @superordinate.setter
    def superordinate(self, superordinate: str) -> None:
        self.representation['superordinate'] = superordinate

    @property
    def position(self) -> str | None:
        return self.representation.get('position')

    @position.setter
    def position(self, position: str) -> None:
        self.representation['position'] = position

    @property
    def uri(self) -> str | None:
        try:
            uri = self.client.get_relation(self.hal, 'self')
        except _NoRelation:
            uri = None
        if uri:
            return uri['href']
        return self.representation.get('uri')

    @classmethod
    def from_response(cls, udm: UDM, response: Response) -> Object:
        return cls.from_data(udm, response.data, response.response.headers)

    @classmethod
    def from_data(cls, udm: UDM, entry: dict, headers: Mapping[str, str] | None = None) -> Object:
        headers = headers or {}
        return cls(udm, entry, etag=headers.get('Etag'), last_modified=headers.get('Last-Modified'))

    def __init__(self, udm: UDM, representation: dict, etag: str | None = None, last_modified: str | None = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(udm.client, *args, **kwargs)
        self.udm = udm
        self.representation = representation
        self.hal = {
            '_links': representation.pop('_links', {}),
            '_embedded': representation.pop('_embedded', {}),
        }
        self.etag = etag
        self.last_modified = last_modified

    def __repr__(self) -> str:
        return f'Object(module={self.object_type!r}, dn={self.dn!r}, uri={self.uri!r})'

    def reload(self) -> None:
        uri = self.client.get_relation(self.hal, 'self')
        if uri:
            obj = ShallowObject(self.udm, self.dn, uri['href']).open()
        else:
            obj = self.module.get(self.dn)
        self._copy_from_obj(obj)

    def save(self, reload: bool = True) -> Response:
        if self.dn:
            return self._modify(reload)
        else:
            return self._create(reload)

    def json_patch(self, patch: dict, reload: bool = True) -> Response:
        if self.dn:
            return self._patch(patch, reload=reload)
        else:
            uri = self.client.get_relation(self.hal, 'create')
            return self._request('POST', uri['href'], patch, {'Content-Type': 'application/json-patch+json'})

    def delete(self, remove_referring: bool = False) -> bytes:
        assert self.uri
        headers = {key: value for key, value in {
            'If-Unmodified-Since': self.last_modified,
            'If-Match': self.etag,
        }.items() if value}
        return self.client.request('DELETE', self.uri, **headers)  # type: ignore # <https://github.com/python/mypy/issues/10008>

    def move(self, position: str, reload: bool = True) -> None:
        self.position = position
        self.save(reload=reload)

    def _modify(self, reload: bool = True) -> Response:
        assert self.uri
        headers = {key: value for key, value in {
            'If-Unmodified-Since': self.last_modified,
            'If-Match': self.etag,
        }.items() if value}
        return self._request('PUT', self.uri, self.representation, headers, reload=reload)

    def _patch(self, data: dict, reload: bool = True) -> Response:
        assert self.uri
        headers = {key: value for key, value in {
            'If-Unmodified-Since': self.last_modified,
            'If-Match': self.etag,
            'Content-Type': 'application/json-patch+json',
        }.items() if value}
        return self._request('PATCH', self.uri, data, headers, reload=reload)

    def _create(self, reload: bool = True) -> Response:
        uri = self.client.get_relation(self.hal, 'create')
        return self._request('POST', uri['href'], self.representation, {}, reload=reload)

    def _request(self, method: str, uri: str, data: dict, headers: dict, reload: bool = True) -> Response:
        response = self.client.make_request(method, uri, data=data, allow_redirects=False, custom_redirect_handling=True, **headers)  # type: ignore # <https://github.com/python/mypy/issues/10008>
        self._reload_from_response(response, reload)
        return response

    def _reload_from_response(self, response: Response, reload: bool) -> None:
        if reload and 200 <= response.response.status_code <= 299 and 'Location' in response.response.headers:
            uri = response.response.headers['Location']
            obj = ShallowObject(self.udm, None, uri)
            self._copy_from_obj(obj.open())
            return

        if response.response.status_code == 200:
            # the response already contains a new representation
            self._copy_from_obj(Object.from_response(self.udm, response))
            return

        if reload:
            self.reload()

    def _copy_from_obj(self, obj: Object) -> None:
        self.udm = obj.udm
        self.representation = copy.deepcopy(obj.representation)
        self.hal = copy.deepcopy(obj.hal)
        self.etag = obj.etag
        self.last_modified = obj.last_modified

    def generate_service_specific_password(self, service: str) -> Any | None:
        uri = self.client.get_relation(self.hal, 'udm:service-specific-password')['href']
        response = self.client.make_request('POST', uri, data={"service": service})
        return response.data.get('password', None)

    def get_layout(self) -> Any | None:
        return self.udm.client.resolve_relation(self.hal, 'udm:layout').get('layout')

    def get_properties(self) -> Any | None:
        return self.udm.client.resolve_relation(self.hal, 'udm:properties').get('properties')

    def get_property_choices(self, property: str) -> Any | None:
        hal = self.udm.client.resolve_relation(self.hal, 'udm:properties')
        return self.udm.client.resolve_relation(hal, 'udm:property-choices', name=property).get('choices')

    def policy_result(self, policy_module: str, policy: str | None = None) -> dict:
        policy_result = self.udm.client.resolve_relation(self.hal, 'udm:policy-result', name=policy_module, template={'policy': policy})
        policy_result.pop('_links', None)
        policy_result.pop('_embedded', None)
        return policy_result


class PatchDocument:
    """application/json-patch+json representation"""

    def __init__(self):
        self.patch = []

    def add(self, path_segments, value):
        self.patch.append({
            'op': 'add',
            'path': self.expand_path(path_segments),
            'value': value,
        })

    def replace(self, path_segments, value):
        self.patch.append({
            'op': 'replace',
            'path': self.expand_path(path_segments),
            'value': value,
        })

    def remove(self, path_segments, value):
        self.patch.append({
            'op': 'remove',
            'path': self.expand_path(path_segments),
            'value': value,  # TODO: not official
        })

    def move(self, path_segments, from_segments):
        self.patch.append({
            'op': 'move',
            'path': self.expand_path(path_segments),
            'from': self.expand_path(from_segments),
        })

    def copy(self, path_segments, from_segments):
        self.patch.append({
            'op': 'copy',
            'path': self.expand_path(path_segments),
            'from': self.expand_path(from_segments),
        })

    def test(self, path_segments, value):
        self.patch.append({
            'op': 'test',
            'path': self.expand_path(path_segments),
            'value': value,
        })

    def expand_path(self, path_segments):
        return '/'.join(path.replace('~', '~0').replace('/', '~1') for path in ['', *path_segments])
