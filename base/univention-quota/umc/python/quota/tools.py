#!/usr/bin/python3
#
# Univention Management Console
#  quota module: modify quota settings
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


import math
import os
import re
import subprocess

import univention.management.console as umc
from univention.config_registry import handler_set
from univention.lib import fstab
from univention.management.console.config import ucr
from univention.management.console.error import UMC_Error
from univention.management.console.log import MODULE


_ = umc.Translation('univention-management-console-module-quota').translate


class UserQuota(dict):

    def __init__(self, partition, user, bused, bsoft, bhard, btime, fused, fsoft, fhard, ftime):
        self['id'] = '%s@%s' % (user, partition)
        self['partitionDevice'] = partition
        self['user'] = user
        self['sizeLimitUsed'] = block2byte(bused, 'MB')
        self['sizeLimitSoft'] = block2byte(bsoft, 'MB')
        self['sizeLimitHard'] = block2byte(bhard, 'MB')

        self['fileLimitUsed'] = fused
        self['fileLimitSoft'] = fsoft
        self['fileLimitHard'] = fhard

        self.set_time('sizeLimitTime', btime)
        self.set_time('fileLimitTime', ftime)

    def set_time(self, time, value):
        if not value:
            self[time] = '-'
        elif value == 'none':
            self[time] = _('Expired')
        elif value.endswith('days'):
            self[time] = _('%s Days') % value[:-4]
        elif ':' in value:
            self[time] = value


def repquota(partition):
    # find filesystem type
    fs = fstab.File()
    part = fs.find(spec=partition)
    args = []
    if part.type == 'xfs':
        args = ['--format', 'xfs']

    # -C == do not try to resolve all users at once
    # -v == verbose
    cmd = ['/usr/sbin/repquota', '-C', '-v', partition, *args]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    stdout, _stderr = proc.communicate()
    return (stdout, proc.returncode)


def repquota_parse(partition, output):
    result = []
    if not output:
        return result

    regex = re.compile('(?P<user>[^ ]*) *[-+]+ *(?P<bused>[0-9]*) *(?P<bsoft>[0-9]*) *(?P<bhard>[0-9]*) *((?P<btime>([0-9]*days|none|[0-9]{2}:[0-9]{2})))? *(?P<fused>[0-9]*) *(?P<fsoft>[0-9]*) *(?P<fhard>[0-9]*) *((?P<ftime>([0-9]*days|none|[0-9]{2}:[0-9]{2})))?')
    for line in output:
        matches = regex.match(line)
        if not matches:
            break
        grp = matches.groupdict()
        if not grp['user'] or grp['user'] == 'root':
            continue
        quota = UserQuota(partition, grp['user'], grp['bused'], grp['bsoft'], grp['bhard'], grp['btime'], grp['fused'], grp['fsoft'], grp['fhard'], grp['ftime'])
        result.append(quota)
    return result


def setquota(partition, user, bsoft, bhard, fsoft, fhard):
    return subprocess.call(['/usr/sbin/setquota', '--always-resolve', '-u', user, str(bsoft), str(bhard), str(fsoft), str(fhard), partition])


class QuotaActivationError(Exception):
    pass


def usrquota_is_active(fstab_entry, mt=None):
    if not mt:
        try:
            mt = fstab.File('/etc/mtab')
        except OSError as error:
            raise QuotaActivationError(_('Could not open %s') % error.filename)

    mtab_entry = mt.find(spec=fstab_entry.spec)
    if not mtab_entry:
        raise QuotaActivationError(_('Device is not mounted'))

    # First remount the partition with option "usrquota" if it isn't already
    return bool(mtab_entry.hasopt('usrquota'))


def quota_is_enabled(fstab_entry):
    local_env = os.environ.copy()
    local_env["LC_MESSAGES"] = "C"
    cmd = ("/sbin/quotaon", "-p", "-u", fstab_entry.mount_point)
    p1 = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=local_env)
    stdout, _stderr = p1.communicate()
    stdout = stdout.decode('UTF-8', 'replace')
    if "not found or has no quota enabled" in stdout:
        return False
    else:
        # match lines like "quota on / (/dev/disk/by-uuid/5bf2a723-b25a) is on"
        pattern = re.compile(r"user quota on %s \([^)]*\) is (on|off)" % fstab_entry.mount_point)
        match = pattern.match(stdout)
        if match:
            return match.group(1) == 'on'
        else:
            return None  # tertium datur


def activate_quota(partition, activate):
    partitions = [partition] if not isinstance(partition, list) else partition
    result = []
    try:
        fs = fstab.File()
    except OSError as error:
        raise UMC_Error(_('Could not open %s') % error.filename, 500)

    failed = []
    for device in partitions:
        fstab_entry = fs.find(spec=device)
        if not fstab_entry:
            failed.append(_('Device %r could not be found') % (device,))
            continue

        try:
            status = _do_activate_quota_partition(fs, fstab_entry, activate)
        except QuotaActivationError as exc:
            failed.append('%s: %s' % (fstab_entry.spec, exc))
            continue

        if fstab_entry.mount_point == '/' and fstab_entry.type == 'xfs':
            try:
                enable_quota_in_kernel(activate)
            except QuotaActivationError as exc:
                failed.append('%s: %s' % (fstab_entry.spec, exc))
                continue
        result.append(status)

    if failed:
        message = _('Failed to activate quota support: ') if activate else _('Failed to deactivate quota support: ')
        message += '\n'.join(failed)
        raise UMC_Error(message)

    message = _('Quota support successfully activated') if activate else _('Quota support successfully deactivated')
    raise UMC_Error(message, 200, {'objects': result})


def _do_activate_quota_partition(fs, fstab_entry, activate):
    quota_enabled = quota_is_enabled(fstab_entry)
    if not (activate ^ quota_enabled):
        return {'partitionDevice': fstab_entry.spec, 'message': _('Quota already en/disabled')}

    # persistently change the option in /etc/fstab:
    if activate:
        if 'usrquota' not in fstab_entry.options:
            fstab_entry.options.append('usrquota')
    else:
        if 'usrquota' in fstab_entry.options:
            fstab_entry.options.remove('usrquota')
    fs.save()

    if fstab_entry.type == 'xfs':
        activation_function = _activate_quota_xfs
    elif fstab_entry.type in ('ext2', 'ext3', 'ext4'):
        activation_function = _activate_quota_ext
    else:
        return {'partitionDevice': fstab_entry.spec, 'message': _('Unknown filesystem')}

    activation_function(fstab_entry, activate)

    return {'partitionDevice': fstab_entry.spec, 'message': _('Operation was successful')}


def _activate_quota_xfs(fstab_entry, activate=True):
    if fstab_entry.mount_point != '/':
        if subprocess.call(('/bin/umount', fstab_entry.spec)):
            raise QuotaActivationError(_('Unmounting the partition has failed'))

        if subprocess.call(('/bin/mount', fstab_entry.spec)):
            raise QuotaActivationError(_('Mounting the partition has failed'))

    if subprocess.call(('/usr/sbin/invoke-rc.d', 'quota', 'restart')):
        raise QuotaActivationError(_('Restarting the quota services has failed'))


def enable_quota_in_kernel(activate):
    ucr.load()
    grub_append = ucr.get('grub/append', '')
    flags = []
    option = 'usrquota'
    match = re.match(r'rootflags=([^\s]*)', grub_append)
    if match:
        flags = match.group(1).split(',')
    if activate and option not in flags:
        flags.append(option)
    elif not activate and option in flags:
        flags.remove(option)

    flags = ','.join(flags)
    if flags:
        flags = 'rootflags=%s' % (flags,)

    new_grub_append = grub_append
    if 'rootflags=' not in grub_append:
        if flags:
            new_grub_append = '%s %s' % (grub_append, flags)
    else:
        new_grub_append = re.sub(r'rootflags=[^\s]*', flags, grub_append)

    if new_grub_append != grub_append:
        MODULE.info('Replacing grub/append from %s to %s' % (grub_append, new_grub_append))
        handler_set(['grub/append=%s' % (new_grub_append,)])
        status = _('enable') if activate else _('disable')
        raise QuotaActivationError(_('To %s quota support for the root filesystem the system has to be rebooted.') % (status,))


def _activate_quota_ext(fstab_entry, activate=True):
    if activate:
        # First remount the partition with option "usrquota" if it isn't already
        if not usrquota_is_active(fstab_entry):
            # Since the usrquota option is set in fstab remount will pick it up automatically
            if subprocess.call(('/bin/mount', '-o', 'remount', fstab_entry.spec)):
                raise QuotaActivationError(_('Remounting the partition has failed'))

        # Then make sure that quotacheck can run on the partition by running quotaoff on this partition.
        if subprocess.call(('/sbin/quotaoff', '-u', fstab_entry.spec)):  # exit status should always be zero, even if off already
            raise QuotaActivationError(_('Restarting the quota services has failed'))

        # Run quotacheck to create the aquota.user quota file on the partition
        # Note: This part is the one that makes activation take some time.
        args = ['/sbin/quotacheck']
        if fstab_entry.mount_point == '/':
            args.append('-m')
        args.extend(['-uc', fstab_entry.mount_point])
        if subprocess.call(args):
            raise QuotaActivationError(_('Generating the quota information file failed'))

        # Finally turn on the quota for the partition.
        if subprocess.call(('/sbin/quotaon', '-u', fstab_entry.spec)):  # exit status should be zero
            raise QuotaActivationError(_('Restarting the quota services has failed'))
    else:
        # First turn the userquota off as requested, otherwise "mount -o remount,noquota" fails.
        if subprocess.call(('/sbin/quotaoff', '-u', fstab_entry.spec)):  # exit status should always be zero, even if off already
            raise QuotaActivationError(_('Restarting the quota services has failed'))

        # Then we could turn of the usrquota option on the partition.
        # Note: This is not strictly required technically, we might as well leave it on (until the machine is rebootet).
        # The important point is that the usrquota option has been removed from fstab, that's what /etc/init.d/quota checks.
        #
        # Note2: If the usrquota option is set in mtab but removed in fstab, then remount doesn't automatically pick it up.
        #
        # if subprocess.call(('/bin/mount', '-o', 'remount,noquota', fstab_entry.spec)):
        #     raise QuotaActivationError(_('Remounting the partition has failed'))


_units = ('B', 'KB', 'MB', 'GB', 'TB')
_size_regex = re.compile('(?P<size>[0-9.]+)(?P<unit>(B|KB|MB|GB|TB))?')


def block2byte(size, convertTo, block_size=1024):
    size = int(size) * float(block_size)
    unit = 0
    if convertTo in _units:
        while _units[unit] != convertTo:
            size /= 1024.0
            unit += 1
    return size


def byte2block(size, unit='MB', block_size=1024):
    factor = 0
    if unit in _units:
        while _units[factor] != unit:
            factor += 1
        size = float(size) * math.pow(1024, factor)
        return int(size / float(block_size))
    else:
        return ''
