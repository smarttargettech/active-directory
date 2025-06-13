#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import shlex
import subprocess
import traceback
from typing import Any

from packaging.version import Version

import univention.config_registry
from univention.lib.i18n import Translation
from univention.management.console.log import MODULE
from univention.management.console.modules import UMC_Error
from univention.management.console.modules.setup.util import _temporary_password_file, get_ucs_domain


UCR = univention.config_registry.ConfigRegistry()
UCR.load()
_ = Translation('univention-management-console-module-setup').translate


def set_role_and_check_if_join_will_work(role: str, master_fqdn: str, admin_username: str, admin_password: str) -> None:
    orig_role = UCR.get('server/role')
    try:
        univention.config_registry.handler_set(['server/role=%s' % (role,)])

        with _temporary_password_file(admin_password) as password_file:
            p1 = subprocess.Popen([
                'univention-join',
                '-dcname', master_fqdn,
                '-dcaccount', admin_username,
                '-dcpwd', password_file,
                '-checkPrerequisites',
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
            stdout, _stderr = p1.communicate()
            if p1.returncode != 0:
                messages = [line[11:] for line in stdout.decode("UTF-8", "replace").split('\n') if line.startswith("* Message: ")]
                raise UMC_Error(_(
                    "univention-join -checkPrerequisites reported a problem. "
                    "Output of check:\n\n",
                ) + "\n".join(messages))
    finally:
        if orig_role:
            univention.config_registry.handler_set(['server/role=%s' % (orig_role,)])
        else:
            univention.config_registry.handler_unset(['server/role'])


def receive_domaincontroller_master_information(dns: str, nameserver: str, address: str, username: str, password: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    result['domain'] = check_credentials_nonmaster(dns, nameserver, address, username, password)
    check_domain_has_activated_license(address, username, password)
    check_domain_is_higher_or_equal_version(address, username, password)
    return result


def check_credentials_nonmaster(dns: str, nameserver: str, address: str, username: str, password: str) -> str:
    domain = get_ucs_domain(nameserver) if dns else '.'.join(address.split('.')[1:])
    if not domain:
        # Not checked... no UCS domain!
        raise UMC_Error(_('No UCS Primary Directory Node could be found at the address.'))
    with _temporary_password_file(password) as password_file:
        if subprocess.call(['univention-ssh', password_file, '%s@%s' % (username, address), '/bin/true']):
            raise UMC_Error(_('The connection to the UCS Primary Directory Node was refused. Please recheck the password.'))
        return domain


def check_domain_has_activated_license(address: str, username: str, password: str) -> None:
    appliance_name = UCR.get("umc/web/appliance/name")
    if not appliance_name:
        return  # the license must only be checked in an appliance scenario

    valid_license = True
    error = None
    with _temporary_password_file(password) as password_file:
        try:
            license_uuid = subprocess.check_output([
                'univention-ssh',
                password_file,
                '%s@%s' % (username, address),
                '/usr/sbin/ucr',
                'get',
                'uuid/license',
            ], stderr=subprocess.STDOUT).decode('UTF-8').rstrip()
        except subprocess.CalledProcessError as exc:
            valid_license = False
            error = exc.output.decode("UTF-8")
        else:
            valid_license = len(license_uuid) == 36
            error = _('The license %s is not valid.') % (license_uuid,)

    if not valid_license:
        raise UMC_Error(' '.join((
            _('To install the {appliance_name} appliance it is necessary to have an activated UCS license on the Primary Directory Node.').format(appliance_name=appliance_name),
            _('During the check of the license status the following error occurred:\n{error}').format(error=error),
        )))


def check_domain_is_higher_or_equal_version(address: str, username: str, password: str) -> None:
    with _temporary_password_file(password) as password_file:
        try:
            master_ucs_version = subprocess.check_output(['univention-ssh', password_file, '%s@%s' % (username, address), 'echo $(/usr/sbin/ucr get version/version)-$(/usr/sbin/ucr get version/patchlevel)'], stderr=subprocess.STDOUT).rstrip().decode('UTF-8', 'replace')
        except subprocess.CalledProcessError:
            MODULE.error('Failed to retrieve UCS version: %s' % (traceback.format_exc(),))
            return
        nonmaster_ucs_version = '{}-{}'.format(UCR.get('version/version'), UCR.get('version/patchlevel'))
        if Version(nonmaster_ucs_version) > Version(master_ucs_version):
            raise UMC_Error(_('The UCS version of the domain you are trying to join ({}) is lower than the local one ({}). This constellation is not supported.').format(master_ucs_version, nonmaster_ucs_version))


def check_for_school_domain(hostname: str, address: str, username: str, password: str) -> dict[str, Any]:
    MODULE.process('univention-join:school: check_for_school_domain(%r, %r, %r, %r)' % (hostname, address, username, '$PASSWORD'))
    is_school_multiserver_domain = check_is_school_multiserver_domain(address, username, password)
    if is_school_multiserver_domain:
        server_school_roles = get_server_school_roles(hostname, address, username, password)
    else:
        server_school_roles = []
    MODULE.process('univention-join:school: check_for_school_domain = %r' % ({'server_school_roles': server_school_roles, 'is_school_multiserver_domain': is_school_multiserver_domain}, ))
    return {'server_school_roles': server_school_roles, 'is_school_multiserver_domain': is_school_multiserver_domain}


def check_is_school_multiserver_domain(address: str, username: str, password: str) -> bool:
    MODULE.process('univention-join:school: check_is_school_multiserver_domain(%r, %r, %r)' % (address, username, '$PASSWORD'))
    is_school_multiserver_domain = False
    with _temporary_password_file(password) as password_file:
        try:
            master_hostdn = subprocess.check_output([
                'univention-ssh',
                password_file,
                '%s@%s' % (username, address),
                '/usr/sbin/univention-config-registry',
                'get',
                'ldap/hostdn',
            ]).strip().decode('UTF-8')
            ldap_base = subprocess.check_output([
                'univention-ssh',
                password_file,
                '%s@%s' % (username, address),
                '/usr/sbin/univention-config-registry',
                'get',
                'ldap/base',
            ]).strip().decode('UTF-8')
            remote_cmd = ' '.join(shlex.quote(x) for x in [
                'univention-ldapsearch',
                '-D',
                f'cn=admin,{ldap_base}',
                '-y',
                '/etc/ldap.secret',
                '-b',
                f'{master_hostdn}',
                '(&(ucsschoolRole=dc_master:school:-)(!(ucsschoolRole=single_master:school:-))(univentionService=UCS@school))',
                'dn',
            ])
            is_school_multiserver_domain = f'dn: {master_hostdn}' in subprocess.check_output([
                'univention-ssh',
                '--no-split',
                password_file,
                '%s@%s' % (username, address),
                remote_cmd,
            ]).strip().decode('UTF-8').splitlines()
        except subprocess.CalledProcessError as exc:
            MODULE.error('univention-join:school: Could not query Primary Directory Node if the domain is a multiserver school domain: %s' % (exc,))
    MODULE.process('univention-join:school: check_is_school_multiserver_domain = %r' % (is_school_multiserver_domain, ))
    return is_school_multiserver_domain


def get_server_school_roles(hostname: str, address: str, username: str, password: str) -> list[str]:
    MODULE.process('univention-join:school: get_server_school_roles(%r, %r, %r, %r)' % (hostname, address, username, '$PASSWORD'))
    school_roles = []
    with _temporary_password_file(password) as password_file:
        try:
            ldap_base = subprocess.check_output([
                'univention-ssh',
                password_file,
                '%s@%s' % (username, address),
                '/usr/sbin/univention-config-registry',
                'get',
                'ldap/base',
            ]).strip().decode('UTF-8')
            remote_cmd = ' '.join(shlex.quote(x) for x in [
                'univention-ldapsearch',
                '-D',
                f'cn=admin,{ldap_base}',
                '-y',
                '/etc/ldap.secret',
                '-LLL',
                f'(uid={hostname}$)',
                'ucsschoolRole',
            ])
            school_roles = subprocess.check_output([
                'univention-ssh',
                '--no-split',
                password_file,
                '%s@%s' % (username, address),
                remote_cmd,
            ]).strip().decode('UTF-8').splitlines()[1:]
            school_roles = [role.split()[-1] for role in school_roles]
        except (subprocess.CalledProcessError, IndexError) as exc:
            MODULE.error('univention-join:school: Could not query Primary Directory Node for ucsschoolRole: %s' % (exc,))
    MODULE.process('univention-join:school: get_server_school_roles = %r' % (school_roles, ))
    return school_roles
