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


import inspect
import os
import types
from collections.abc import Iterable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, cast

from univention.admin.uldap import access, position

import listener
from .api_adapter import ListenerModuleAdapter
from .exceptions import ListenerModuleConfigurationError, ListenerModuleRuntimeError
from .handler_configuration import ListenerModuleConfiguration
from .handler_logging import get_logger


listener.configRegistry.load()


class HandlerMetaClass(type):
    """
    Read handler configuration, invoke adapter and set global variables in module to
    fulfill original API.
    """

    def __new__(mcs, clsname: str, bases: tuple[type, ...], attrs: dict[str, Any]) -> type['ListenerModuleHandler']:
        kls = cast(type["ListenerModuleHandler"], super().__new__(mcs, clsname, bases, attrs))
        is_listener_module = getattr(kls, '_is_listener_module', lambda: False)
        if is_listener_module():
            lm_module: types.ModuleType | None = inspect.getmodule(kls)
            name = os.path.basename(lm_module.__name__).split(".")[0]
            kls.config = kls._get_configuration(name)
            adapter_cls: type[ListenerModuleAdapter] = kls._adapter_class
            for k, v in adapter_cls(kls.config).get_globals().items():
                setattr(lm_module, k, v)
        return kls


class ListenerModuleHandler(metaclass=HandlerMetaClass):
    """
    Listener module base class.

    Subclass this to implement the logic of your listener module and have
    :py:meth:`ListenerModuleConfiguration.get_listener_module_class` return the name of
    your subclass.

    This class is not intended to be used directly. It should only be
    instantiated by :py:meth:`ListenerModuleConfiguration.get_listener_module_instance()`.
    """

    _metadata_attributes = (
        'createTimestamp', 'creatorsName', 'entryCSN', 'entryDN', 'entryUUID',
        'hasSubordinates', 'modifiersName', 'modifyTimestamp',
        'structuralObjectClass', 'subschemaSubentry',
    )
    _configuration_class = ListenerModuleConfiguration
    _adapter_class = ListenerModuleAdapter
    config: ListenerModuleConfiguration | None = None
    ucr = listener.configRegistry

    class Configuration(ListenerModuleConfiguration):
        """
        Overwrite this with your own class of the same name. It can be
        any Python class with just the required attributes (`description`,
        `ldap_filter`) or a subclass of :py:class:`ListenerModuleConfiguration`.
        """

    def __init__(self, *args: str, **kwargs: str) -> None:
        """
        When subclassing, in :py:meth:`__init__()` first call must be:

                `super(.., self).__init__(*args, **kwargs)`

        `self.config` will be set by the metaclass.
        """
        if not self.config:
            raise ListenerModuleConfigurationError(f'{self.__class__.__name__}.config was not set by meta class.')
        self.logger = get_logger(self.config.get_name())
        self.ucr.load()
        self._lo: access | None = None
        self._po: position | None = None
        self._ldap_credentials: dict[str, str] | None = None
        self.logger.debug('Starting with configuration: %r', self.config)
        if not self.config.get_active():
            self.logger.warning(
                'Listener module %r deactivated by UCRV "listener/module/%s/deactivate".',
                self.config.get_name(), self.config.get_name(),
            )

    def __repr__(self) -> str:
        assert self.config
        return f'{self.__class__.__name__}({self.config.name})'

    def create(self, dn: str, new: Mapping[str, Sequence[bytes]]) -> None:
        """
        Called when a new object was created.

        :param str dn: current objects DN
        :param dict new: new LDAP objects attributes
        """

    def modify(self, dn: str, old: Mapping[str, Sequence[bytes]], new: Mapping[str, Sequence[bytes]], old_dn: str | None) -> None:
        """
        Called when an existing object was modified or moved.

        A move can be be detected by looking at `old_dn`. Attributes can be
        modified during a move.

        :param str dn: current objects DN
        :param dict old: previous LDAP objects attributes
        :param dict new: new LDAP objects attributes
        :param old_dn: previous DN if object was moved/renamed, None otherwise
        :type old_dn: str or None
        """

    def remove(self, dn: str, old: Mapping[str, Sequence[bytes]]) -> None:
        """
        Called when an object was deleted.

        :param str dn: current objects DN
        :param dict old: previous LDAP objects attributes
        """

    def initialize(self) -> None:
        """
        Called once when the Univention Directory Listener loads the module
        for the first time or when a resync it triggered.
        """

    def clean(self) -> None:
        """
        Called once when the Univention Directory Listener loads the module
        for the first time or when a resync it triggered.
        """

    def pre_run(self) -> None:
        """
        Called before create/modify/remove if either the Univention Directory
        Listener has been restarted or when :py:meth:`post_run()` has run before.

        Use for example to open an LDAP connection.
        """

    def post_run(self) -> None:
        """
        Called only, when no change happens for 15 seconds - for *any* listener
        module.

        Use for example to close an LDAP connection.
        """

    @staticmethod
    @contextmanager
    def as_root() -> Iterator[None]:
        """
        Contextmanager to temporarily change the effective UID of the current
        process to 0:

                with self.as_root():
                        do something

        Use :py:func:`listener.setuid()` for any other user than `root`. But be
        aware that :py:func:`listener.unsetuid()` will not be possible
        afterwards, as that requires root privileges.
        """
        old_uid = os.geteuid()
        try:
            if old_uid != 0:
                listener.setuid(0)
            yield
        finally:
            if old_uid != 0:
                listener.unsetuid()

    @classmethod
    def diff(cls, old: Mapping[str, Sequence[bytes]], new: Mapping[str, Sequence[bytes]], keys: Iterable[str] | None = None, ignore_metadata: bool = True) -> dict[str, tuple[Sequence[bytes] | None, Sequence[bytes] | None]]:
        """
        Find differences in old and new. Returns dict with keys pointing to old
        and new values.

        :param dict old: previous LDAP objects attributes
        :param dict new: new LDAP objects attributes
        :param list keys: consider only those keys in comparison
        :param bool ignore_metadata: ignore changed metadata attributes (if `keys` is not set)
        :return: key -> (old[key], new[key]) mapping
        :rtype: dict
        """
        res = {}
        if keys:
            keys = set(keys)
        else:
            keys = set(old) | set(new)
            if ignore_metadata:
                keys.difference_update(cls._metadata_attributes)
        for key in keys:
            if set(old.get(key, [])) != set(new.get(key, [])):
                res[key] = old.get(key), new.get(key)
        return res

    def error_handler(self, dn: str, old: Mapping[str, Sequence[bytes]], new: Mapping[str, Sequence[bytes]], command: str, exc_type: type[BaseException] | None, exc_value: BaseException | None, exc_traceback: types.TracebackType | None) -> None:
        # NoReturn
        """
        Will be called for unhandled exceptions in create/modify/remove.

        :param str dn: current objects DN
        :param dict old: previous LDAP objects attributes
        :param dict new: new LDAP objects attributes
        :param str command: LDAP modification type
        :param type exc_type: exception class
        :param BaseException exc_value: exception object
        :param traceback exc_traceback: traceback object
        """
        self.logger.exception('dn=%r command=%r\n    old=%r\n    new=%r', dn, command, old, new)  # noqa: LOG004
        raise exc_value.with_traceback(exc_traceback)

    @property
    def lo(self) -> access:
        """
        LDAP connection object.

        :return: uldap.access object
        :rtype: univention.admin.uldap.access
        """
        if not self._lo:
            ldap_credentials = self._get_ldap_credentials()
            if not ldap_credentials:
                assert self.config
                raise ListenerModuleRuntimeError(
                    f'LDAP connection of listener module {self.config.get_name()!r} has not yet been initialized.',
                )
            self._lo = access(**ldap_credentials)
        return self._lo

    @property
    def po(self) -> position:
        """
        Get a LDAP position object for the base DN (ldap/base).

        :return: uldap.position object
        :rtype: univention.admin.uldap.position
        """
        if not self._po:
            self._po = position(self.lo.base)
        return self._po

    def _get_ldap_credentials(self) -> dict[str, str] | None:
        """
        Get the LDAP credentials received through setdata().

        :return: the LDAP credentials
        :rtype: dict(str, str)
        """
        return self._ldap_credentials

    def _set_ldap_credentials(self, base: str, binddn: str, bindpw: str, host: str) -> None:
        """
        Store LDAP connection credentials for use by :py:attr.`self.lo`. It is not
        necessary to manually run this method. The listener will automatically
        run it at startup.

        :param str base: base DN
        :param str binddn: bind DB
        :param str bindpw: bind password
        :param str host: LDAP server
        """
        old_credentials = self._ldap_credentials
        self._ldap_credentials = {
            "host": host,
            "base": base,
            "binddn": binddn,
            "bindpw": bindpw,
        }
        if old_credentials != self._ldap_credentials:
            # force creation of new LDAP connection
            self._lo = self._po = None

    @classmethod
    def _get_configuration(cls, name: str) -> ListenerModuleConfiguration:
        """
        Load configuration, optionally converting a plain Python class to a
        :py:class:`ListenerModuleConfiguration` object. Set `cls._configuration_class` to
        a subclass of :py:class:`ListenerModuleConfiguration` to change the returned
        object type.

        :param str name: the modules name
        :return: configuration object
        :rtype: ListenerModuleConfiguration
        """
        try:
            conf_class = cls.Configuration
        except AttributeError:
            raise ListenerModuleConfigurationError(f'Class {cls.__name__!r} missing inner "Configuration" class.')
        if not inspect.isclass(conf_class):
            raise ListenerModuleConfigurationError(f'{cls.__name__!s}.Configuration must be a class.')
        if conf_class is ListenerModuleHandler.Configuration:
            raise ListenerModuleConfigurationError(f'Missing {cls.__name__!s}.Configuration class.')
        if issubclass(conf_class, cls._configuration_class):
            conf_class.listener_module_class = cls
            conf_class.name = name
            return conf_class()
        else:
            conf_class.name = name
            conf_obj = conf_class()
            attrs = cls._configuration_class.get_configuration_keys()
            kwargs = {"listener_module_class": cls}
            for attr in attrs:
                try:
                    get_method = getattr(conf_obj, f'get_{attr}')
                    if not callable(get_method):
                        raise ListenerModuleConfigurationError(
                            f'Attribute {get_method!r} of configuration class {conf_obj.__class__!r} is not callable.',
                        )
                    kwargs[attr] = get_method()
                    continue
                except AttributeError:
                    pass
                try:
                    kwargs[attr] = getattr(conf_obj, attr)
                except AttributeError:
                    pass
                # Checking for required attributes is done in ListenerModuleConfiguration().
            return cls._configuration_class(**kwargs)

    @classmethod
    def _is_listener_module(cls) -> bool:
        """
        Is this a listener module?

        :return: `True` if the file is in :file:`/usr/lib/univention-directory-listener/`.
        :rtype: bool
        """
        try:
            path = inspect.getfile(cls)
        except TypeError:
            # loaded from interactive console: <module '__main__' (built-in)> is a built-in class
            return False
        return path.startswith('/usr/lib/univention-directory-listener')
