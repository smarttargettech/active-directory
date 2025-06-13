#!/usr/bin/python3
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


from univention.admin.uldap import access, getAdminConnection
from univention.config_registry import ucr_live as ucr
from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import Instance, ProblemFixed, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('Server Role Windows')
description = '\n'.join([
    _('Several services rely on the attribute "univentionServerRole" to search and identify objects in OpenLDAP.'),
    _('Objects that implicitly satisfy the criteria of a Univention Object but lack this attribute should be migrated.'),
])

_WINDOWS_SERVER_ROLES = {
    'computers/windows_domaincontroller': 'windows_domaincontroller',
    'computers/windows': 'windows_client',
}


def udm_objects_without_ServerRole(lo: access) -> dict[str, list[str]]:
    objs: dict[str, list[str]] = {}
    result = lo.search('(&(objectClass=univentionWindows)(!(univentionServerRole=*)))', attr=['univentionObjectType'])
    if result:
        ldap_base = ucr.get('ldap/base')
        for dn, attrs in result:
            if dn.endswith(',cn=temporary,cn=univention,%s' % ldap_base):
                continue
            try:
                univentionObjectType = attrs['univentionObjectType'][0].decode('UTF-8')
            except KeyError:
                univentionObjectType = None

            server_role = _WINDOWS_SERVER_ROLES.get(univentionObjectType, "")
            objs.setdefault(server_role, []).append(dn)

    return objs


def run(_umc_instance: Instance) -> None:
    if ucr.get('server/role') != 'domaincontroller_master':
        return

    lo, _pos = getAdminConnection()
    objs = udm_objects_without_ServerRole(lo)
    details = '\n\n' + _('These objects were found:')

    total_objs = 0
    fixable_objs = 0
    for server_role in sorted(objs):
        num_objs = len(objs[server_role])
        if num_objs:
            total_objs += num_objs
            if server_role:
                fixable_objs += num_objs
                details += '\n· ' + _('Number of objects that should be marked as "%(server_role)s": %(num_objs)d') % {'server_role': server_role, 'num_objs': num_objs}
            else:
                details += '\n· ' + _("Number of unspecific Windows computer objects with inconsistent univentionObjectType: %d (Can't fix this automatically)") % (num_objs,)
    if total_objs:
        if fixable_objs:
            raise Warning(description + details, buttons=[{
                'action': 'migrate_objects',
                'label': _('Migrate %d LDAP objects') % fixable_objs,
            }])
        else:
            raise Warning(description + details, buttons=[])


def migrate_objects(_umc_instance: Instance) -> None:
    lo, _pos = getAdminConnection()
    objs = udm_objects_without_ServerRole(lo)
    for server_role in sorted(objs):
        if not server_role:
            continue
        for dn in objs[server_role]:
            changes = [('univentionServerRole', None, server_role)]
            lo.modify(dn, changes)
    raise ProblemFixed(buttons=[])


actions = {
    'migrate_objects': migrate_objects,
}


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
