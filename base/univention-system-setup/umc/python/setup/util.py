#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2011-2025 Univention GmbH
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

"""
Univention Management Console
 module: system setup
"""

from __future__ import annotations

import copy
import csv
import ipaddress
import json
import os
import os.path
import random
import re
import socket
import subprocess
import tempfile
import time
import traceback
from contextlib import contextmanager
from re import Pattern
from typing import IO, TYPE_CHECKING, Any

import dns.exception
import dns.resolver
import dns.reversename
import ldap
import psutil

import univention.config_registry
from univention.lib import atjobs
from univention.lib.admember import (
    check_ad_account, check_connection, connectionFailed, do_time_sync, failedADConnect, lookup_adds_dc,
    notDomainAdminInAD,
)
from univention.lib.i18n import Locale, Translation
from univention.management.console.log import MODULE
from univention.management.console.modules import UMC_Error


if TYPE_CHECKING:
    from collections.abc import Container, Iterator, Mapping


# FIXME: this triggers imports from univention-lib during build time test execution.
# This in effect imports univention-ldap which is not an explicit dependency for
# univention-lib as of writing. (Bug #43388)
# The try except can be removed as soon as the dependency problem is resolved.
try:
    from univention.appcenter.actions import get_action
    from univention.appcenter.app_cache import AppCache, Apps
except ImportError as exc:
    MODULE.warn('Ignoring import error: %s' % (exc,))
_ = Translation('univention-management-console-module-setup').translate

ucr = univention.config_registry.ConfigRegistry()
ucr.load()

PATH_SYS_CLASS_NET = '/sys/class/net'
PATH_SETUP_SCRIPTS = '/usr/lib/univention-system-setup/scripts/'
PATH_JOIN_SCRIPT = '/usr/lib/univention-system-setup/scripts/setup-join.sh'
PATH_JOIN_LOG = '/var/log/univention/join.log'
PATH_PROFILE = '/var/cache/univention-system-setup/profile'
LOG_FILE = '/var/log/univention/setup.log'
PATH_PASSWORD_FILE = '/var/cache/univention-system-setup/secret'
PATH_STATUS_FILE = '/var/www/ucs_setup_process_status.json'
CMD_ENABLE_EXEC = ['/usr/share/univention-updater/enable-apache2-umc', '--no-restart']
CMD_ENABLE_EXEC_WITH_RESTART = '/usr/share/univention-updater/enable-apache2-umc'
CMD_DISABLE_EXEC = '/usr/share/univention-updater/disable-apache2-umc'
CMD_CLEANUP_SCRIPT = '/usr/lib/univention-system-setup/scripts/cleanup.py >>/var/log/univention/setup.log 2>&1'
CMD_APPLIANCE_HOOKS = '/usr/lib/univention-system-setup/scripts/appliance_hooks.py >>/var/log/univention/setup.log 2>&1'
CITY_DATA_PATH = '/usr/share/univention-system-setup/city_data.json'
COUNTRY_DATA_PATH = '/usr/share/univention-system-setup/country_data.json'

RE_LOCALE = re.compile(r'([^.@ ]+).*')

# list of all needed UCR variables
UCR_VARIABLES = [
    # common
    'server/role',
    # language
    'locale', 'locale/default',
    # keyboard
    'xorg/keyboard/options/XkbLayout', 'xorg/keyboard/options/XkbModel',
    'xorg/keyboard/options/XkbVariant',
    # basis
    'hostname', 'domainname', 'ldap/base', 'windows/domain',
    # net: ipv4
    'gateway',
    'nameserver1', 'nameserver2', 'nameserver3',
    'dns/forwarder1', 'dns/forwarder2', 'dns/forwarder3',
    'proxy/http',
    # net: ipv6
    'ipv6/gateway',
    'interfaces/primary',
    # ssl
    'ssl/common', 'ssl/locality', 'ssl/country', 'ssl/state',
    'ssl/organization', 'ssl/organizationalunit', 'ssl/email',
    # fqdn
    'hostname',
    'domainname',
]


def timestamp() -> str:
    return time.strftime('%Y-%m-%d %H:%M:%S')


def is_system_joined() -> bool:
    return os.path.exists('/var/univention-join/joined')


def load_values(lang: str | None = None) -> dict[str, str]:
    ucr.load()
    values = {ikey: ucr[ikey] for ikey in UCR_VARIABLES}

    # net
    from univention.management.console.modules.setup.network import Interfaces
    interfaces = Interfaces()
    values['interfaces'] = interfaces.to_dict()
    values['physical_interfaces'] = [idev['name'] for idev in detect_interfaces()]

    # see whether the system has been joined or not
    values['joined'] = is_system_joined()

    # root password
    values['root_password'] = ''

    # memory
    values['memory_total'] = psutil.virtual_memory().total / 1024.0 / 1024.0  # MiB

    # get timezone
    values['timezone'] = ''
    if os.path.exists('/etc/timezone'):
        with open('/etc/timezone') as fd:
            values['timezone'] = fd.readline().strip()

    # read license agreement for app appliance
    if lang and ucr.get('umc/web/appliance/data_path'):
        prefix = ucr.get('umc/web/appliance/data_path')
        license_path = '%sLICENSE_AGREEMENT' % prefix
        localized_license_path = '%s_%s' % (license_path, lang.upper())
        english_license_path = '%s_EN' % license_path
        for ipath in (localized_license_path, license_path, english_license_path):
            if os.path.exists(ipath):
                with open(ipath) as license_file:
                    values['license_agreement'] = license_file.read()
                    break

    # check for installed system activation
    values['system_activation_installed'] = os.path.exists('/usr/sbin/univention-system-activation')

    return values


def auto_complete_values_for_join(newValues: dict[str, str], current_locale: Locale | None = None) -> dict[str, str]:
    # try to automatically determine the domain, except on a dcmaster
    if newValues['server/role'] != 'domaincontroller_master' and not newValues.get('domainname'):
        ucr.load()
        for nameserver in ('nameserver1', 'nameserver2', 'nameserver3'):
            if newValues.get('domainname'):
                break
            nameserver = newValues.get(nameserver, ucr.get(nameserver))
            if not nameserver:
                continue
            newValues['domainname'] = get_ucs_domain(nameserver)
        if not newValues['domainname']:
            raise Exception(_("Cannot automatically determine the domain. Please specify the server's fully qualified domain name."))

    isAdMember = 'ad/member' in newValues and 'ad/address' in newValues
    if 'windows/domain' not in newValues and isAdMember:
        MODULE.process('Searching for NETBIOS domain in AD')
        for nameserver in ('nameserver1', 'nameserver2', 'nameserver3'):
            ns = newValues.get(nameserver, ucr.get(nameserver))
            if ns:
                try:
                    ad_domain_info = lookup_adds_dc(newValues.get('ad/address'), ucr={'nameserver1': ns})
                except failedADConnect:
                    pass
                else:
                    newValues['windows/domain'] = ad_domain_info['Netbios Domain']
                    MODULE.process('Setting NETBIOS domain to AD value: %s' % newValues['windows/domain'])
                    break

    domainname = newValues.get("domainname")
    if 'windows/domain' not in newValues and domainname:
        newValues['windows/domain'] = domain2windowdomain(domainname)
        MODULE.process('Setting NETBIOS domain to default: %s' % newValues['windows/domain'])

    # make sure that AD connector package is installed if AD member mode is chosen
    selectedComponents = set(newValues.get('components', []))
    if isAdMember and newValues['server/role'] == 'domaincontroller_master':
        selectedComponents.add('univention-ad-connector')

    # make sure to install the memberof overlay if it is installed on the Primary Directory Node
    if newValues['server/role'] not in ('domaincontroller_master', 'memberserver'):
        selectedComponents.add('univention-ldap-overlay-memberof')

    # add lists with all packages that should be removed/installed on the system
    if selectedComponents:
        currentComponents: set[str] = set()
        for iapp in get_apps():
            if iapp['is_installed']:
                for ipackages in (iapp['default_packages'], iapp['default_packages_master']):
                    currentComponents = currentComponents.union(ipackages)

        # set of all available software packages
        allComponents = {'univention-ldap-overlay-memberof'}
        for iapp in get_apps():
            for ipackages in (iapp['default_packages'], iapp['default_packages_master']):
                allComponents = allComponents.union(ipackages)

        # get all packages that shall be removed
        removeComponents = list(allComponents & (currentComponents - selectedComponents))
        newValues['packages_remove'] = ' '.join(removeComponents)

        # get all packages that shall be installed
        installComponents = list(allComponents & (selectedComponents - currentComponents))
        newValues['packages_install'] = ' '.join(installComponents)

    current_locale = Locale(ucr.get('locale/default', 'en_US.UTF-8:UTF-8').split(':', 1)[0])
    if newValues['server/role'] == 'domaincontroller_master':
        # add newValues for SSL UCR variables
        default_locale = current_locale
        if 'locale/default' in newValues:
            default_locale = Locale(newValues['locale/default'].split(':', 1)[0])
        newValues['ssl/state'] = default_locale.territory
        newValues['ssl/locality'] = default_locale.territory
        newValues['ssl/organization'] = newValues.get('organization', default_locale.territory)
        newValues['ssl/organizationalunit'] = 'Univention Corporate Server'
        newValues['ssl/email'] = 'ssl@{domainname}'.format(**newValues)

    # make sure that the locale of the current session is also supported
    # ... otherwise the setup scripts will fail after regenerating the
    # locale data (in 20_language/10language) with some strange python
    # exceptions about unsupported locale strings...
    if 'locale' not in newValues:
        newValues['locale'] = newValues.get('locale/default', '')
    forcedLocales = ['en_US.UTF-8:UTF-8', 'de_DE.UTF-8:UTF-8']  # we need en_US and de_DE locale as default language
    if current_locale:
        forcedLocales.append(f'{current_locale}:{current_locale.codeset}')
    for ilocale in forcedLocales:
        if ilocale not in newValues['locale']:
            newValues['locale'] = '%s %s' % (newValues['locale'], ilocale)

    return newValues


def pre_save(newValues: dict[str, str]) -> None:
    """Modify the final dict before saving it to the profile file."""
    # network interfaces
    from univention.management.console.modules.setup.network import Interfaces
    if 'interfaces' in newValues:
        interfaces = Interfaces()
        interfaces.from_dict(newValues.pop('interfaces'))
        interfaces.check_consistency()
        newValues.update({key: value or '' for key, value in interfaces.to_ucr().items()})


def write_profile(values: dict[str, str]) -> None:
    pre_save(values)
    old_umask = os.umask(0o177)
    try:
        with open(PATH_PROFILE, "w+") as cache_file:
            for ikey, ival in values.items():
                if isinstance(ival, bool):
                    ival = str(ival)
                cache_file.write('%s="%s"\n' % (ikey, ival or ''))
    finally:
        os.umask(old_umask)


def run_networkscrips(demo_mode: bool = False) -> None:
    # write header before executing scripts
    f = open(LOG_FILE, 'a')
    f.write('\n\n=== RUNNING NETWORK APPLY SCRIPTS (%s) ===\n\n' % timestamp())
    f.flush()

    # make sure that UMC servers and apache will not be restartet
    subprocess.call(CMD_DISABLE_EXEC, stdout=f, stderr=f)

    # If fast demo mode is used, no additional parameters must be provided,
    # as they will prevent ldap modification. The host object has to be updated
    script_parameters = []
    if not demo_mode:
        script_parameters = ['--network-only', '--appliance-mode']

    try:
        netpath = os.path.join(PATH_SETUP_SCRIPTS, '30_net')
        for scriptpath in sorted(os.listdir(netpath)):
            scriptpath = os.path.join(netpath, scriptpath)
            # launch script
            try:
                # appliance-mode for temporary saving the old ip address
                # network-only for not restarting all those services (time consuming!)
                p = subprocess.Popen([scriptpath, *script_parameters], stdout=f, stderr=subprocess.STDOUT)
                MODULE.info("Running script '%s': pid=%d" % (scriptpath, p.pid))
                p.wait()
            except OSError as ex:
                MODULE.error("Failed to run '%s': %s" % (scriptpath, ex))
    finally:
        # enable execution of servers again
        subprocess.call(CMD_ENABLE_EXEC, stdout=f, stderr=f)

    f.write('\n=== DONE (%s) ===\n\n' % timestamp())
    f.close()


@contextmanager
def written_profile(values: dict[str, str]) -> Iterator[None]:
    write_profile(values)
    try:
        yield
    finally:
        os.remove(PATH_PROFILE)


class ProgressState:  # noqa: PLW1641

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.name = ''
        self.message = ''
        self._percentage = 0.0
        self.fraction = 0.0
        self.fractionName = ''
        self.steps = 1
        self.step = 0.0
        self.max = 100
        self.errors: list[str] = []
        self.critical = False

    @property
    def percentage(self) -> float:
        return (self._percentage + self.fraction * (self.step / float(self.steps))) / self.max * 100

    def __eq__(self, other: object) -> bool:
        return self.name == other.name and self.message == other.message and self.percentage == other.percentage and self.fraction == other.fraction and self.steps == other.steps and self.step == other.step and self.errors == other.errors and self.critical == other.critical

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)

    def __bool__(self) -> bool:
        return bool(self.name or self.message or self.percentage)
    __nonzero__ = __bool__


class ProgressParser:
    # regular expressions
    NAME = re.compile('^__NAME__: *(?P<key>[^ ]*) (?P<name>.*)\n$')
    MSG = re.compile('^__MSG__: *(?P<message>.*)\n$')
    STEPS = re.compile('^__STEPS__: *(?P<steps>.*)\n$')
    STEP = re.compile('^__STEP__: *(?P<step>.*)\n$')
    JOINERROR = re.compile('^__JOINERR__: *(?P<error_message>.*)\n$')
    ERROR = re.compile('^__ERR__: *(?P<error_message>.*)\n$')

    # fractions of setup scripts
    FRACTIONS = {
        '05_role/10role': 30,
        '10_basis/12domainname': 15,
        '10_basis/14ldap_basis': 20,
        '20_language/11default_locale': 5,
        '30_net/10interfaces': 20,
        '30_net/12gateway': 10,
        '30_net/13ipv6gateway': 10,
        '40_ssl/10ssl': 10,
        '50_software/10software': 30,
        '90_postjoin/10admember': 30,
        '90_postjoin/20upgrade': 10,
    }

    # current status
    def __init__(self) -> None:
        self.current = ProgressState()
        self.old = ProgressState()
        self.allowed_subdirs: Container[str] | None = None
        self.reset()

    def reset(self, allowed_subdirs: Container[str] | None = None) -> None:
        self.allowed_subdirs = allowed_subdirs
        ucr.load()
        self.current.reset()
        self.old.reset()
        self.fractions = copy.copy(ProgressParser.FRACTIONS)
        self.calculateFractions()

    def calculateFractions(self) -> None:
        MODULE.info('Calculating maximum value for fractions ...')
        for category in [x for x in os.listdir(PATH_SETUP_SCRIPTS) if os.path.isdir(os.path.join(PATH_SETUP_SCRIPTS, x))]:
            cat_path = os.path.join(PATH_SETUP_SCRIPTS, category)
            for script in [x for x in os.listdir(cat_path) if os.path.isfile(os.path.join(cat_path, x))]:
                name = '%s/%s' % (category, script)
                if name not in self.fractions:
                    self.fractions[name] = 1
                if self.allowed_subdirs and category not in self.allowed_subdirs:
                    self.fractions[name] = 0

        self.current.max = sum(self.fractions.values())
        MODULE.info('Calculated a maximum value of %d' % self.current.max)
        MODULE.info('Dumping all fractions:\n%s' % self.fractions)

    @property
    def changed(self) -> bool:
        if self.current != self.old:
            MODULE.info('Progress state has changed!')
            self.old = copy.copy(self.current)
            return True
        return False

    def parse(self, line: str) -> bool:
        # start new component name
        match = ProgressParser.NAME.match(line)
        if match is not None:
            self.current.name, self.current.fractionName = match.groups()
            self.current.message = ''
            self.current._percentage += self.current.fraction
            self.current.fraction = self.fractions.get(self.current.name, 1.0)
            self.current.step = 0  # reset current step
            self.current.steps = 1
            return True

        # new status message
        match = ProgressParser.MSG.match(line)
        if match is not None:
            self.current.message = match.groups()[0]
            return True

        # number of steps
        match = ProgressParser.STEPS.match(line)
        if match is not None:
            try:
                self.current.steps = int(match.groups()[0])
                self.current.step = 0
                return True
            except ValueError:
                pass

        # current step
        match = ProgressParser.STEP.match(line)
        if match is not None:
            try:
                self.current.step = float(match.groups()[0])
                if self.current.step > self.current.steps:
                    self.current.step = self.current.steps
                return True
            except ValueError:
                pass

        # error message: why did the join fail?
        match = ProgressParser.JOINERROR.match(line)
        if match is not None:
            error = '%s: %s\n' % (self.current.fractionName, match.groups()[0])
            with open(PATH_JOIN_LOG, 'rb') as join_log:
                log = join_log.read().decode('UTF-8', 'replace').splitlines(True)
            error_log = []
            for line in reversed(log):
                error_log.append(line)
                if line.startswith('Configure'):
                    break
            for line in reversed(error_log):
                error += line
            self.current.errors.append(error)
            self.current.critical = True
            return True

        # error message: why did the script fail?
        match = ProgressParser.ERROR.match(line)
        if match is not None:
            error = '%s: %s' % (self.current.fractionName, match.groups()[0])
            self.current.errors.append(error)
            return True

        return False


def sorted_files_in_subdirs(directory: str, allowed_subdirs: Container[str] | None = None) -> Iterator[str]:
    for entry in sorted(os.listdir(directory)):
        if allowed_subdirs and entry not in allowed_subdirs:
            continue
        path = os.path.join(directory, entry)
        if os.path.isdir(path):
            for filename in sorted(os.listdir(path)):
                yield os.path.join(path, filename)


def run_scripts(progressParser: ProgressParser, restartServer: bool = False, allowed_subdirs: Container[str] | None = None, lang: str = 'C', args: list[str] = []) -> None:
    # write header before executing scripts
    f = open(LOG_FILE, 'a')
    f.write('\n\n=== RUNNING SETUP SCRIPTS (%s) ===\n\n' % timestamp())
    f.flush()

    # read-only handle to LOG_FILE for observing file end
    fr = open(LOG_FILE)

    # start observing at the end of the file
    fr.seek(0, os.SEEK_END)
    lastPos = fr.tell()

    # next full line to pass to the progressParser
    fullLine = ''

    # make sure that UMC servers and apache will not be restartet
    subprocess.call(CMD_DISABLE_EXEC, stdout=f, stderr=f)

    for scriptpath in sorted_files_in_subdirs(PATH_SETUP_SCRIPTS, allowed_subdirs):
        # launch script
        icmd = [scriptpath, *args]
        f.write('== script: %s\n' % icmd)
        try:
            p = subprocess.Popen(icmd, stdout=f, stderr=subprocess.STDOUT, env={
                'PATH': '/bin:/sbin:/usr/bin:/usr/sbin',
                'LANG': lang,
            })
            MODULE.info("Running script '%s': pid=%d" % (icmd, p.pid))
        except OSError as exc:
            MODULE.error("Failed to run '%s': %s" % (icmd, exc))
            continue
        while p.poll() is None:
            fr.seek(0, os.SEEK_END)  # update file handle
            fr.seek(lastPos, os.SEEK_SET)  # continue reading at last position

            currentLine = fr.readline()  # try to read until next line break
            if not currentLine:
                continue

            fullLine += currentLine
            lastPos += len(currentLine)
            if currentLine[-1] == '\n':
                progressParser.parse(fullLine)
                fullLine = ''

    fr.close()

    # Deactivate login message
    univention.config_registry.handler_set(['system/setup/showloginmessage=false'])

    # enable execution of servers again
    subprocess.call(CMD_ENABLE_EXEC, stdout=f, stderr=f)

    if restartServer:
        f.write('=== Restart of UMC server and web server (%s) ===\n' % timestamp())
        f.flush()
        p = subprocess.Popen(['/usr/bin/at', 'now'], stdin=subprocess.PIPE, stderr=f, stdout=f)
        p.communicate(b'''#!/bin/sh
sleep 5;  # leave enough time to display error messages or indicate success
deb-systemd-invoke restart univention-management-console-server;''')

    f.write('\n=== DONE (%s) ===\n\n' % timestamp())
    f.close()


@contextmanager
def _temporary_password_file(password: str) -> Iterator[str]:
    # write password file
    with open(PATH_PASSWORD_FILE, 'w') as fp:
        fp.write('%s' % password)
    os.chmod(PATH_PASSWORD_FILE, 0o600)
    try:
        yield PATH_PASSWORD_FILE
    finally:
        # remove password file
        os.remove(PATH_PASSWORD_FILE)


def run_joinscript(progressParser: ProgressParser, values: dict[str, str], _username: str, password: str, dcname: str | None = None, lang: str = 'C') -> None:
    # write header before executing join script
    f = open(LOG_FILE, 'a')
    f.write('\n\n=== RUNNING SETUP JOIN SCRIPT (%s) ===\n\n' % timestamp())
    f.flush()

    # the following scripts will not be called via setup-join.sh
    progressParser.fractions['10_basis/10hostname'] = 0
    progressParser.fractions['10_basis/12domainname'] = 0
    progressParser.fractions['10_basis/14ldap_basis'] = 0
    progressParser.fractions['10_basis/16windows_domain'] = 0

    # check whether particular scripts are called
    if not values.get('ad/member'):
        progressParser.fractions['90_postjoin/10admember'] = 0
    if not values.get('update/system/after/setup'):
        progressParser.fractions['90_postjoin/20upgrade'] = 0
    if not values.get('packages_remove') and not values.get('packages_install'):
        progressParser.fractions['50_software/10software'] = 0

    # additional entries that will be called via setup-join.sh
    progressParser.fractions['domain-join'] = 50
    progressParser.fractions['appliance-hooks.d'] = 1
    progressParser.fractions['create-ssh-keys'] = 10

    # recompute sum
    progressParser.current.max = sum(progressParser.fractions.values())

    def runit(command):
        p = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env={
            'PATH': '/bin:/sbin:/usr/bin:/usr/sbin',
            'LANG': lang,
        })
        while True:
            line = p.stdout.readline().decode("UTF-8", "replace")
            if not line:
                break
            progressParser.parse(line)
            f.write(line)
            f.flush()
        p.wait()

    cmd = [PATH_JOIN_SCRIPT]
    if _username and password:
        if dcname:
            cmd.extend(['--dcname', dcname])

        with _temporary_password_file(password) as password_file:
            # sanitize username
            reg = re.compile('[^ a-zA-Z_0-9-]')
            username = reg.sub('_', _username)

            # run join scripts without the cleanup scripts
            runit([*cmd, '--dcaccount', username, '--password_file', password_file, '--run_cleanup_as_atjob'])

    else:
        # run join scripts without the cleanup scripts
        runit([*cmd, '--run_cleanup_as_atjob'])

    f.write('\n=== DONE (%s) ===\n\n' % timestamp())
    f.close()


def cleanup(with_appliance_hooks: bool = False) -> None:
    # add delay of 1 sec before actually executing the commands
    # in order to avoid problems with restarting the UMC server
    # and thus killing the setup module process
    cmd = 'sleep 1; '
    if with_appliance_hooks:
        cmd += CMD_APPLIANCE_HOOKS + '; '
    cmd += CMD_CLEANUP_SCRIPT

    # start an at job in the background
    atjobs.add(cmd)


def run_scripts_in_path(path: str, logfile: IO[str], category_name: str = "") -> None:
    logfile.write('\n=== Running %s scripts (%s) ===\n' % (category_name, timestamp()))
    logfile.flush()

    if os.path.isdir(path):
        for filename in sorted(os.listdir(path)):
            logfile.write('= Running %s\n' % filename)
            logfile.flush()
            try:
                subprocess.call(os.path.join(path, filename), stdout=logfile, stderr=logfile)
            except OSError:
                logfile.write('%s' % (traceback.format_exc(),))
            logfile.flush()

    logfile.write('\n=== done (%s) ===\n' % timestamp())
    logfile.flush()


def create_status_file() -> None:
    with open(PATH_STATUS_FILE, 'w') as status_file:
        status_file.write('"setup-scripts"')


def detect_interfaces() -> list[dict[str, str | None]]:
    """
    Function to detect network interfaces in local sysfs.
    The loopback interface "lo" will be filtered out.
    Returns a list of dicts with the entries 'name' and 'mac'.
    """
    interfaces: list[dict[str, str | None]] = []

    if not os.path.exists(PATH_SYS_CLASS_NET):
        return interfaces
    for dirname in os.listdir(PATH_SYS_CLASS_NET):
        pathname = os.path.join(PATH_SYS_CLASS_NET, dirname)
        if not os.path.isdir(pathname):
            continue
        # filter out lo, etc. interfaces
        if open(os.path.join(pathname, 'type')).read().strip() not in ('1', '2', '3', '4', '5', '6', '7', '8', '15', '19'):
            continue
        # filter out bridge, bond, tun/tap interfaces
        if any(os.path.exists(os.path.join(pathname, path)) for path in ('bridge', 'bonding', 'brport', 'tun_flags')):
            continue
        # filter out vlan devices
        if '.' in dirname:
            continue
        mac = None
        try:
            # try to read mac address
            mac = open(os.path.join(pathname, 'address')).read().strip()
        except OSError:
            pass
        interfaces.append({'name': dirname, 'mac': mac})

    return interfaces


def dhclient(interface: str, timeout: float = 10.0) -> dict[str, str]:
    """
    perform DHCP request for specified interface. If successful, returns a dict
    similar to the following::

        {
            'address': '10.200.26.51',
            'broadcast': '10.200.26.255',
            'domainname': 'univention.qa',
            'gateway': '',
            'nameserver_1': '10.200.26.27',
            'nameserver_2': '',
            'nameserver_3': '',
            'netmask': '255.255.255.0'
        }
    """
    dhcp = {}

    with tempfile.NamedTemporaryFile("w+") as tmp:
        cmd = (
            '/usr/bin/timeout', '-k', '1', str(timeout),
            '/sbin/dhclient',
            "-q",
            "-d",  # force dhclient to always run as a foreground process
            '-1',
            '-lf', '/tmp/dhclient.leases',
            '-sf', '/usr/share/univention-system-setup/dhclient-script-wrapper',
            '-e', 'dhclientscript_outputfile=%s' % (tmp.name,),
            interface,
        )
        MODULE.info('Launch dhclient query via command: %s' % (cmd, ))
        subprocess.call(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        for line in tmp:
            key, _, value = line.strip().partition('=')
            dhcp[key] = value[1:-1]

    MODULE.info('dhclient returned the following values: %r' % (dhcp,))

    return dhcp


def get_apps(no_cache: bool = False) -> list[dict[str, Any]]:
    if no_cache:
        AppCache().clear_cache()
    get = get_action('get')
    return [get.to_dict(app) for app in Apps().get_all_apps() if app.is_ucs_component()]


def is_proxy(proxy: str) -> bool:
    return not (proxy and proxy not in {'http://', 'https://'} and not proxy.startswith('http://') and not proxy.startswith('https://'))


def is_ipaddr(addr: str) -> bool:
    try:
        ipaddress.ip_address('%s' % (addr,))
    except ValueError:
        return False
    return True


def is_ipv4addr(addr: str) -> bool:
    try:
        ipaddress.IPv4Address('%s' % (addr,))
    except ValueError:
        return False
    return True


def is_ipv4netmask(addr_netmask: str) -> bool:
    try:
        ipaddress.IPv4Network('%s' % (addr_netmask,), False)
    except (ValueError, ipaddress.NetmaskValueError, ipaddress.AddressValueError):
        return False
    return True


def is_ipv6addr(addr: str) -> bool:
    try:
        ipaddress.IPv6Address('%s' % (addr,))
    except ValueError:
        return False
    return True


def is_ipv6netmask(addr_netmask: str) -> bool:
    try:
        ipaddress.IPv6Network('%s' % (addr_netmask,), False)
    except (ValueError, ipaddress.NetmaskValueError, ipaddress.AddressValueError):
        return False
    return True


def is_hostname(hostname: str) -> bool:
    return is_hostname.RE.match(hostname) is not None  # type: ignore


is_hostname.RE = re.compile("^[a-z0-9]([a-z0-9-]*[a-z0-9])?$", re.IGNORECASE)  # type: ignore


def is_domainname(domainname: str) -> bool:
    """
    Check if domainname is a valid DNS domainname according to RFC952/1123.
    >>> is_domainname('foo')
    True
    >>> is_domainname('f00.bar')
    True
    >>> is_domainname('-f.bar')
    False
    >>> is_domainname('f-.bar')
    False
    >>> is_domainname('f..bar')
    False
    >>> is_domainname('#.bar')
    False
    >>> is_domainname('1234567890123456789012345678901234567890123456789012345678901234.bar')
    False
    """
    return all(is_domainname.RE.match(_) for _ in domainname.split('.'))  # type: ignore


is_domainname.RE = re.compile(r'^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$', re.I)  # type: ignore


def is_windowsdomainname(domainname: str) -> bool:
    return is_windowsdomainname.RE.match(domainname) is not None and len(domainname) < 14  # type: ignore


is_windowsdomainname.RE = re.compile(r"^[A-Z](?:[A-Z0-9-]*[A-Z0-9])?$")  # type: ignore


def domain2windowdomain(domainname: str) -> str:
    windomain = domainname.split('.', 1)[0].upper()

    invalidChars = re.compile(r"^[^A-Z]*([A-Z0-9-]*?)[^A-Z0-9]*$")
    match = invalidChars.match(windomain)
    windomain = match.group(1) if match else ''

    windomain = windomain[:15]  # enforce netbios limit

    if not windomain:
        # fallback name
        windomain = 'UCSDOMAIN'
    return windomain


def is_domaincontroller(domaincontroller: str) -> bool:
    return is_domaincontroller.RE.match(domaincontroller) is not None  # type: ignore


is_domaincontroller.RE = re.compile(r"^[a-zA-Z].*\..*$")  # type: ignore


def is_ldap_base(ldap_base: str) -> bool:
    """
    >>> is_ldap_base('dc=foo,dc=bar')
    True
    >>> is_ldap_base('cn=foo,c=De,dc=foo,dc=bar')
    True
    >>> is_ldap_base('cn=foo,c=DED,dc=foo,dc=bar')
    False
    >>> is_ldap_base('dc=foo,')
    False
    >>> is_ldap_base(',dc=bar')
    False
    >>> is_ldap_base('dc=foo')
    False
    >>> is_ldap_base('cn=foo,c=ZZ,dc=foo,dc=bar')
    False
    """
    match = is_ldap_base.RE.match(ldap_base)  # type: ignore
    return match is not None and not any(part.upper().startswith('C=') and part.upper()[2:] not in is_ldap_base.CC for part in ldap.dn.explode_dn(ldap_base))  # type: ignore


is_ldap_base.RE = re.compile('^(c=[A-Za-z]{2}|(dc|cn|o|l)=[a-zA-Z0-9-]+)(,(c=[A-Za-z]{2}|((dc|cn|o|l)=[a-zA-Z0-9-]+)))+$')  # type: ignore
is_ldap_base.CC = ['AD', 'AE', 'AF', 'AG', 'AI', 'AL', 'AM', 'AO', 'AQ', 'AR', 'AS', 'AT', 'AU', 'AW', 'AX', 'AZ', 'BA', 'BB', 'BD', 'BE', 'BF', 'BG', 'BH', 'BI', 'BJ', 'BL', 'BM', 'BN', 'BO', 'BQ', 'BR', 'BS', 'BT', 'BV', 'BW', 'BY', 'BZ', 'CA', 'CC', 'CD', 'CF', 'CG', 'CH', 'CI', 'CK', 'CL', 'CM', 'CN', 'CO', 'CR', 'CU', 'CV', 'CW', 'CX', 'CY', 'CZ', 'DE', 'DJ', 'DK', 'DM', 'DO', 'DZ', 'EC', 'EE', 'EG', 'EH', 'ER', 'ES', 'ET', 'FI', 'FJ', 'FK', 'FM', 'FO', 'FR', 'GA', 'GB', 'GD', 'GE', 'GF', 'GG', 'GH', 'GI', 'GL', 'GM', 'GN', 'GP', 'GQ', 'GR', 'GS', 'GT', 'GU', 'GW', 'GY', 'HK', 'HM', 'HN', 'HR', 'HT', 'HU', 'ID', 'IE', 'IL', 'IM', 'IN', 'IO', 'IQ', 'IR', 'IS', 'IT', 'JE', 'JM', 'JO', 'JP', 'KE', 'KG', 'KH', 'KI', 'KM', 'KN', 'KP', 'KR', 'KW', 'KY', 'KZ', 'LA', 'LB', 'LC', 'LI', 'LK', 'LR', 'LS', 'LT', 'LU', 'LV', 'LY', 'MA', 'MC', 'MD', 'ME', 'MF', 'MG', 'MH', 'MK', 'ML', 'MM', 'MN', 'MO', 'MP', 'MQ', 'MR', 'MS', 'MT', 'MU', 'MV', 'MW', 'MX', 'MY', 'MZ', 'NA', 'NC', 'NE', 'NF', 'NG', 'NI', 'NL', 'NO', 'NP', 'NR', 'NU', 'NZ', 'OM', 'PA', 'PE', 'PF', 'PG', 'PH', 'PK', 'PL', 'PM', 'PN', 'PR', 'PS', 'PT', 'PW', 'PY', 'QA', 'RE', 'RO', 'RS', 'RU', 'RW', 'SA', 'SB', 'SC', 'SD', 'SE', 'SG', 'SH', 'SI', 'SJ', 'SK', 'SL', 'SM', 'SN', 'SO', 'SR', 'SS', 'ST', 'SV', 'SX', 'SY', 'SZ', 'TC', 'TD', 'TF', 'TG', 'TH', 'TJ', 'TK', 'TL', 'TM', 'TN', 'TO', 'TR', 'TT', 'TV', 'TW', 'TZ', 'UA', 'UG', 'UM', 'US', 'UY', 'UZ', 'VA', 'VC', 'VE', 'VG', 'VI', 'VN', 'VU', 'WF', 'WS', 'YE', 'YT', 'ZA', 'ZM', 'ZW']  # type: ignore

# new defined methods


def is_ascii(string: str) -> bool:
    try:
        string.encode("ascii")
        return True
    except UnicodeEncodeError:
        return False


def _get_dns_resolver(nameserver: str) -> dns.resolver.Resolver:
    resolver = dns.resolver.Resolver()
    resolver.lifetime = 10  # make sure that we get an early timeout
    resolver.nameservers = [nameserver]
    return resolver


def is_ucs_domain(nameserver: str, domain: str) -> bool:
    return bool(get_ucs_domaincontroller_master_query(nameserver, domain))


def get_ucs_domaincontroller_master_query(nameserver: str, domain: str) -> dns.resolver.Answer | None:
    if not nameserver or not domain:
        return None

    # register nameserver
    resolver = _get_dns_resolver(nameserver)

    # perform a SRV lookup
    try:
        return resolver.query('_domaincontroller_master._tcp.%s.' % domain, 'SRV')
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers):
        MODULE.warn('No valid UCS domain (%s) at nameserver %s!' % (domain, nameserver))
    except dns.exception.Timeout as exc:
        MODULE.warn('Lookup for Primary Directory Node record at nameserver %s timed out: %s' % (nameserver, exc))
    except dns.exception.DNSException:
        MODULE.error('DNS Exception: %s' % (traceback.format_exc()))
    return None


def resolve_domaincontroller_master_srv_record(nameserver: str, domain: str) -> bool:
    response = get_ucs_domaincontroller_master_query(nameserver, domain)
    if not response:
        return False
    try:
        return response[0].target.to_text().rstrip('.')
    except LookupError:
        return False


def is_ssh_reachable(host: str) -> bool:
    if not host:
        return False
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        # TODO: timeout?
        s.connect((host, 22))
        return True
    except OSError:
        pass
    finally:
        try:
            s.close()
        except OSError:
            pass
    return False


def get_ucs_domain(nameserver: str) -> str:
    domain = get_domain(nameserver)
    if not is_ucs_domain(nameserver, domain):
        return ""
    return domain


def get_domain(nameserver: str) -> str:
    fqdn = get_fqdn(nameserver) or ""
    _, _, domain = fqdn.partition(".")
    return domain


def get_fqdn(nameserver: str) -> str | None:
    # register nameserver
    resolver = _get_dns_resolver(nameserver)

    # perform a reverse lookup
    try:
        reverse_address = dns.reversename.from_address(nameserver)
        MODULE.info('Found reverse address: %s' % (reverse_address,))
        reverse_lookup = resolver.query(reverse_address, 'PTR')
        if not len(reverse_lookup):
            return None

        fqdn = reverse_lookup[0]
        parts = [i.decode('ASCII') for i in fqdn.target.labels if i]
        domain = '.'.join(parts)

        return domain
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers) as exc:
        MODULE.warn('Lookup for nameserver %s failed: %s %s' % (nameserver, type(exc).__name__, exc))
    except dns.exception.Timeout as exc:
        MODULE.warn('Lookup for nameserver %s timed out: %s' % (nameserver, exc))
    except dns.exception.DNSException:
        MODULE.error('DNS Exception: %s' % (traceback.format_exc()))
    return None


def get_available_locales(pattern: Pattern[str], category: str = 'language_en') -> list[dict[str, str]] | None:
    """Return a list of all available locales."""
    try:
        fsupported = open('/usr/share/i18n/SUPPORTED')
        flanguages = open('/usr/share/univention-system-setup/locale/languagelist')
    except Exception:
        MODULE.error('Cannot find locale data for languages in /usr/share/univention-system-setup/locale')
        return None

    # get all locales that are supported
    rsupported = csv.reader(fsupported, delimiter=' ')
    supportedLocales = {'C': True}
    for ilocale in rsupported:
        # we only support UTF-8
        if ilocale[1] != 'UTF-8':
            continue

        # get the locale
        m = RE_LOCALE.match(ilocale[0])
        if m:
            supportedLocales[m.groups()[0]] = True

    column = {'langcode': 0, 'language_en': 1, 'language': 2, 'countrycode': 4, 'fallbacklocale': 5}.get(category, 1)

    # open all languages
    rlanguages = csv.reader(flanguages, delimiter=';')
    locales = []
    for ilang in rlanguages:
        if ilang[0].startswith('#'):
            continue

        if not pattern.match(ilang[column]):
            continue

        # each language might be spoken in several countries
        ipath = '/usr/share/univention-system-setup/locale/short-list/%s.short' % ilang[0]
        if os.path.exists(ipath):
            try:
                # open the short list with countries belonging to the language
                fshort = open(ipath)
                rshort = csv.reader(fshort, delimiter='\t')

                # create for each country a locale entry
                for jcountry in rshort:
                    code = '%s_%s' % (ilang[0], jcountry[0])
                    if code in supportedLocales:
                        locales.append({
                            'id': '%s.UTF-8:UTF-8' % code,
                            'label': '%s (%s)' % (ilang[1], jcountry[2]),
                        })
                continue
            except Exception:
                pass

        # get the locale code
        code = ilang[0]
        if code.find('_') < 0 and code != 'C':
            # no underscore -> we need to build the locale ourself
            code = '%s_%s' % (ilang[0], ilang[4])

        # final entry
        if code in supportedLocales:
            locales.append({
                'id': '%s.UTF-8:UTF-8' % code,
                'label': ilang[1],
            })

    return locales


_city_data = None


def get_city_data() -> Any:
    global _city_data
    if not _city_data:
        with open(CITY_DATA_PATH) as infile:
            _city_data = json.load(infile)
    return _city_data


_country_data = None


def get_country_data() -> Any:
    global _country_data
    if not _country_data:
        with open(COUNTRY_DATA_PATH) as infile:
            _country_data = json.load(infile)
    return _country_data


def get_random_nameserver(country: Mapping[str, Any]) -> dict[str, str | None]:
    ipv4_servers = country.get('ipv4') or country.get('ipv4_erroneous') or [None]
    ipv6_servers = country.get('ipv6') or country.get('ipv6_erroneous') or [None]
    return {
        "ipv4_nameserver": random.choice(ipv4_servers),
        "ipv6_nameserver": random.choice(ipv6_servers),
    }


def check_credentials_ad(nameserver: str, address: str, username: str, password: str) -> str:
    try:
        ad_domain_info = lookup_adds_dc(address, ucr={'nameserver1': nameserver})
        check_connection(ad_domain_info, username, password)
        do_time_sync(address)
        check_ad_account(ad_domain_info, username, password)
    except failedADConnect:
        # Not checked... no AD!
        raise UMC_Error(_('The connection to the Active Directory server failed. Please recheck the address.'))
    except connectionFailed:
        # checked: failed!
        raise UMC_Error(_('The connection to the Active Directory server was refused. Please recheck the password.'))
    except notDomainAdminInAD:  # check_ad_account()
        # checked: Not a Domain Administrator!
        raise UMC_Error(_("The given user is not member of the Domain Admins group in Active Directory. This is a requirement for the Active Directory domain join."))
    else:
        return ad_domain_info['Domain']
