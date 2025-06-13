#!/usr/bin/python3
#
# Univention Management Console
#  quota module: handles partition related commands
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2006-2025 Univention GmbH
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


import univention.management.console as umc
from univention.lib import fstab
from univention.management.console.error import UMC_Error
from univention.management.console.log import MODULE
from univention.management.console.modules.decorators import simple_response
from univention.management.console.modules.quota import df, tools


_ = umc.Translation('univention-management-console-module-quota').translate


class Commands:

    def partitions_query(self, request):
        result = []
        try:
            fs = fstab.File('/etc/fstab')
            mt = fstab.File('/etc/mtab')
        except OSError as error:
            MODULE.error('Could not open %s' % error.filename)
            raise UMC_Error(_('Could not open %s') % error.filename, 500)

        partitions = fs.get(['xfs', 'ext4', 'ext3', 'ext2'], False)
        for partition in partitions:
            list_entry = {}
            list_entry['partitionDevice'] = partition.spec
            list_entry['mountPoint'] = partition.mount_point
            list_entry['partitionSize'] = None
            list_entry['freeSpace'] = None
            list_entry['inUse'] = tools.quota_is_enabled(partition)
            mounted_partition = mt.find(spec=partition.spec)
            if mounted_partition:
                partition_info = df.DeviceInfo(partition.mount_point)
                list_entry['partitionSize'] = tools.block2byte(partition_info.size(), 'GB', 1)
                list_entry['freeSpace'] = tools.block2byte(partition_info.free(), 'GB', 1)
            result.append(list_entry)
        self.finished(request.id, result)

    def partitions_info(self, request):
        result = {}
        try:
            fs = fstab.File('/etc/fstab')
            mt = fstab.File('/etc/mtab')
        except OSError as error:
            MODULE.error('Could not open %s' % error.filename)
            raise UMC_Error(_('Could not open %s') % error.filename, 500)

        partition = fs.find(spec=request.options['partitionDevice'])
        if not partition:
            raise UMC_Error(_('No partition found'))
        mounted_partition = mt.find(spec=partition.spec)
        if not mounted_partition:
            raise UMC_Error(_('This partition is currently not mounted'))

        result['mountPoint'] = mounted_partition.mount_point
        result['filesystem'] = mounted_partition.type
        result['options'] = mounted_partition.options
        self.finished(request.id, result)

    @simple_response
    def partitions_activate(self, partitionDevice):
        MODULE.info('quota/partitions/activate: %s' % (partitionDevice,))

        def _thread(self, request):
            return tools.activate_quota(partitionDevice, True)
        return _thread

    @simple_response
    def partitions_deactivate(self, partitionDevice):
        MODULE.info('quota/partitions/deactivate: %s' % (partitionDevice,))

        def _thread(self, request):
            return tools.activate_quota(partitionDevice, False)
        return _thread
