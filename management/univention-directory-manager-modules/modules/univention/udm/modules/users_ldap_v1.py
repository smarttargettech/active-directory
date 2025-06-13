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
FOR TESTING PURPOSES ONLY!

Module and object specific for "users/ldap" UDM module.
"""


from ..encoders import DisabledPropertyEncoder
from .generic import GenericModule, GenericObject, GenericObjectProperties


class UsersLdapObjectProperties(GenericObjectProperties):
    """users/ldap UDM properties."""

    _encoders = {
        'disabled': DisabledPropertyEncoder,
    }


class UsersLdapObject(GenericObject):
    """Better representation of users/ldap properties."""

    udm_prop_class = UsersLdapObjectProperties


class UsersLdapModule(GenericModule):
    """UsersLdapObject factory"""

    _udm_object_class = UsersLdapObject

    class Meta:
        supported_api_versions = [1, 2, 3]
        suitable_for = ['users/ldap']
