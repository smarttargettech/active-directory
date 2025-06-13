#!/usr/bin/python3
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


from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Any

from univention.listener import ListenerModuleConfiguration, ListenerModuleHandler


class ComplexHandler(ListenerModuleHandler):

    # For complex setups make the :py:class:`Configuration` a subclass of
    # :py:class:`ListenerModuleConfiguration` and overwrite its methods.
    class Configuration(ListenerModuleConfiguration):
        description = 'a description'
        ldap_filter = '(objectClass=inetOrgPerson)'

        def get_attributes(self) -> list[str]:
            # do more complicated stuff than just setting the class variable...
            return ['cn']

        def get_active(self) -> bool:
            ucr_setting = super(ComplexHandler.Configuration, self).get_active()
            # check something in a database or network service
            query_external_source = True
            return ucr_setting and query_external_source

    def __init__(self, listener_configuration: ListenerModuleConfiguration, *args: Any, **kwargs: Any) -> None:
        # The log level for messages that go to
        # :file:`/var/log/univention/listener_modules/my_listener_module.log` is set
        # with the UCR variable `listener/module/my_listener_module/debug/level`.
        super().__init__(listener_configuration, *args, **kwargs)
        self.logger.info('ComplexHandler.__init__()')
        self.logger.debug('DEBUG level message')
        self.logger.info('INFO level message')
        self.logger.warning('WARN level message')
        self.logger.error('ERROR level message')

    def create(self, dn: str, new: Mapping[str, Sequence[bytes]]) -> None:
        self.logger.info('ComplexHandler.create() dn=%r', dn)

    def modify(self, dn: str, old: Mapping[str, Sequence[bytes]], new: Mapping[str, Sequence[bytes]], old_dn: str | None) -> None:
        # modify() will be called for both moves and modifies.
        # If `old_dn` is set, a move happened.
        # Both DN an attributes can change during a move.
        self.logger.info('ComplexHandler.modify() dn=%r', dn)
        if old_dn:
            self.logger.info('ComplexHandler.modify() this is (also) a MOVE, old_dn=%r', old_dn)
        self.logger.info('ComplexHandler.modify() self.diff(old, new)=%r', self.diff(old, new))
        self.logger.info(
            'ComplexHandler.modify() self.diff(old, new, ignore_metadata=False)=%r',
            self.diff(old, new, ignore_metadata=False),
        )

    def remove(self, dn: str, old: Mapping[str, Sequence[bytes]]) -> None:
        # An exception is triggered here to showcase the error_handler feature.
        self.logger.info('ComplexHandler.remove() dn=%r', dn)
        raise Exception("fail")
        # This will raise an :py:exception:`Exception`, which will be handled by :py:meth:`error_handler`.
        # The error handler will *not* return here. After all this is an unhandled exception.

    def initialize(self) -> None:
        super().initialize()
        self.logger.info('ComplexHandler.initialize()')

    def clean(self) -> None:
        super().clean()
        self.logger.info('ComplexHandler.clean()')

    def pre_run(self) -> None:
        super().pre_run()
        self.logger.info('ComplexHandler.pre_run()')

    def post_run(self) -> None:
        super().post_run()
        self.logger.info('ComplexHandler.post_run()')

    def error_handler(
            self,
            dn: str,
            old: Mapping[str, Sequence[bytes]],
            new: Mapping[str, Sequence[bytes]],
            command: str,
            exc_type: type[BaseException] | None,
            exc_value: BaseException | None,
            exc_traceback: TracebackType | None,
    ) -> None:
        # `exc_type`, `exc_value` and `exc_traceback` can be examined for further
        # information about the exception.
        self.logger.exception(  # noqa: LOG004
            'An error occurred in listener module %r. dn=%r old={%d keys...} new={%d keys...} command=%r',
            self.config.name, dn, len(old.keys()), len(new.keys()), command,
        )
