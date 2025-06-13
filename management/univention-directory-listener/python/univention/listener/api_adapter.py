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


import sys
from collections.abc import Mapping, Sequence  # noqa: F401
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from .handler import ListenerModuleHandler  # noqa: F401
    from .handler_configuration import ListenerModuleConfiguration  # noqa: F401


class ListenerModuleAdapter:
    """
    Adapter to convert the :py:mod:`univention.listener.listener_module interface` to
    the existing listener module interface.

    Use in a classic listener module like this:

            globals().update(ListenerModuleAdapter(MyListenerModuleConfiguration()).get_globals())
    """

    def __init__(self, module_configuration, *args, **kwargs):
        # type: (ListenerModuleConfiguration, *Any, **Any) -> None
        """:param ListenerModuleConfiguration module_configuration: configuration object"""
        self.config = module_configuration
        self._ldap_cred = {}  # type: Dict[str, str]
        self._module_handler_obj = None  # type: Optional[ListenerModuleHandler]
        self._saved_old = {}  # type: Mapping[str, Sequence[bytes]]
        self._saved_old_dn = None  # type: Optional[str]
        self._rename = False
        self._renamed = False
        self._run_checks()

    def _run_checks(self):
        # type: () -> None
        pass

    def get_globals(self):
        # type: () -> Dict[str, Any]
        """
        Returns the variables to be written to the module namespace, that
        make up the legacy listener module interface.

        :return: a mapping with keys: `name`, `description`, `filter_s`,
                `attributes`, `modrdn`, `handler`, `initialize`, `clean`, `prerun`,
                `postrun`, `setdata`, ..
        :rtype: dict
        """
        name = self.config.get_name()
        description = self.config.get_description()
        filter_s = self.config.get_ldap_filter() if self.config.get_active() else '(objectClass=listenerModuleDeactivated)'
        attributes = self.config.get_attributes()
        priority = self.config.get_priority()
        modrdn = 1
        handler = self._handler
        initialize = self._lazy_initialize
        clean = self._lazy_clean
        prerun = self._lazy_pre_run
        postrun = self._lazy_post_run
        setdata = self._setdata
        return {
            "name": name,
            "description": description,
            "filter": filter_s,
            "attributes": attributes,
            "priority": priority,
            "modrdn": modrdn,
            "handler": handler,
            "initialize": initialize,
            "clean": clean,
            "prerun": prerun,
            "postrun": postrun,
            "setdata": setdata,
        }

    def _setdata(self, key, value):
        # type: (str, str) -> None
        """
        Store LDAP connection credentials passes by the listener (one by one)
        to the listener module. Passes them to the handler object once they
        are complete.

        :param str key: one of `basedn`, `basedn`, `bindpw`, `ldapserver`
        :param str value: credentials
        """
        self._ldap_cred[key] = value
        if set(self._ldap_cred) >= {'basedn', 'bindpw', 'ldapserver'}:
            self._module_handler._set_ldap_credentials(
                self._ldap_cred['basedn'],
                self._ldap_cred['binddn'],
                self._ldap_cred['bindpw'],
                self._ldap_cred['ldapserver'],
            )
            self._ldap_cred.clear()

    @property
    def _module_handler(self):
        # type: () -> ListenerModuleHandler
        """Make sure to not create more than one instance of a listener module."""
        if not self._module_handler_obj:
            self._module_handler_obj = self.config.get_listener_module_instance()
        return self._module_handler_obj

    def _handler(self, dn, new, old, command):
        # type: (str, Mapping[str, Sequence[bytes]], Mapping[str, Sequence[bytes]], str) -> None
        """
        Function called by listener when a LDAP object matching the filter is
        created/modified/moved/deleted.

        :param str dn: the objects DN
        :param dict new: new LDAP objects attributes
        :param dict old: previous LDAP objects attributes
        :param str command: LDAP modification type
        """
        if command == 'r':
            self._saved_old = old
            self._saved_old_dn = dn
            self._rename = True
            self._renamed = False
            return
        elif command == 'a' and self._rename:
            old = self._saved_old

        try:
            if old and not new:
                self._module_handler.remove(dn, old)
            elif old and new:
                if self._renamed and not self._module_handler.diff(old, new):
                    # ignore second modify call after a move if no non-metadata
                    # attribute changed
                    self._rename = self._renamed = False
                    return
                self._module_handler.modify(dn, old, new, self._saved_old_dn if self._rename else None)
                self._renamed = self._rename
                self._rename = False
                self._saved_old_dn = None
            elif not old and new:
                self._module_handler.create(dn, new)
        except Exception:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._module_handler.error_handler(dn, old, new, command, exc_type, exc_value, exc_traceback)

    def _lazy_initialize(self):
        # type: () -> None
        return self._module_handler.initialize()

    def _lazy_clean(self):
        # type: () -> None
        return self._module_handler.clean()

    def _lazy_pre_run(self):
        # type: () -> None
        return self._module_handler.pre_run()

    def _lazy_post_run(self):
        # type: () -> None
        return self._module_handler.post_run()
