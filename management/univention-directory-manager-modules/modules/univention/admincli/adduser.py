#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2004-2025 Univention GmbH
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

"""adduser part for the command line interface"""

import getopt
import os
import subprocess
from collections.abc import Iterable, Iterator  # noqa: F401
from logging import getLogger

from ldap.filter import filter_format

import univention.admin.config
import univention.admin.handlers.computers.windows
import univention.admin.handlers.groups.group
import univention.admin.handlers.users.user
import univention.admin.modules
import univention.admin.objects
import univention.admin.uldap
import univention.config_registry
import univention.logging


log = getLogger('ADMIN')


def status(msg):  # type: (str) -> str
    # univention-adduser is called by Samba when doing "vampire." Since
    # vampire produces a lot of output, and we'd like to print a moderate
    # log, we prepend UNIVENTION to our output. That way we can identify
    # distinguish them from all of Samba's log messages
    out = 'UNIVENTION %s' % (msg,)
    return out


def nscd_invalidate(table):  # type: (str) -> None
    if table:
        log.debug('NSCD: --invalidate %s', table)
        try:
            subprocess.check_call(['/usr/sbin/nscd', '--invalidate', table], close_fds=True)
        except (OSError, subprocess.CalledProcessError):
            log.debug('NSCD: failed')
        else:
            log.debug('NSCD: ok')


def get_user_object(user, position, lo):  # type: (str, univention.admin.uldap.position, univention.admin.uldap.access) -> Union[univention.admin.modules.UdmModule, str]
    try:
        # user Account
        return univention.admin.modules.lookup(univention.admin.handlers.users.user, None, lo, scope='domain', base=position.getDn(), filter=filter_format('(username=%s)', [user]), required=True, unique=True)[0]
    except Exception:
        # machine Account
        for handler in [univention.admin.handlers.computers.windows, univention.admin.handlers.computers.domaincontroller_master, univention.admin.handlers.computers.domaincontroller_slave, univention.admin.handlers.computers.domaincontroller_backup, univention.admin.handlers.computers.memberserver]:
            try:
                return univention.admin.modules.lookup(handler, None, lo, scope='domain', base=position.getDn(), filter=filter_format('(uid=%s)', [user]), required=True, unique=True)[0]
            except Exception:  # noqa: S112
                continue
    return 'ERROR: account not found, nothing modified'


def doit(arglist):
    univention.logging.basicConfig(filename='/var/log/univention/directory-manager-cmd.log', univention_debug_level=1)
    out = []  # type: List[str]
    configRegistry = univention.config_registry.ConfigRegistry()
    configRegistry.load()
    op = 'add'
    scope = 'user'
    cmd = os.path.basename(arglist[0])
    if cmd == 'univention-addgroup':
        scope = 'group'
        op = 'add'
    elif cmd == 'univention-deluser':
        scope = 'user'
        op = 'del'
    elif cmd == 'univention-delgroup':
        scope = 'group'
        op = 'del'
    elif cmd == 'univention-addmachine':
        scope = 'machine'
        op = 'add'
    elif cmd == 'univention-delmachine':
        scope = 'machine'
        op = 'del'
    elif cmd == 'univention-setprimarygroup':
        scope = 'user'
        op = 'primarygroup'

    _opts, args = getopt.getopt(arglist[1:], '', ['status-fd=', 'status-fifo='])

    try:
        lo, position = univention.admin.uldap.getAdminConnection()
    except Exception as exc:
        log.warning('authentication error: %s', exc)
        try:
            lo, position = univention.admin.uldap.getMachineConnection()
        except Exception as exc2:
            log.warning('authentication error: %s', exc2)
            out.append('authentication error: %s' % (exc,))
            out.append('authentication error: %s' % (exc2,))
            return out

    univention.admin.modules.update()

    if len(args) == 1:
        if scope == 'machine':
            machine = args[0]
            machine = machine.removesuffix('$')
            if configRegistry.get('samba/defaultcontainer/computer'):
                position.setDn(configRegistry['samba/defaultcontainer/computer'])
            else:
                position.setDn(univention.admin.config.getDefaultContainer(lo, 'computers/windows'))
        elif scope == 'group':
            group = args[0]
            if configRegistry.get('samba/defaultcontainer/group'):
                position.setDn(configRegistry['samba/defaultcontainer/group'])
            else:
                position.setDn(univention.admin.config.getDefaultContainer(lo, 'groups/group'))
        else:
            user = args[0]
            if configRegistry.get('samba/defaultcontainer/user'):
                position.setDn(configRegistry['samba/defaultcontainer/user'])
            else:
                position.setDn(univention.admin.config.getDefaultContainer(lo, 'users/user'))
        action = op + scope

    elif len(args) == 2:
        user, group = args
        if op == 'del':
            action = 'deluserfromgroup'
        elif op == 'primarygroup':
            action = 'setprimarygroup'
        else:
            action = 'addusertogroup'
    else:
        return out

    if action == 'adduser':
        out.append(status('Adding user %s' % (user,)))
        object = univention.admin.handlers.users.user.object(None, lo, position=position)
        object.open()
        object['username'] = user
        object['lastname'] = user.encode('utf-8').decode('ASCII')
        object['password'] = subprocess.check_output(['/usr/bin/makepasswd', '--minchars=8'], close_fds=True).strip().decode('ASCII', 'ignore')
        object['primaryGroup'] = univention.admin.config.getDefaultValue(lo, 'group')
        object.create()
        nscd_invalidate('passwd')

    elif action == 'deluser':
        out.append(status('Removing user %s' % (user,)))
        object = univention.admin.modules.lookup(univention.admin.handlers.users.user, None, lo, scope='domain', base=position.getDomain(), filter=filter_format('(username=%s)', [user]), required=True, unique=True)[0]
        object.open()
        object.remove()
        nscd_invalidate('passwd')

    elif action == 'addgroup':
        out.append(status('Adding group %s' % (group,)))
        object = univention.admin.handlers.groups.group.object(None, lo, position=position)
        object.open()
        object.options = ['posix']
        object['name'] = group
        object.create()
        nscd_invalidate('group')

    elif action == 'delgroup':
        out.append(status('Removing group %s' % (group,)))
        object = univention.admin.modules.lookup(univention.admin.handlers.groups.group, None, lo, scope='domain', base=position.getDomain(), filter=filter_format('(name=%s)', [group]), required=True, unique=True)[0]
        object.open()
        object.remove()
        nscd_invalidate('group')

    elif action == 'addusertogroup':
        if group in configRegistry.get('samba/addusertogroup/filter/group', '').split(','):
            out.append(status('addusertogroup: filter protects group "%s"' % (group,)))
            return out
        out.append(status('Adding user %s to group %s' % (user, group)))
        groupobject = univention.admin.modules.lookup(univention.admin.handlers.groups.group, None, lo, scope='domain', base=position.getDn(), filter=filter_format('(name=%s)', [group]), required=True, unique=True)[0]
        groupobject.open()
        userobject = get_user_object(user, position, lo)
        if isinstance(userobject, str):
            out.append(userobject)
            return out

        if userobject.dn not in groupobject['users']:
            if groupobject['users'] == [''] or groupobject['users'] == []:
                groupobject['users'] = [userobject.dn]
            else:
                groupobject['users'].append(userobject.dn)
            groupobject.modify()
            nscd_invalidate('group')

    elif action == 'deluserfromgroup':
        out.append(status('Removing user %s from group %s' % (user, group)))
        groupobject = univention.admin.modules.lookup(univention.admin.handlers.groups.group, None, lo, scope='domain', base=position.getDn(), filter=filter_format('(name=%s)', [group]), required=True, unique=True)[0]
        groupobject.open()

        userobject = get_user_object(user, position, lo)
        if isinstance(userobject, str):
            out.append(userobject)
            return out

        userobject.open()
        if userobject.dn in groupobject['users'] and userobject['primaryGroup'] != groupobject.dn:
            groupobject['users'].remove(userobject.dn)
            groupobject.modify()
            nscd_invalidate('group')

    elif action == 'addmachine':
        out.append(status('Adding machine %s' % (machine,)))
        object = univention.admin.handlers.computers.windows.object(None, lo, position=position)
        object.open()
        object.options = ['posix']
        object['name'] = machine
        object['primaryGroup'] = univention.admin.config.getDefaultValue(lo, 'computerGroup')
        object.create()
        nscd_invalidate('hosts')
        nscd_invalidate('passwd')

    elif action == 'delmachine':
        out.append(status('Removing machine %s' % (machine,)))
        object = univention.admin.modules.lookup(univention.admin.handlers.computers.windows, None, lo, scope='domain', base=position.getDomain(), filter=filter_format('(name=%s)', [machine]), required=True, unique=True)[0]
        object.open()
        object.remove()
        nscd_invalidate('hosts')

    elif action == 'setprimarygroup':
        out.append(status('Set primary group %s for user %s' % (group, user)))
        try:
            groupobject = univention.admin.modules.lookup(univention.admin.handlers.groups.group, None, lo, scope='domain', base=position.getDn(), filter=filter_format('(name=%s)', [group]), required=True, unique=True)[0]
        except Exception:
            out.append('ERROR: group not found, nothing modified')
            return out
        groupobject.open()

        userobject = get_user_object(user, position, lo)
        if isinstance(userobject, str):
            out.append(userobject)
            return out

        if 'samba' in userobject.options:
            userobject.options.remove('samba')
        userobject.open()

        if userobject.has_property('primaryGroup'):
            userobject['primaryGroup'] = groupobject.dn
        elif userobject.has_property('machineAccountGroup'):
            userobject['machineAccountGroup'] = groupobject.dn
        else:
            out.append('ERROR: unknown group attribute, nothing modified')
            return out

        userobject.modify()

        if userobject.dn not in groupobject['users']:
            groupobject['users'].append(userobject.dn)
            groupobject.modify()

        nscd_invalidate('group')
        nscd_invalidate('passwd')
    return out


if __name__ == '__main__':
    import sys
    print('\n'.join(doit(sys.argv)))
