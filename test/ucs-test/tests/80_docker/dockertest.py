#
# UCS test
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2015-2025 Univention GmbH
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

import os
import shutil
import subprocess
import threading

import requests

from univention.config_registry import ConfigRegistry, handler_set
from univention.testing import umc
from univention.testing.debian_package import DebianPackage
from univention.testing.strings import random_name, random_version
from univention.testing.ucr import UCSTestConfigRegistry


class UCSTest_Docker_Exception(Exception):
    pass


class UCSTest_Docker_LoginFailed(Exception):
    pass


class UCSTest_Docker_PullFailed(Exception):
    pass


class AppcenterMetainfAlreadyExists(Exception):
    pass


class AppcenterRepositoryAlreadyExists(Exception):
    pass


class UCSTest_DockerApp_InstallationFailed(Exception):
    pass


class UCSTest_DockerApp_ConfigureFailed(Exception):
    pass


class UCSTest_DockerApp_UpdateFailed(Exception):
    pass


class UCSTest_DockerApp_UpgradeFailed(Exception):
    pass


class UCSTest_DockerApp_VerifyFailed(Exception):
    pass


class UCSTest_DockerApp_RemoveFailed(Exception):
    pass


class UCSTest_DockerApp_ModProxyFailed(Exception):
    pass


class UCTTest_DockerApp_UMCInstallFailed(Exception):
    pass


class UCSTest_DockerApp_RegisterFailed(Exception):
    pass


def tiny_app(name=None, version=None):
    name = name or get_app_name()
    version = version or '1'
    app = App(name=name, version=version, build_package=False)
    app.set_ini_parameter(
        DockerImage='docker-test.software-univention.de/alpine:3.6',
        DockerScriptInit='/sbin/init',
        DockerScriptSetup='',
        DockerScriptStoreData='',
        DockerScriptRestoreDataBeforeSetup='',
        DockerScriptRestoreDataAfterSetup='',
        DockerScriptUpdateAvailable='',
        DockerScriptUpdatePackages='',
        DockerScriptUpdateRelease='',
        DockerScriptUpdateAppVersion='',
    )
    return app


def tiny_app_apache(name=None, version=None):
    name = name or get_app_name()
    version = version or '1'
    app = App(name=name, version=version, build_package=False)
    app.set_ini_parameter(
        DockerImage='docker-test.software-univention.de/nimmis/alpine-apache',
        DockerScriptInit='/boot.sh',
        DockerScriptSetup='',
        DockerScriptStoreData='',
        DockerScriptRestoreDataBeforeSetup='',
        DockerScriptRestoreDataAfterSetup='',
        DockerScriptUpdateAvailable='',
        DockerScriptUpdatePackages='',
        DockerScriptUpdateRelease='',
        DockerScriptUpdateAppVersion='',
    )
    return app


def docker_login(server='docker.software-univention.de'):
    cmd = ['docker', 'login', '-u', 'ucs', '-p', 'readonly', server]
    error_handling_call(cmd, exc=UCSTest_Docker_LoginFailed)


def docker_pull(image, server='docker.software-univention.de'):
    cmd = ['docker', 'pull', '%s/%s' % (server, image)]
    error_handling_call(cmd, exc=UCSTest_Docker_PullFailed)


def docker_image_is_present(imgname):
    cmd = ['docker', 'inspect', imgname]
    return subprocess.call(cmd, stdout=subprocess.DEVNULL) == 0


def remove_docker_image(imgname):
    cmd = ['docker', 'rmi', imgname]
    return subprocess.call(cmd) == 0


def pull_docker_image(imgname):
    cmd = ['docker', 'pull', imgname]
    return subprocess.call(cmd) == 0


def restart_docker():
    cmd = ['systemctl', 'restart', 'docker']
    return subprocess.call(cmd) == 0


def get_app_name():
    """returns a valid app name"""
    return random_name()


def get_app_version():
    return random_version()


def copy_package_to_appcenter(ucs_version, app_directory, package_name):
    target = os.path.join('/var/www/univention-repository/%s/maintained/component' % ucs_version, '%s/all' % app_directory)
    print('cp %s %s' % (package_name, target))
    if not os.path.exists(target):
        os.makedirs(target)
    shutil.copy(package_name, target)
    command = '''
        set -x -e;
        cd /var/www/univention-repository/%(version)s/maintained/component;
        apt-ftparchive packages %(app)s/all >%(app)s/all/Packages;
        gzip -c %(app)s/all/Packages >%(app)s/all/Packages.gz
    ''' % {'version': ucs_version, 'app': app_directory}
    print('Creating packages in local repository:')
    print(command)
    print(subprocess.check_output(command, shell=True, text=True))


def error_handling_call(*args, exc=Exception, **kwargs):
    try:
        print(subprocess.check_output(*args, **kwargs, stderr=subprocess.STDOUT).decode('UTF-8', 'replace'))
    except subprocess.CalledProcessError as ex:
        raise exc('%s: %s' % (ex, ex.output.decode('UTF-8', 'replace')))


class App:

    def __init__(self, name, version, container_version=None, app_directory_suffix=None, package_name=None, build_package=True, call_join_scripts=True):
        self.app_name = name
        self.app_version = version
        self.call_join_scripts = call_join_scripts
        self.app_directory_suffix = app_directory_suffix or random_version()
        self.app_directory = '%s_%s' % (self.app_name, self.app_directory_suffix)
        self.package_name = package_name or get_app_name()
        self.package_version = '%s.%s' % (version, get_app_version())

        self.ucr = ConfigRegistry()
        self.ucr.load()

        if build_package:
            self.package = DebianPackage(name=self.package_name, version=self.package_version)
            self.package.build()
        else:
            self.package = None

        self.ini = {
            'ID': self.app_name,
            'Code': self.app_name[0:2],
            'Name': self.app_name,
            'Version': self.app_version,
            'NotifyVendor': False,
            'Categories': 'System services',
            'Logo': '%s.svg' % self.app_name,
            'ServerRole': 'domaincontroller_master,domaincontroller_backup,domaincontroller_slave,memberserver',
        }
        if self.package:
            self.ini['DefaultPackages'] = self.package_name

        self.scripts = {}

        if not container_version:
            self.ucs_version = self.ucr.get('version/version')
        else:
            self.ucs_version = container_version
            # make sure version of default appbox image is part of SupportedUCSVersions
            self.ini['SupportedUCSVersions'] = '%s-0,4.3-0,%s-0' % (container_version, self.ucr.get('version/version'))

        self.installed = False

        self.admin_user = self.ucr.get('tests/domainadmin/account').split(',')[0][len('uid='):]
        self.admin_pwdfile = self.ucr.get('tests/domainadmin/pwdfile')

        print(repr(self))

    def __repr__(self):
        return '%s(app_name=%r, app_version=%r)' % (self.__class__.__name__, self.app_name, self.app_version)

    def set_ini_parameter(self, **kwargs):
        for key, value in kwargs.items():
            print('set_ini_parameter(%s=%s)' % (key, value))
            self.ini[key] = value

    def add_to_local_appcenter(self):
        self._dump_ini()
        if self.package:
            copy_package_to_appcenter(self.ucs_version, self.app_directory, self.package.get_binary_name())
        self._dump_scripts()

    def add_script(self, **kwargs):
        for key, value in kwargs.items():
            self.scripts[key] = value

    def install(self):
        print('App.install()')
        self._update()
        cmd = ['univention-app', 'install', '--noninteractive', '--username', self.admin_user, '--pwdfile', self.admin_pwdfile]
        if not self.call_join_scripts:
            cmd.append('--do-not-call-join-scripts')
        cmd.append('%s=%s' % (self.app_name, self.app_version))
        print(cmd)
        error_handling_call(cmd, exc=UCSTest_DockerApp_InstallationFailed)

        self.reload_container_id()

        self.installed = True

    def reload_container_id(self):
        self.ucr.load()
        self.container_id = self.ucr.get('appcenter/apps/%s/container' % self.app_name)

    def file(self, fname):
        fname = fname.removeprefix('/')
        dirname = subprocess.check_output(['docker', 'inspect', '--format={{.GraphDriver.Data.MergedDir}}', self.container_id], text=True).strip()
        return os.path.join(dirname, fname)

    def configure(self, args):
        set_vars = []
        unset_vars = []
        for key, value in args.items():
            if value is None:
                unset_vars.append(key)
            else:
                set_vars.append('%s=%s' % (key, value))
        cmd = ['univention-app', 'configure', '%s=%s' % (self.app_name, self.app_version)]
        if set_vars:
            cmd.extend(['--set', *set_vars])
        if unset_vars:
            cmd.extend(['--unset', *unset_vars])
        error_handling_call(cmd, exc=UCSTest_DockerApp_ConfigureFailed)

    def install_via_umc(self):
        def _thread(event, options):
            try:
                client.umc_command("appcenter/keep_alive")
            finally:
                event.set()
        print('App.umc_install()')
        client = umc.Client.get_test_connection()
        client.umc_get('session-info')

        options = {
            "function": 'install',
            "application": self.app_name,
            "app": self.app_name,
            "force": True,
        }
        resp = client.umc_command('appcenter/docker/invoke', options).result
        progress_id = resp.get('id')
        if not resp:
            raise UCTTest_DockerApp_UMCInstallFailed(resp, None)
        errors = []
        finished = False
        progress = None
        event = threading.Event()
        threading.Thread(target=_thread, args=(event, options)).start()
        while not (event.wait(3) and finished):
            options = {"progress_id": progress_id}
            progress = client.umc_command('appcenter/docker/progress', options, print_request_data=False, print_response=False).result
            progress.get('info', None)
            for i in progress.get('intermediate', []):
                if i['level'] in ['ERROR', 'CRITICAL']:
                    errors.append(i)
            finished = progress.get('finished', False)
        if not progress['result'].get('success', False) or not progress['result'].get('can_continue', False):
            raise UCTTest_DockerApp_UMCInstallFailed(progress, errors)
        self.reload_container_id()
        self.installed = True
        if errors:
            raise UCTTest_DockerApp_UMCInstallFailed(None, errors)

    def _update(self):
        error_handling_call(['univention-app', 'update'], exc=UCSTest_DockerApp_UpdateFailed)

    def register(self):
        print('App.register()')
        cmd = ['univention-app', 'register', '--app']
        print(cmd)
        error_handling_call(cmd, exc=UCSTest_DockerApp_RegisterFailed)

    def upgrade(self):
        print('App.upgrade()')
        self._update()
        cmd = ['univention-app', 'upgrade', '--noninteractive', '--username', self.admin_user, '--pwdfile', self.admin_pwdfile]
        if not self.call_join_scripts:
            cmd.append('--do-not-call-join-scripts')
        cmd.append('%s=%s' % (self.app_name, self.app_version))
        print(cmd)
        error_handling_call(cmd, exc=UCSTest_DockerApp_UpgradeFailed)
        self.reload_container_id()
        self.installed = True

    def verify(self):
        print('App.verify()')
        error_handling_call(['univention-app', 'status', '%s=%s' % (self.app_name, self.app_version)], exc=UCSTest_DockerApp_VerifyFailed)

        if self.package:
            try:
                output = subprocess.check_output(['univention-app', 'shell', '%s=%s' % (self.app_name, self.app_version), 'dpkg-query', '-W', self.package_name], text=True)
                expected_output1 = '%s\t%s\r\n' % (self.package_name, self.package_version)
                expected_output2 = '%s\t%s\n' % (self.package_name, self.package_version)
                if output not in [expected_output1, expected_output2]:
                    raise UCSTest_DockerApp_VerifyFailed('%r != %r' % (output, expected_output2))
            except subprocess.CalledProcessError:
                raise UCSTest_DockerApp_VerifyFailed('univention-app shell failed')

    def uninstall(self):
        print('App.uninstall()')
        if self.installed:
            cmd = ['univention-app', 'remove', '--noninteractive', '--username', self.admin_user, '--pwdfile', self.admin_pwdfile]
            if not self.call_join_scripts:
                cmd.append('--do-not-call-join-scripts')
            cmd.append('%s=%s' % (self.app_name, self.app_version))
            print(cmd)
            error_handling_call(cmd, exc=UCSTest_DockerApp_RemoveFailed)

    def execute_command_in_container(self, cmd):
        print('Execute: %s' % cmd)
        return subprocess.check_output('docker exec %s %s' % (self.container_id, cmd), stderr=subprocess.STDOUT, shell=True, text=True)

    def remove(self):
        print('App.remove()')
        if self.package:
            self.package.remove()

    def _dump_ini(self):
        if not os.path.exists('/var/www/meta-inf/%s' % self.ucs_version):
            os.makedirs('/var/www/meta-inf/%s' % self.ucs_version)

        if self.ucs_version == '4.2' and not os.path.exists('/var/www/meta-inf/4.1'):
            os.makedirs('/var/www/meta-inf/4.1')

        target = os.path.join('/var/www/meta-inf/%s' % self.ucs_version, '%s.ini' % self.app_directory)
        with open(target, 'w') as f:
            print('Write ini file: %s' % target)
            f.write('[Application]\n')
            print('[Application]')
            for key in self.ini.keys():
                f.write('%s: %s\n' % (key, self.ini[key]))
                print('%s: %s' % (key, self.ini[key]))
            print()
        svg = os.path.join('/var/www/meta-inf/%s' % self.ucs_version, self.ini.get('Logo'))
        with open(svg, 'w') as f:
            f.write(get_dummy_svg())

    def _dump_scripts(self):
        for script, content in self.scripts.items():
            comp_path = os.path.join('/var/www/univention-repository/%s/maintained/component' % self.ucs_version, '%s' % self.app_directory)
            if not os.path.exists(comp_path):
                os.makedirs(comp_path)
            target = os.path.join(comp_path, script)

            print('Create %s' % target)
            print(content)

            with open(target, 'w') as f:
                f.write(content)

    def configure_tinyapp_modproxy(self):
        fqdn = '%(hostname)s.%(domainname)s' % self.ucr
        self.execute_command_in_container('apk update --allow-untrusted')
        self.execute_command_in_container('apk upgrade')
        self.execute_command_in_container('apk add apache2-ssl')
        self.execute_command_in_container("sed -i 's#/var/www/localhost/htdocs#/web/html#g' /etc/apache2/conf.d/ssl.conf")
        self.execute_command_in_container("sed -i 's#/var/www/localhost/cgi-bin#/web/cgi-bin#g' /etc/apache2/conf.d/ssl.conf")
        self.execute_command_in_container("sed -i 's#www.example.com#%s#g' /etc/apache2/conf.d/ssl.conf" % fqdn)
        self.execute_command_in_container('cp /etc/apache2/conf.d/ssl.conf /web/config/conf.d')
        self.execute_command_in_container('sv restart apache2')
        self.execute_command_in_container('cat  /etc/ssl/apache2/server.pem > /root/server.pem')
        self.execute_command_in_container('mkdir /web/html/%s' % self.app_name)
        self.execute_command_in_container('/bin/sh -c "echo TEST-%s > /web/html/%s/index.txt"' % (self.app_name, self.app_name))

    def verify_basic_modproxy_settings_tinyapp(self, http=True, https=True):
        fqdn = '%(hostname)s.%(domainname)s' % self.ucr
        test_string = 'TEST-%s\n' % self.app_name
        protocols = {'http': http, 'https': https}
        for protocol, should_succeed in protocols.items():
            response = requests.get(f'{protocol}://{fqdn}/{self.app_name}/index.txt', verify=False)  # noqa: S501
            try:
                response.raise_for_status()
            except requests.exceptions.HTTPError:
                if should_succeed:
                    raise

            html = response.text
            correct = html == test_string if should_succeed else html != test_string
            if not correct:
                raise UCSTest_DockerApp_ModProxyFailed(
                    f'Got: {html}\nTested against: {test_string}\nProtocol: {protocol}\nTested equality: {should_succeed}',
                )


class Appcenter:
    def __init__(self, version=None):
        self.meta_inf_created = False
        self.univention_repository_created = False
        self.ucr = UCSTestConfigRegistry()
        self.ucr.load()
        self.apps = []

        if os.path.exists('/var/www/meta-inf'):
            print('ERROR: /var/www/meta-inf already exists')
            shutil.rmtree('/var/www/meta-inf', True)
            shutil.rmtree('/var/www/univention-repository', True)
            raise AppcenterMetainfAlreadyExists()
        if os.path.exists('/var/www/univention-repository'):
            print('ERROR: /var/www/univention-repository already exists')
            shutil.rmtree('/var/www/meta-inf', True)
            shutil.rmtree('/var/www/univention-repository', True)
            raise AppcenterRepositoryAlreadyExists()

        if not version:
            self.add_ucs_version_to_appcenter('4.4')
            self.add_ucs_version_to_appcenter('5.0')
            self.add_ucs_version_to_appcenter('5.1')
            self.add_ucs_version_to_appcenter('5.2')
            self.versions = ['4.4', '5.0', '5.1', '5.2']
            self._write_ucs_ini('[5.2]\nSupportedUCSVersions=5.2, 5.1, 5.0, 4.4\n[5.1]\nSupportedUCSVersions=5.1, 5.0, 4.4\n[5.0]\nSupportedUCSVersions=5.0, 4.4, 4.3\n[4.4]\nSupportedUCSVersions=4.4, 4.3, 4.2, 4.1\n[4.3]\nSupportedUCSVersions=4.3, 4.2, 4.1\n')
            self._write_suggestions_json()
        else:
            self.add_ucs_version_to_appcenter(version)
            self.versions = [version]
            self._write_ucs_ini('[%s]\nSupportedUCSVersions=%s\n' % (version, version))
            self._write_suggestions_json()

        print(repr(self))

    def _write_suggestions_json(self):
        with open('/var/www/meta-inf/suggestions.json', 'w') as f:
            f.write('{"v1": []}')

    def _write_ucs_ini(self, content):
        with open('/var/www/meta-inf/ucs.ini', 'w') as f:
            f.write(content)

    def add_ucs_version_to_appcenter(self, version):
        if not os.path.exists('/var/www/meta-inf'):
            os.makedirs('/var/www/meta-inf', 0o755)
            self.meta_inf_created = True

        if not os.path.exists('/var/www/univention-repository'):
            os.makedirs('/var/www/univention-repository', 0o755)
            self.univention_repository_created = True

        os.makedirs('/var/www/univention-repository/%s/maintained/component' % version)
        os.makedirs('/var/www/meta-inf/%s' % version)

        if not os.path.exists('/var/www/meta-inf/categories.ini'):
            with open('/var/www/meta-inf/categories.ini', 'w') as f:
                f.write('''[de]
Administration=Administration
Business=Business
Collaboration=Collaboration
Education=Schule
System services=Systemdienste
UCS components=UCS-Komponenten
Virtualization=Virtualisierung''')

        if not os.path.exists('/var/www/meta-inf/app-categories.ini'):
            with open('/var/www/meta-inf/app-categories.ini', 'w') as f:
                f.write(
                    '[de]\n'
                    'Backup & Archiving=Backup & Archivierung\n'
                    'Education=Bildung\n'
                    'CMS=CMS\n'
                    'Collaboration & Groupware=Collaboration & Groupware\n'
                    'CRM & ERP=CRM & ERP\n'
                    'Desktop=Desktop\n'
                    'Device Management=Device Management\n'
                    'File Sync & Share=File Sync & Share\n'
                    'Identity Management=Identity Management\n'
                    'Infrastructure=Infrastruktur\n'
                    'Mail & Messaging=Mail & Messaging\n'
                    'Office=Office\n'
                    'Printing=Drucken\n'
                    'Project Management=Projekt Management\n'
                    'Security=Sicherheit\n'
                    'Storage=Speicher\n'
                    'Telephony=Telefonie\n'
                    'Virtualization=Virtualisierung\n')
            with open('/var/www/meta-inf/rating.ini', 'w') as f:
                f.write('# rating stuff\n')
            with open('/var/www/meta-inf/license_types.ini', 'w') as f:
                f.write('# license stuff')

        handler_set([
            'update/secure_apt=no',
            'appcenter/index/verify=false',
            'repository/app_center/server=http://%(hostname)s.%(domainname)s' % self.ucr,
        ])

    def update(self):
        for vv in os.listdir('/var/www/meta-inf/'):
            directory = os.path.join('/var/www/meta-inf/', vv)
            if not os.path.isdir(directory):
                continue
            print('create_appcenter_json.py for %s' % vv)
            fqdn = '%(hostname)s.%(domainname)s' % self.ucr
            subprocess.check_call([
                './create_appcenter_json.py',
                '-u', vv,
                '-d', '/var/www',
                '-o', f'/var/www/meta-inf/{vv}/index.json.gz',
                '-s', f'http://{fqdn}',
                '-t', f'/var/www/meta-inf/{vv}/all.tar',
            ])
            subprocess.check_call([
                'zsyncmake',
                '-u', f'http://{fqdn}/meta-inf/{vv}/all.tar.gz',
                '-z',
                '-o', f'/var/www/meta-inf/{vv}/all.tar.zsync',
                f'/var/www/meta-inf/{vv}/all.tar',
            ])
        subprocess.check_call(['univention-app', 'update'])

    def cleanup(self):
        if self.meta_inf_created:
            shutil.rmtree('/var/www/meta-inf')
        if self.univention_repository_created:
            shutil.rmtree('/var/www/univention-repository')
        self.ucr.revert_to_original_registry()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type:
            print('Cleanup after exception: %s %s' % (exc_type, exc_value))
        try:
            for app in self.apps:
                app.uninstall()
        except Exception as ex:
            print('removing app %s in __exit__ failed with: %s' % (app, str(ex)))
        finally:
            self.cleanup()


def restore_data_script_4_1():
    return '''#!/usr/bin/python2.7
from optparse import OptionParser
import os
import shutil
import univention.config_registry
import traceback

BLACKLIST_UCR_VARIABLES = [
    'version/version',
    'version/erratalevel',
    'version/patchlevel',
]


# Helper function to copy all meta data of a file or directory
def copy_permissions(src, dest):
    s_stat = os.stat(src)
    os.chown(dest, s_stat.st_uid, s_stat.st_gid)
    shutil.copymode(src, dest)
    shutil.copystat(src, dest)
    d_stat = os.stat(dest)


def restore_files(source_dir):
    if not os.path.exists(source_dir):
        return
    for (path, dirs, files) in os.walk(source_dir):
        for d in dirs:
            r_path = path.replace(source_dir, '/', 1)
            dest = os.path.join(r_path, d)
            if not os.path.exists(dest):
                os.makedirs(dest)
            src = os.path.join(path, d)
            copy_permissions(src, dest)
        for i in files:
            src = os.path.join(path, i)
            dest = src.replace(source_dir, '', 1)
            if os.path.islink(src):
                linkto = os.readlink(src)
                if os.path.exists(dest) or os.path.islink(dest):
                    print 'rm %s' % dest
                    os.remove(dest)
                print 'ln -sf %s %s' % (linkto, dest)
                os.symlink(linkto, dest)
            else:
                print 'cp %s %s' % (src, dest)
                shutil.copy(src, dest)
                copy_permissions(src, dest)


def restore_ucr_layer(ucr_file, options):
    if not os.path.exists(ucr_file):
        return
    f = open(ucr_file, "r")
    vv = []
    for v in f.readlines():
        v = v.strip()
        if not v or v.startswith('#'):
            continue
        key, value = v.split(':', 1)
        if key not in BLACKLIST_UCR_VARIABLES:
            vv.append('%s=%s' % (key, value))
    if vv:
        print vv
        univention.config_registry.handler_set(vv, opts=options)

if __name__ == '__main__':
    parser = OptionParser('%prog [options]')
    parser.add_option('--app', dest='app', help='App ID')
    parser.add_option('--app-version', dest='app_version', help='Version of App')
    parser.add_option('--error-file', dest='error_file', help='Name of Error File')
    opts, args = parser.parse_args()

    conf_dir = '/var/lib/univention-appcenter/apps/%s/conf/' % opts.app
    source_dir = '/var/lib/univention-appcenter/apps/%s/conf/files' % opts.app

    try:
        restore_files(source_dir)

        print '** Restore forced UCR layer:'
        restore_ucr_layer(os.path.join(conf_dir, 'base-forced.conf'), {'force': True})
        print '** Restore ldap UCR layer'
        restore_ucr_layer(os.path.join(conf_dir, 'base-ldap.conf'), {'ldap-policy': True})
        print '** Restore normal UCR layer:'
        restore_ucr_layer(os.path.join(conf_dir, 'base.conf'), {})
    except:
        traceback.print_exc()
        if opts.error_file:
            with open(opts.error_file, 'a+') as error_file:
                traceback.print_exc(file=error_file)
        raise
'''


def store_data_script_4_1():
    return '''#!/usr/bin/python2.7
from optparse import OptionParser
import glob
import os
import shutil
import traceback


# Helper function to copy all meta data of a file or directory
def copy_permissions(src, dest):
    s_stat = os.stat(src)
    os.chown(dest, s_stat.st_uid, s_stat.st_gid)
    shutil.copymode(src, dest)
    shutil.copystat(src, dest)
    d_stat = os.stat(dest)


# Helper function to copy the files and directory
def copy_to_persistent_storage(src, dest):
    l_src = src.split('/')
    # Ignore first empty entry
    if l_src[0] == '':
        l_src = l_src[1:]
    for j in range(0, len(l_src)):
        s = os.path.join('/', '/'.join(l_src[0:j + 1]))
        d = os.path.join(dest, '/'.join(l_src[0:j + 1]))
        if os.path.isdir(s):
            if not os.path.exists(d):
                os.makedirs(d)
                copy_permissions(s, d)
        elif os.path.islink(s):
            linkto = os.readlink(s)
            if os.path.exists(d) or os.path.islink(d):
                print 'rm %s' % d
                os.remove(d)
            print 'ln -sf %s %s' % (linkto, d)
            os.symlink(linkto, d)
        else:
            print 'cp %s %s' % (s, d)
            shutil.copy(s, d)
            copy_permissions(s, d)


def copy_files(src, dest):
    for f in glob.glob(src):
        copy_to_persistent_storage(f, dest)


def copy_recursive(src, dest):
    if not os.path.exists(src):
        return
    copy_to_persistent_storage(src, dest)
    for root, dirs, files in os.walk(src):
        for f in files:
            fullpath = os.path.join(root, f)
            copy_to_persistent_storage(fullpath, dest)


if __name__ == '__main__':
    parser = OptionParser('%prog [options]')
    parser.add_option('--app', dest='app', help='App ID')
    parser.add_option('--app-version', dest='app_version', help='Version of App')
    parser.add_option('--error-file', dest='error_file', help='Name of Error File')
    opts, args = parser.parse_args()

    dest = '/var/lib/univention-appcenter/apps/%s/conf/' % opts.app

    # The files and directories below the files directory are restored
    # automatically after the new container has been started
    store = '/var/lib/univention-appcenter/apps/%s/conf/files' % opts.app

    try:
        for f in glob.glob('/etc/univention/base*conf'):
            print 'cp %s %s' % (f, dest)
            shutil.copy(f, dest)
        copy_files('/etc/*.secret', store)
        copy_recursive('/etc/univention/ssl', store)
        copy_recursive('/var/univention-join', store)
        copy_recursive('/var/lib/univention-ldap/', store)
        copy_recursive('/var/lib/univention-directory-listener/', store)
        copy_recursive('/etc/univention/connector', store)
    except:
        traceback.print_exc()
        if opts.error_file:
            with open(opts.error_file, 'a+') as error_file:
                traceback.print_exc(file=error_file)
        raise
'''


def get_dummy_svg():
    return '''<?xml version="1.0" encoding="UTF-8" standalone="no"?>
<!-- Created with Inkscape (http://www.inkscape.org/) -->

<svg
   xmlns:dc="http://purl.org/dc/elements/1.1/"
   xmlns:cc="http://creativecommons.org/ns#"
   xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
   xmlns:svg="http://www.w3.org/2000/svg"
   xmlns="http://www.w3.org/2000/svg"
   version="1.1"
   width="110"
   height="126.122"
   id="svg3555">
  <defs
     id="defs3557" />
  <metadata
     id="metadata3560">
    <rdf:RDF>
      <cc:Work
         rdf:about="">
        <dc:format>image/svg+xml</dc:format>
        <dc:type
           rdf:resource="http://purl.org/dc/dcmitype/StillImage" />
        <dc:title></dc:title>
      </cc:Work>
    </rdf:RDF>
  </metadata>
  <g
     transform="translate(-319.28571,-275.01547)"
     id="layer1">
    <g
       transform="matrix(1,0,0,-1,331.53071,388.89247)"
       id="g530">
      <path
         d="m 0,0 0,101.633 85.51,0 0,-66.758 C 85.51,15.552 61.655,23.293 61.655,23.293 61.655,23.293 68.958,0 50.941,0 L 0,0 z m 97.755,33.818 0,80.059 -110,0 0,-126.122 63.372,0 c 20.867,0 46.628,27.266 46.628,46.063 M 40.87,21.383 C 33.322,18.73 27.1,21.772 28.349,29.02 c 1.248,7.25 8.41,22.771 9.432,25.705 1.021,2.936 -0.937,3.74 -3.036,2.546 -1.21,-0.698 -3.009,-2.098 -4.554,-3.458 -0.427,0.862 -1.03,1.848 -1.482,2.791 2.52,2.526 6.732,5.912 11.72,7.138 5.958,1.471 15.916,-0.88 11.636,-12.269 -3.056,-8.117 -5.218,-13.719 -6.58,-17.89 -1.361,-4.173 0.256,-5.048 2.639,-3.423 1.862,1.271 3.846,3 5.299,4.342 0.673,-1.093 0.888,-1.442 1.553,-2.698 C 52.452,29.217 45.85,23.163 40.87,21.383 m 15.638,50.213 c -3.423,-2.913 -8.498,-2.85 -11.336,0.143 -2.838,2.992 -2.365,7.779 1.058,10.694 3.423,2.913 8.498,2.85 11.336,-0.141 2.838,-2.993 2.364,-7.781 -1.058,-10.696"
         id="path532"
         style="fill:#ffffff;fill-opacity:1;fill-rule:nonzero;stroke:none" />
    </g>
  </g>
</svg>'''
