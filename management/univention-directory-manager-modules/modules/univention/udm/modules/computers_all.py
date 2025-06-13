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

r"""Module and object for all `computers/\*` UDM modules."""


from ..encoders import (
    CnameListPropertyEncoder, DnsEntryZoneAliasListPropertyEncoder, DnsEntryZoneForwardListMultiplePropertyEncoder,
    DnsEntryZoneReverseListMultiplePropertyEncoder, StringIntBooleanPropertyEncoder, StringIntPropertyEncoder,
    dn_list_property_encoder_for, dn_property_encoder_for,
)
from .generic import GenericModule, GenericObject, GenericObjectProperties


class ComputersAllObjectProperties(GenericObjectProperties):
    r"""`computers/\*` UDM properties."""

    _encoders = {
        'dnsAlias': CnameListPropertyEncoder,  # What is this? Isn't this data in dnsEntryZoneAlias already?
        'dnsEntryZoneAlias': DnsEntryZoneAliasListPropertyEncoder,
        'dnsEntryZoneForward': DnsEntryZoneForwardListMultiplePropertyEncoder,
        'dnsEntryZoneReverse': DnsEntryZoneReverseListMultiplePropertyEncoder,
        'groups': dn_list_property_encoder_for('groups/group'),
        'nagiosServices': dn_list_property_encoder_for('nagios/service'),
        'network': dn_property_encoder_for('networks/network'),
        'primaryGroup': dn_property_encoder_for('groups/group'),
        'reinstall': StringIntBooleanPropertyEncoder,
        'sambaRID': StringIntPropertyEncoder,
    }


class ComputersAllObject(GenericObject):
    r"""Better representation of `computers/\*` properties."""

    udm_prop_class = ComputersAllObjectProperties


class ComputersAllModule(GenericModule):
    """ComputersAllObject factory"""

    _udm_object_class = ComputersAllObject

    class Meta:
        supported_api_versions = [1, 2, 3]
        default_positions_property = 'computers'
        suitable_for = ['computers/*']


class ComputersDCModule(ComputersAllModule):
    """ComputersAllObject factory with an adjusted default position"""

    class Meta:
        supported_api_versions = [1, 2, 3]
        default_positions_property = 'domaincontroller'
        suitable_for = ['computers/domaincontroller_master', 'computers/domaincontroller_backup', 'computers/domaincontroller_slave']


class ComputersMemberModule(ComputersAllModule):
    """ComputersAllObject factory with an adjusted default position"""

    def _get_default_object_positions(self) -> list[str]:
        ret = super()._get_default_object_positions()
        if len(ret) == 4 and \
                f'cn=computers,{self.connection.base}' in ret and \
                f'cn=memberserver,cn=computers,{self.connection.base}' in ret and \
                f'cn=dc,cn=computers,{self.connection.base}' in ret and \
                self.connection.base in ret:
            ret.remove(f'cn=memberserver,cn=computers,{self.connection.base}')
            ret.insert(0, f'cn=memberserver,cn=computers,{self.connection.base}')
        return ret

    class Meta:
        supported_api_versions = [1, 2, 3]
        default_positions_property = 'computers'
        suitable_for = ['computers/memberserver']
