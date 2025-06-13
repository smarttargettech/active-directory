#
# Univention S4 Connector
#  UDM module for BLOB-based wireless Group Policy
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

import univention.admin.handlers
import univention.admin.localization
import univention.admin.syntax
from univention.admin.layout import Group, Tab


translation = univention.admin.localization.translation('univention.admin.handlers.ms')
_ = translation.translate

module = 'ms/gpwl-wireless-blob'
operations = ['add', 'edit', 'remove', 'search', 'move', 'subtree_move']
childs = True
short_description = _('MS wireless Group Policy blob')
long_description = ''
options = {
    'default': univention.admin.option(
        short_description=short_description,
        default=True,
        objectClasses=['msieee80211-Policy', 'top'],
    ),
}
property_descriptions = {
    'name': univention.admin.property(
        short_description=_('Name'),
        long_description='',
        syntax=univention.admin.syntax.string,
        required=True,
        identifies=True,
    ),
    'description': univention.admin.property(
        short_description=_('Description'),
        long_description='',
        syntax=univention.admin.syntax.string,
    ),
    'msieee80211-ID': univention.admin.property(
        short_description=_('ID'),
        long_description='',
        syntax=univention.admin.syntax.string,
    ),
    'msieee80211-DataType': univention.admin.property(
        short_description=_('Data type'),
        long_description='',
        syntax=univention.admin.syntax.integer,
    ),
    'msieee80211-Data': univention.admin.property(
        short_description=_('Data'),
        long_description='',
        syntax=univention.admin.syntax.TextArea,
        size='Two',
    ),
}

layout = [
    Tab(_('General'), _('Basic settings'), layout=[
        Group(_('General'), layout=[
            ["name", "description"],
        ]),
        Group(_('Policy settings'), layout=[
            'msieee80211-ID',
            'msieee80211-DataType',
            'msieee80211-Data',
        ]),
    ]),
]

mapping = univention.admin.mapping.mapping()
mapping.register('name', 'cn', None, univention.admin.mapping.ListToString)
mapping.register('description', 'description', None, univention.admin.mapping.ListToString)
mapping.register('msieee80211-ID', 'msieee80211-ID', None, univention.admin.mapping.ListToString)
mapping.register('msieee80211-DataType', 'msieee80211-DataType', None, univention.admin.mapping.ListToString)
mapping.register('msieee80211-Data', 'msieee80211-Data', univention.admin.mapping.mapBase64, univention.admin.mapping.unmapBase64)


class object(univention.admin.handlers.simpleLdap):
    module = module

    def _ldap_pre_modify(self):
        if self.hasChanged('name'):
            self.move(self._ldap_dn())


identify = object.identify
lookup = object.lookup
