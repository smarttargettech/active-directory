#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2018-2025 Univention GmbH
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
# you and Univention.
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
Univention Directory Manager Modules (UDM) API

This is a simplified API for accessing UDM objects.
It consists of UDM modules and UDM object.
UDM modules are factories for UDM objects.
UDM objects manipulate LDAP objects.

The :py:class:`UDM` class is a LDAP connection and UDM module factory.

Usage::

    from univention.udm import UDM

    user_mod = UDM.admin().version(2).get('users/user')

or::

    user_mod = UDM.machine().version(2).get('users/user')

or::

    user_mod = UDM.credentials('myuser', 's3cr3t').version(2).get('users/user')

    obj = user_mod.get(dn)
    obj.props.firstname = 'foo'  # modify property
    obj.position = 'cn=users,cn=example,dc=com'  # move LDAP object
    obj.save()  # apply changes

    obj = user_mod.get(dn)
    obj.delete()

    obj = user_mod.new()
    obj.props.username = 'bar'
    obj.props.lastname = 'baz'
    obj.props.password = 'v3r7s3cr3t'
    obj.props.unixhome = '/home/bar'
    obj.save()

    for obj in user_mod.search('uid=a*'):  # search() returns a generator
        print(obj.props.firstname, obj.props.lastname)

A shortcut exists to get UDM objects directly, without knowing their
univention object type::

    UDM.admin().version(2).obj_by_dn(dn)

A shortcut exists to get UDM objects directly, knowing their univention object
type, but without knowing their DN::

    UDM.admin().version(2).get('groups/group').get_by_id('Domain Users')

The API is versioned. A fixed version must be hard coded in your code. Supply
it as argument to the UDM module factory or via :py:meth:`version()`::

    UDM(lo, 0)              # use API version 0 and an existing LDAP connection object
    UDM.admin().version(1)  # use API version 1
    UDM.credentials('myuser', 's3cr3t').version(2).obj_by_dn(dn)  # get object using API version 2

* Version 0: values of UDM properties are the same as with the low level UDM API: mostly strings.
* Version 1: values of (most) UDM properties are de/encoded to useful Python types (e.g. "0" -> 0 or False)
* Version 2: an encoder for settings/portal_category properties was added.

The LDAP connection to use must be supplies as an argument to the UDM module factory or set via
:py:meth:`admin()`, :py:meth:`machine()`, or :py:meth:`credentials()`::

    UDM(lo)        # use an already existing uldap connection object
    UDM.admin()    # cn=admin connection
    UDM.machine()  # machine connection
    UDM.credentials(identity, password, base=None, server=None, port=None)  # custom connection,
        # `identity` is either a username or a DN. LDAP base, server FQDN/IP and port are optional.
        # If it is a username, a machine connection is used to retrieve the DN it belongs to.
"""

from __future__ import annotations

from fnmatch import fnmatch
from operator import itemgetter
from typing import TYPE_CHECKING, Self

from .exceptions import ApiVersionMustNotChange, ApiVersionNotSupported, NoApiVersionSet, NoObject
from .plugins import Plugins


if TYPE_CHECKING:
    import univention.admin.uldap

    from .base import BaseModule, BaseObject

_MODULES_PATH = 'univention.udm.modules'


class UDM:
    """
    Dynamic factory for creating :py:class:`BaseModule` objects::

            group_mod = UDM.admin().version(2).get('groups/group')
            folder_mod = UDM.machine().version(2).get('mail/folder')
            user_mod = UDM.credentials('myuser', 's3cr3t').version(2).get('users/user')

    A shortcut exists to get UDM objects directly::

            UDM.admin().version(2).obj_by_dn(dn)
    """

    _module_object_cache: dict[tuple[str, int, int], BaseModule] = {}

    def __init__(self, connection: univention.admin.uldap.access, api_version: int | None = None) -> None:
        """
        Use the provided connection.

        :param connection: Any connection object (e.g., univention.admin.uldap.access)
        :param int api_version: load only UDM modules that support the
                specified version, can be set later using :py:meth:`version()`.
        """
        self.connection = connection
        self._api_version: int | None = None
        if api_version is not None:
            self.version(api_version)

    @classmethod
    def admin(cls) -> Self:
        """
        Use a cn=admin connection.

        :return: a :py:class:`univention.udm.udm.UDM` instance
        :raises univention.udm.exceptions.ConnectionError: Non-Primary systems, server down, etc.
        """
        from .connections import LDAP_connection
        connection = LDAP_connection.get_admin_connection()
        return cls(connection)

    @classmethod
    def machine(cls, prefer_local_connection: bool = False) -> Self:
        """
        Use a machine connection.

        :param bool prefer_local_connection: Connect to a local LDAP server (on
            a Replica, this would be the local slapd, on a Managed Node, this would
            be locally configured in UCR). Else, connect directly to the Primary
        :return: a :py:class:`univention.udm.udm.UDM` instance
        :raises univention.udm.exceptions.ConnectionError: File permissions, server down, etc.
        """
        from .connections import LDAP_connection
        connection = LDAP_connection.get_machine_connection(ldap_master=not prefer_local_connection)
        return cls(connection)

    @classmethod
    def credentials(
        cls,
        identity: str,
        password: str,
        base: str | None = None,
        server: str | None = None,
        port: int | None = None,
    ) -> Self:
        """
        Use the provided credentials to open an LDAP connection.

        `identity` must be either a username or a DN. If it is a username, a
        machine connection is used to retrieve the DN it belongs to.

        :param str identity: username or user dn to use for LDAP connection
        :param str password: password of user / DN to use for LDAP connection
        :param str base: optional search base
        :param str server: optional LDAP server address as FQDN
        :param int port: optional LDAP server port
        :return: a :py:class:`univention.udm.udm.UDM` instance
        :raises univention.udm.exceptions.ConnectionError: Invalid credentials, server down, etc.
        """
        from .connections import LDAP_connection
        connection = LDAP_connection.get_credentials_connection(identity, password, base, server, port)
        return cls(connection)

    def version(self, api_version: int) -> Self:
        """
        Set the version of the API that the UDM modules must support.

        Use in a chain of methods to get a UDM module::

                UDM.get_admin().version(2).get('groups/group')

        :param int api_version: load only UDM modules that support the
                specified version
        :return: self (the :py:class:`univention.udm.udm.UDM` instance)
        :raises univention.udm.exceptions.ApiVersionMustNotChange: if called twice
        """
        if not isinstance(api_version, int):
            raise ApiVersionNotSupported("Argument 'api_version' must be an int.", requested_version=api_version)
        if self._api_version is None:
            self._api_version = api_version
        else:
            raise ApiVersionMustNotChange()
        return self

    def get(self, name: str) -> BaseModule:
        """
        Get an object of :py:class:`BaseModule` (or of a subclass) for UDM
        module `name`.

        :param str name: UDM module name (e.g. `users/user`)
        :return: object of a subclass of :py:class:`BaseModule`
        :raises univention.udm.exceptions.ApiVersionNotSupported: if the Python module for `name` could not be loaded
        :raises univention.udm.exceptions.NoApiVersionSet: if the API version has not been set
        """
        key = (name, self._api_version, id(self.connection))
        if key not in self._module_object_cache:
            suitable_modules = []
            plugins = Plugins(_MODULES_PATH)
            for module in plugins:
                if self.api_version not in module.meta.supported_api_versions:
                    continue
                for suitable in module.meta.suitable_for:
                    if fnmatch(name, suitable):
                        suitable_modules.append((suitable.count('*'), module))
                        break
            suitable_modules.sort(key=itemgetter(0))
            try:
                klass = suitable_modules[0][1]
            except IndexError:
                raise ApiVersionNotSupported(module_name=name, requested_version=self.api_version)
            else:
                self._module_object_cache[key] = klass(name, self.connection, self.api_version)
        return self._module_object_cache[key]

    def obj_by_dn(self, dn: str) -> BaseObject:
        """
        Try to load an UDM object from LDAP. Guess the required UDM module
        from the ``univentionObjectType`` LDAP attribute of the LDAP object.

        :param str dn: DN of the object to load
        :return: object of a subclass of :py:class:`BaseObject`
        :raises univention.udm.exceptions.NoApiVersionSet: if the API version has not been set
        :raises univention.udm.exceptions.NoObject: if no object is found at `dn`
        :raises univention.udm.exceptions.ImportError: if the Python module for ``univentionObjectType``
                at ``dn`` could not be loaded
        :raises univention.udm.exceptions.UnknownModuleType: if the LDAP object at ``dn`` had no or
                empty attribute ``univentionObjectType``
        """
        if self.connection.__module__ != 'univention.admin.uldap':
            raise NotImplementedError('obj_by_dn() can only be used with an LDAP connection.')
        ldap_obj = self.connection.get(dn, attr=['univentionObjectType'])
        if not ldap_obj:
            raise NoObject(dn=dn)
        uot = ldap_obj['univentionObjectType'][0].decode('utf-8')
        udm_module = self.get(uot)
        return udm_module.get(dn)

    @property
    def api_version(self) -> int:
        if self._api_version is None:
            raise NoApiVersionSet()
        return self._api_version
