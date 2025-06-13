#
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

from __future__ import annotations

import inspect
import string
from typing import TYPE_CHECKING, Any

import listener
from .exceptions import ListenerModuleConfigurationError
from .handler_logging import get_logger


if TYPE_CHECKING:
    from .handler import ListenerModuleHandler


listener.configRegistry.load()


class ListenerModuleConfiguration:
    """
    Interface class for accessing the configuration and code of a listener
    module.

    Subclass this and set the class attributes or pass them through `__init__`.
    If more logic is needed, overwrite the corresponding
    `get_<attribute>` method. Setting `name`, `description`, `ldap_filter` and
    `listener_module_class` is mandatory.

    To extend the configuration, add key names in :py:meth:`get_configuration_keys()`
    and create a `get_<attribute>` method.

    The listener server will use an object of your subclass to access your
    listener module through :py:meth:`get_listener_module_instance()`.
    """

    name = ''                     # (**) name of the listener module
    description = ''              # (*) description of the listener module
    ldap_filter = ''              # (*) LDAP filter, if matched will trigger the listener module
    listener_module_class: type[ListenerModuleHandler] = None  # (**) class that implements the module
    attributes: list[str] = []  # only trigger module, if any of the listed attributes has changed
    # (*) required
    # (**) will be set automatically by the handlers metaclass

    _mandatory_attributes: tuple[str, ...] = ('description', 'ldap_filter', 'listener_module_class')

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _keys = self.get_configuration_keys()
        for k, _v in list(kwargs.items()):
            if k in _keys:
                setattr(self, k, kwargs.pop(k))
        self.logger = get_logger(self.get_name())
        self._run_checks()

    def __repr__(self) -> str:
        return f'{self.__class__.__name__}(name={self.get_name()!r})'

    def _run_checks(self) -> None:
        allowed_name_chars = string.ascii_letters + string.digits + ',.-_'

        for attr in self._mandatory_attributes:
            if not getattr(self, f'get_{attr}', lambda: '')() and not getattr(self, attr, ''):
                raise ListenerModuleConfigurationError(f'Missing or empty {attr!r} attribute in configuration.')
        if set(self.get_name()) - set(allowed_name_chars):
            raise ListenerModuleConfigurationError(
                f'The "name" of a listener module may only contain the following characters: {allowed_name_chars!r}',
            )
        if not inspect.isclass(self.get_listener_module_class()):
            raise ListenerModuleConfigurationError('Attribute "listener_module_class" must be a class.')

    @classmethod
    def get_configuration_keys(cls) -> list[str]:
        """
        List of known configuration keys. Subclasses can expand this to support
        additional attributes.

        :return: list of known configuration keys
        :rtype: list(str)
        """
        return [
            'attributes',
            'description',
            'ldap_filter',
            'listener_module_class',
            'name',
        ]

    def get_name(self) -> str:
        """
        :return: name of module
        :rtype: str
        """
        return self.name

    def get_description(self) -> str:
        """
        :return: description string of module
        :rtype: str
        """
        return self.description

    def get_ldap_filter(self) -> str:
        """
        :return: LDAP filter of module
        :rtype: str
        """
        return self.ldap_filter

    def get_attributes(self) -> list[str]:
        """
        :return: attributes of matching LDAP objects the module will be notified about if changed
        :rtype: list(str)
        """
        assert isinstance(self.attributes, list)
        return self.attributes

    def get_priority(self) -> float:
        """
        :return: priority of the handler. Defines the order in which this module is executed inside the listener
        :rtype: float
        """
        priority = getattr(self, "priority", 50.0)
        return float(priority)

    def get_listener_module_instance(self, *args: Any, **kwargs: Any) -> ListenerModuleHandler:
        """
        Get an instance of the listener module.

        :param tuple args: passed to `__init__` of :py:class:`ListenerModuleHandler`
        :param dict kwargs: : passed to `__init__` of :py:class:`ListenerModuleHandler`
        :return: instance of :py:class:`ListenerModuleHandler`
        :rtype: ListenerModuleHandler
        """
        cls = self.get_listener_module_class()
        return cls(*args, **kwargs)

    def get_listener_module_class(self) -> type[ListenerModuleHandler]:
        """
        Get the class to instantiate for a listener module.

        :return: subclass of :py:class:`univention.listener.ListenerModuleHandler`
        :rtype: ListenerModuleHandler
        """
        return self.listener_module_class

    def get_active(self) -> bool:
        """
        If this listener module should run. Determined by the value of
        `listener/module/<name>/deactivate`.

        :return: whether the listener module should be activated
        :rtype: bool
        """
        return not listener.configRegistry.is_true(f'listener/module/{self.get_name()}/deactivate', False)
