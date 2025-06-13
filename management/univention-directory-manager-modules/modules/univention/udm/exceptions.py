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

from collections.abc import Collection  # noqa: F401


class UdmError(Exception):
    """Base class of Exceptions raised by (simplified) UDM modules."""

    msg = ''

    def __init__(self, msg=None, dn=None, module_name=None):
        # type: (Optional[str], Optional[str], Optional[str]) -> None
        msg = msg or self.msg
        super().__init__(msg)
        self.dn = dn
        self.module_name = module_name


class ApiVersionMustNotChange(UdmError):
    """Raised when UDM.version() is called twice."""

    msg = 'The version of an UDM instance must not be changed.'


class ConnectionError(UdmError):
    """Raised when something goes wrong getting a connection."""


class ApiVersionNotSupported(UdmError):
    def __init__(
        self,
        msg=None,  # type: Optional[str]
        module_name=None,  # type: Optional[str]
        requested_version=None,  # type: Optional[int]
    ):  # type: (...) -> None
        self.requested_version = requested_version
        msg = msg or f'Module {module_name!r} is not supported in API version {requested_version!r}.'
        super().__init__(msg, module_name=module_name)


class CreateError(UdmError):
    """Raised when an error occurred when creating an object."""


class DeletedError(UdmError):
    def __init__(self, msg=None, dn=None, module_name=None):
        # type: (Optional[str], Optional[str], Optional[str]) -> None
        msg = msg or 'Object{} has already been deleted.'.format(f' {dn!r}' if dn else '')
        super().__init__(msg, dn, module_name)


class DeleteError(UdmError):
    """Raised when a client tries to delete a UDM object but fails."""

    def __init__(self, msg=None, dn=None, module_name=None):
        # type: (Optional[str], Optional[str], Optional[str]) -> None
        msg = msg or 'Object{} could not be deleted.'.format(f' {dn!r}' if dn else '')
        super().__init__(msg, dn, module_name)


class NotYetSavedError(UdmError):
    """
    Raised when a client tries to delete or reload a UDM object that is not
    yet saved.
    """

    msg = 'Object has not been created/loaded yet.'


class ModifyError(UdmError):
    """Raised if an error occurred when modifying an object."""


class MoveError(UdmError):
    """Raised if an error occurred when moving an object."""


class NoApiVersionSet(UdmError):
    """
    Raised when UDM.get() or UDM.obj_by_id() is used before setting an API
    version.
    """

    msg = 'No API version has been set.'


class NoObject(UdmError):
    """Raised when a UDM object could not be found at a DN."""

    def __init__(self, msg=None, dn=None, module_name=None):
        # type: (Optional[str], Optional[str], Optional[str]) -> None
        msg = msg or f'No object found at DN {dn!r}.'
        super().__init__(msg, dn, module_name)


class NoSuperordinate(UdmError):
    """Raised when no superordinate was supplied but one is needed."""

    def __init__(self, msg=None, dn=None, module_name=None, superordinate_types=None):
        # type: (Optional[str], Optional[str], Optional[str], Optional[Collection[str]]) -> None
        msg = msg or 'No superordinate was supplied, but one of type{} {} is required to create/save a {} object.'.format(
            's' if len(superordinate_types or ()) > 1 else '', ', '.join(superordinate_types or ()), module_name)
        super().__init__(msg, dn, module_name)


class SearchLimitReached(UdmError):
    """Raised when the search results in more objects than specified by the sizelimit."""

    def __init__(self, msg=None, dn=None, module_name=None, search_filter=None, sizelimit=None):
        # type: (Optional[str], Optional[str], Optional[str], Optional[str], Optional[int]) -> None
        msg = msg or 'The search_filter {} resulted in more objects than the specified sizelimit of {} allowed.'.format(
            search_filter or "''", sizelimit or "/",
        )
        self.search_filter = search_filter
        self.sizelimit = sizelimit
        super().__init__(msg, dn, module_name)


class MultipleObjects(UdmError):
    """
    Raised when more than one UDM object was found when there should be at
    most one.
    """


class UnknownModuleType(UdmError):
    """Raised when an LDAP object has no or empty attribute univentionObjectType."""

    def __init__(self, msg=None, dn=None, module_name=None):
        # type: (Optional[str], Optional[str], Optional[str]) -> None
        msg = msg or f'No or empty attribute "univentionObjectType" found at DN {dn!r}.'
        super().__init__(msg, dn, module_name)


class UnknownProperty(UdmError):
    """
    Raised when a client tries to set a property on :py:attr:`BaseObject.props`,
    that it does not support.
    """


class WrongObjectType(UdmError):
    """
    Raised when the LDAP object to be loaded does not match the module type
    (:py:attr:`BaseModule.name`).
    """

    def __init__(self, msg=None, dn=None, module_name=None, univention_object_type=None):
        # type: (Optional[str], Optional[str], Optional[str], Optional[str]) -> None
        msg = msg or f'Wrong UDM module: {dn!r} is not a {module_name!r}, but a {univention_object_type!r}.'
        super().__init__(msg, dn, module_name)
