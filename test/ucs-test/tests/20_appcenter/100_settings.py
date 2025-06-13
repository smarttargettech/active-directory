#!/usr/share/ucs-test/runner pytest-3
## desc: App Settings
## tags: [basic, coverage, skip_admember]
## packages:
##   - univention-appcenter-dev
## exposure: dangerous

import os
import os.path
import re
import stat
import subprocess
from contextlib import contextmanager

import pytest

import univention.config_registry
from univention.appcenter.actions import Abort, get_action
from univention.appcenter.app_cache import Apps
from univention.appcenter.docker import Docker
from univention.appcenter.log import log_to_logfile, log_to_stream
from univention.appcenter.settings import SettingValueError
from univention.appcenter.ucr import ucr_get, ucr_save

import appcentertest as app_test


# from shutil import rmtree


log_to_logfile()
log_to_stream()


class Configuring:
    def __init__(self, app, revert='configure'):
        self.settings = set()
        self.app = app
        self.revert = revert

    def __enter__(self):
        return self

    def set(self, config):
        self.settings.update(config)
        configure = get_action('configure')
        configure.call(app=self.app, set_vars=config, run_script='no')

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.revert == 'configure':
            config = {key: None for key in self.settings}  # noqa: C420
            configure = get_action('configure')
            configure.call(app=self.app, set_vars=config, run_script='no')
            for setting in self.settings:
                assert ucr_get(setting) is None
        elif self.revert == 'ucr':
            config = {key: None for key in self.settings}  # noqa: C420
            ucr_save(config)


def fresh_settings(content, app, num):
    settings = get_settings(content, app)
    assert len(settings) == num
    return Apps().find(app.id), settings


def docker_shell(app, command):
    container = ucr_get(app.ucr_container_key)
    return subprocess.check_output(['docker', 'exec', container, '/bin/bash', '-c', command], stderr=subprocess.STDOUT, text=True)


@contextmanager
def install_app(app, set_vars=None):
    username = re.match('uid=([^,]*),.*', ucr_get('tests/domainadmin/account')).groups()[0]
    install = get_action('install')
    subprocess.run(['apt-get', 'update'], check=True)
    install.call(app=[app], username=username, password=ucr_get('tests/domainadmin/pwd'), noninteractive=True, set_vars=set_vars)
    yield app
    remove = get_action('remove')
    remove.call(app=[app], username=username, password=ucr_get('tests/domainadmin/pwd'), noninteractive=True)


@contextmanager
def add_custom_settings(app, custom_settings_content):
    custom_settings_file = f"/var/lib/univention-appcenter/apps/{app.id}/custom.settings"
    with open(custom_settings_file, "w") as f:
        f.write(custom_settings_content)
    try:
        yield
    finally:
        os.remove(custom_settings_file)


@pytest.fixture(scope='module')
def local_appcenter():
    with app_test.local_appcenter():
        yield


@pytest.fixture(scope='module')
def installed_component_app(local_appcenter):
    ini_file = '''[Application]
ID = ucs-test
Code = TE
Name = UCS Test App
Logo = logo.svg
Version = 1.0
License = free
WithoutRepository = True
DefaultPackages = libcurl4-doc'''
    with open('/tmp/app.ini', 'w') as fd:
        fd.write(ini_file)
    with open('/tmp/app.logo', 'w') as fd:
        fd.write('<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"><rect x="10" y="10" height="100" width="100" style="stroke:#ff0000; fill: #0000ff"/></svg>')
    populate = get_action('dev-populate-appcenter')
    populate.call(new=True, ini='/tmp/app.ini', logo='/tmp/app.logo')
    app = Apps().find('ucs-test')
    with install_app(app) as app:
        yield app


@pytest.fixture(scope='module')
def apache_docker_app(local_appcenter):
    ini_file = '''[Application]
ID = apache
Code = AP
Name = Apache
Version = 2.4
DockerImage = docker-test.software-univention.de/httpd:2.4.23-alpine
DockerScriptInit = httpd-foreground
DockerScriptStoreData =
DockerScriptRestoreDataBeforeSetup =
DockerScriptRestoreDataAfterSetup =
DockerScriptSetup =
DockerScriptUpdateAvailable =
PortsRedirection = 8080:80
Webinterface = /
WebInterfacePortHTTP = 8080
WebInterfacePortHTTPS = 0
AutoModProxy = False
UCSOverviewCategory = False'''
    with open('/tmp/app.ini', 'w') as fd:
        fd.write(ini_file)
    populate = get_action('dev-populate-appcenter')
    populate.call(new=True, ini='/tmp/app.ini')
    return Apps().find('apache')


@pytest.fixture
def installed_apache_docker_app(apache_docker_app):
    with install_app(apache_docker_app) as app:
        yield app


def get_settings(content, app):
    fname = '/tmp/app.settings'
    with open(fname, 'w') as fd:
        fd.write(content)
    populate = get_action('dev-populate-appcenter')
    populate.call(component_id=app.component_id, ini=app.get_ini_file(), settings='/tmp/app.settings')

    app = Apps().find(app.id)
    settings = app.get_settings()

    return settings


def test_string_setting(installed_component_app):
    content = '''[test/setting]
Type = String
Description = My Description
InitialValue = Default: @%@ldap/base@%@
'''

    app, settings = fresh_settings(content, installed_component_app, 1)
    setting, = settings
    assert repr(setting) == "StringSetting(name='test/setting')"

    assert setting.is_inside(app) is False
    assert setting.is_outside(app) is True

    assert setting.get_initial_value(app) == 'Default: %s' % ucr_get('ldap/base')

    assert setting.get_value(app) is None

    with Configuring(app, revert='ucr') as config:
        config.set({setting.name: 'My value'})
        assert setting.get_value(app) == 'My value'
        config.set({setting.name: None})
        assert setting.get_value(app) is None
        config.set({setting.name: ''})
        assert setting.get_value(app) is None


def test_string_setting_docker(installed_apache_docker_app):
    content = '''[test/setting]
Type = String
Description = My Description
InitialValue = Default: @%@ldap/base@%@
Scope = inside, outside
'''

    app, settings = fresh_settings(content, installed_apache_docker_app, 1)
    setting, = settings
    assert repr(setting) == "StringSetting(name='test/setting')"

    assert setting.is_inside(app) is True
    assert setting.is_outside(app) is True

    assert setting.get_initial_value(app) == 'Default: %s' % ucr_get('ldap/base')

    assert setting.get_value(app) is None

    with Configuring(app, revert='ucr') as config:
        config.set({setting.name: 'My value'})
        assert setting.get_value(app) == 'My value'
        assert ucr_get(setting.name) == 'My value'
        assert docker_shell(app, 'grep "test/setting: " /etc/univention/base.conf') == 'test/setting: My value\n'

        stop = get_action('stop')
        stop.call(app=app)
        config.set({setting.name: 'My new value'})

        start = get_action('start')
        start.call(app=app)
        assert ucr_get(setting.name) == 'My new value'


@pytest.mark.parametrize('content_custom', [
    f'''[test1/setting]
Type = String
Description = My Description
InitialValue = Default: @%@hostname@%@
Scope = {scope}
''' for scope in ('inside, outside', 'outside', 'inside')
])
def test_string_custom_setting_docker(installed_apache_docker_app, content_custom):
    content = '''[test/setting]
Type = String
Description = My Description
InitialValue = Default: @%@ldap/base@%@
Scope = inside, outside
'''
    with add_custom_settings(installed_apache_docker_app, content_custom):
        app, settings = fresh_settings(content, installed_apache_docker_app, 2)
        setting1, setting2 = settings
        for c, setting in [(content, setting1), (content_custom, setting2)]:
            assert repr(setting) == f"StringSetting(name='{setting.name}')"
            assert setting.is_inside(app) is ("inside" in c)
            assert setting.is_outside(app) is ("outside" in c)
            ucr_var_name = re.search('@%@(.*?)@%@', c).group(1)
            assert setting.get_initial_value(app) == 'Default: %s' % ucr_get(ucr_var_name)
            assert setting.get_value(app) is None

        with Configuring(app, revert='ucr') as config:
            config.set({setting1.name: 'My value', setting2.name: 'My value2'})

            assert setting1.get_value(app) == 'My value'
            assert setting2.get_value(app) == 'My value2'

            assert ucr_get(setting1.name) == 'My value'
            if setting2.is_outside(app):
                assert ucr_get(setting2.name) == 'My value2'
            assert docker_shell(app, f'grep "{setting1.name}: " /etc/univention/base.conf') == f'{setting1.name}: My value\n'
            if setting2.is_inside(app):
                assert docker_shell(app, f'grep "{setting2.name}: " /etc/univention/base.conf') == f'{setting2.name}: My value2\n'

            config.set({setting1.name: 'My new value', setting2.name: 'My new value2'})

            stop = get_action('stop')
            stop.call(app=app)

            start = get_action('start')
            start.call(app=app)

            assert ucr_get(setting1.name) == 'My new value'
            if setting2.is_outside(app):
                assert ucr_get(setting2.name) == 'My new value2'

            assert docker_shell(app, f'grep "{setting1.name}: " /etc/univention/base.conf') == f'{setting1.name}: My new value\n'
            if setting2.is_inside(app):
                assert docker_shell(app, f'grep "{setting2.name}: " /etc/univention/base.conf') == f'{setting2.name}: My new value2\n'


def test_int_setting(installed_component_app):
    content = '''[test/setting2]
Type = Int
Description = My Description 2
InitialValue = 123
Show = Install, Settings
Required = Yes
'''

    app, settings = fresh_settings(content, installed_component_app, 1)
    setting, = settings
    assert repr(setting) == "IntSetting(name='test/setting2')"

    # FIXME: This should be int(123), right?
    assert setting.get_initial_value(app) == '123'
    assert setting.get_value(app, phase='Install') == '123'
    assert setting.get_value(app, phase='Settings') is None

    assert setting.should_go_into_image_configuration(app) is False

    with pytest.raises(SettingValueError):
        setting.sanitize_value(app, None)

    with Configuring(app, revert='ucr') as config:
        config.set({setting.name: '3000'})
        assert setting.get_value(app) == 3000
        with pytest.raises(Abort):
            config.set({setting.name: 'invalid'})
        assert setting.get_value(app) == 3000


def test_status_and_file_setting(installed_component_app):
    content = '''[test/setting3]
Type = Status
Description = My Description 3

[test/setting4]
Type = File
Filename = /tmp/settingdir/setting4.test
Description = My Description 4

[test/setting4/2]
Type = File
Filename = /tmp/%s
Description = My Description 4.2
''' % (300 * 'X')

    app, settings = fresh_settings(content, installed_component_app, 3)
    status_setting, file_setting, file_setting2 = settings
    assert repr(status_setting) == "StatusSetting(name='test/setting3')"
    assert repr(file_setting) == "FileSetting(name='test/setting4')"
    assert repr(file_setting2) == "FileSetting(name='test/setting4/2')"

    try:
        with Configuring(app, revert='ucr') as config:
            ucr_save({status_setting.name: 'My Status'})
            assert status_setting.get_value(app) == 'My Status'
            assert not os.path.exists(file_setting.filename)
            assert file_setting.get_value(app) is None

            config.set({status_setting.name: 'My new Status', file_setting.name: 'File content'})

            assert status_setting.get_value(app) == 'My Status'
            assert os.path.exists(file_setting.filename)
            assert open(file_setting.filename).read() == 'File content'
            assert file_setting.get_value(app) == 'File content'

            config.set({file_setting.name: None})
            assert not os.path.exists(file_setting.filename)
            assert file_setting.get_value(app) is None

            assert file_setting2.get_value(app) is None
            config.set({file_setting2.name: 'File content 2'})
            assert file_setting2.get_value(app) is None
    finally:
        try:
            os.unlink(file_setting.filename)
        except OSError:
            pass


def test_file_setting_docker(installed_apache_docker_app):
    content = '''[test/setting4]
Type = File
Filename = /tmp/settingdir/setting4.test
Description = My Description 4
'''

    app, settings = fresh_settings(content, installed_apache_docker_app, 1)
    setting, = settings
    assert repr(setting) == "FileSetting(name='test/setting4')"

    docker_file = Docker(app).path(setting.filename)

    try:
        with Configuring(app, revert='configure') as config:
            assert not os.path.exists(docker_file)
            assert setting.get_value(app) is None

            config.set({setting.name: 'Docker file content'})
            assert os.path.exists(docker_file)
            assert open(docker_file).read() == 'Docker file content'
            assert setting.get_value(app) == 'Docker file content'

            config.set({setting.name: None})
            assert not os.path.exists(docker_file)
            assert setting.get_value(app) is None
    finally:
        try:
            os.unlink(setting.filename)
        except OSError:
            pass


def test_password_setting(installed_component_app):
    content = '''[test/setting5]
Type = Password

[test/setting6]
Type = PasswordFile
Filename = /tmp/settingdir/setting6.password
'''

    app, settings = fresh_settings(content, installed_component_app, 2)
    password_setting, password_file_setting = settings

    assert repr(password_setting) == "PasswordSetting(name='test/setting5')"
    assert repr(password_file_setting) == "PasswordFileSetting(name='test/setting6')"

    assert password_setting.should_go_into_image_configuration(app) is False
    assert password_file_setting.should_go_into_image_configuration(app) is False

    assert password_setting.get_value(app) is None
    assert not os.path.exists(password_file_setting.filename)

    try:
        with Configuring(app, revert='ucr') as config:
            config.set({password_setting.name: 'MyPassword', password_file_setting.name: 'FilePassword'})

            assert password_setting.get_value(app) == 'MyPassword'
            assert os.path.exists(password_file_setting.filename)
            assert open(password_file_setting.filename).read() == 'FilePassword'
            assert stat.S_IMODE(os.stat(password_file_setting.filename).st_mode) == 0o600
    finally:
        try:
            os.unlink(password_file_setting.filename)
        except OSError:
            pass


def test_password_setting_docker(installed_apache_docker_app):
    content = '''[test/setting5]
Type = Password

[test/setting6]
Type = PasswordFile
Filename = /tmp/settingdir/setting6.password
'''

    app, settings = fresh_settings(content, installed_apache_docker_app, 2)
    password_setting, password_file_setting = settings

    assert repr(password_setting) == "PasswordSetting(name='test/setting5')"
    assert repr(password_file_setting) == "PasswordFileSetting(name='test/setting6')"

    assert password_setting.should_go_into_image_configuration(app) is False
    assert password_file_setting.should_go_into_image_configuration(app) is False

    password_file = Docker(app).path(password_file_setting.filename)

    assert password_setting.is_inside(app) is True
    assert password_file_setting.is_inside(app) is True

    assert not os.path.exists(password_file)

    with Configuring(app, revert='ucr') as config:
        config.set({password_setting.name: 'MyPassword', password_file_setting.name: 'FilePassword'})

        assert password_setting.get_value(app) == 'MyPassword'
        assert os.path.exists(password_file)
        assert open(password_file).read() == 'FilePassword'
        assert stat.S_IMODE(os.stat(password_file).st_mode) == 0o600

        stop = get_action('stop')
        stop.call(app=app)
        config.set({password_setting.name: 'MyNewPassword2', password_file_setting.name: 'NewFilePassword2'})
        assert password_setting.get_value(app) is None
        assert password_file_setting.get_value(app) is None

        start = get_action('start')
        start.call(app=app)
        assert password_setting.get_value(app) == 'MyPassword'
        assert open(password_file).read() == 'FilePassword'


def test_bool_setting(installed_component_app):
    content = '''[test/setting7]
Type = Bool
Description = My Description 7
InitialValue = False
'''

    app, settings = fresh_settings(content, installed_component_app, 1)
    setting, = settings
    assert repr(setting) == "BoolSetting(name='test/setting7')"

    # FIXME: This should be bool(False), right?
    assert setting.get_initial_value(app) == 'False'
    assert setting.get_value(app) is False

    with Configuring(app, revert='ucr') as config:
        config.set({setting.name: 'yes'})
        assert setting.get_value(app) is True
        config.set({setting.name: 'false'})
        assert setting.get_value(app) is False
        config.set({setting.name: True})
        assert setting.get_value(app) is True


def test_list_setting(installed_component_app):
    content = '''[test/setting8]
Type = List
Values = v1, v2, v3
Labels = Label 1, Label 2\\, among others, Label 3
Description = My Description 8
'''

    app, settings = fresh_settings(content, installed_component_app, 1)
    setting, = settings
    assert repr(setting) == "ListSetting(name='test/setting8')"

    with Configuring(app, revert='ucr') as config:
        with pytest.raises(Abort):
            config.set({setting.name: 'v4'})
        assert setting.get_value(app) is None
        config.set({setting.name: 'v1'})
        assert setting.get_value(app) == 'v1'


@pytest.fixture(scope='module')
def outside_test_settings():
    return '''[test_settings/outside]
Type = String
Required = True
Show = Install, Settings
Scope = outside
Description = setting1
InitialValue = initValue

[test_settings/inside]
Type = String
Show = Install
Scope = inside
Description = setting2

[test_settings/not_given]
Type = String
Show = Install
Scope = outside
InitialValue = initValue
Description = setting3

[test_settings/list]
Show = Install
Values = value1, value2, value3
Labels = Label 1, Label 2, Label 3
InitialValue = initValue
Scope = outside
Description = setting4

[test_settings/bool]
Type = Bool
Required = True
Show = Install, Settings
Scope = outside
InitialValue = false
Description = setting5
'''


@pytest.fixture(scope='module')
def outside_test_preinst():
    return '''#!/bin/bash
eval "$(ucr shell)"
set -x
test "$test_settings_outside" = "123" || exit 1
test "$test_settings_list" = "value2" || exit 1
test -z "$test_settings_inside" || exit 1
test -z "$test_settings_not_exists" || exit 1
test "$test_settings_not_given" = "initValue" || exit 1
test "$test_settings_bool" = "true" || exit 1
exit 0'''


def docker_app_ini():
    return '''[Application]
ID = alpine
Code = AP
Name = Alpine
Version = 3.6
DockerImage = docker-test.software-univention.de/alpine:3.6
DockerScriptInit = /sbin/init
DockerScriptStoreData =
DockerScriptRestoreDataBeforeSetup =
DockerScriptRestoreDataAfterSetup =
DockerScriptSetup =
DockerScriptUpdateAvailable =
AutoModProxy = False
UCSOverviewCategory = False''', 'alpine'


def package_app_ini():
    return '''[Application]
ID = ucstest
Code = TE
Name = UCS Test App
Logo = logo.svg
Version = 1.0
License = free
WithoutRepository = True
DefaultPackages = libcurl4-doc''', 'ucstest'


@pytest.fixture(scope='module', params=[package_app_ini, docker_app_ini])
def outside_test_app(request, local_appcenter, outside_test_preinst, outside_test_settings):
    ini_file, app_id = request.param()
    with open('/tmp/app.ini', 'w') as fd:
        fd.write(ini_file)
    with open('/tmp/app.settings', 'w') as fd:
        fd.write(outside_test_settings)
    with open('/tmp/app.preinst', 'w') as fd:
        fd.write(outside_test_preinst)
    populate = get_action('dev-populate-appcenter')
    populate.call(new=True, settings='/tmp/app.settings', preinst='/tmp/app.preinst', ini='/tmp/app.ini')
    return Apps().find(app_id)


def test_outside_settings_in_preinst(outside_test_app):
    settings_unset = [
        'test_settings/outside',
        'test_settings/inside',
        'test_settings/not_given',
        'test_settings/list',
        'test_settings/bool',
    ]
    univention.config_registry.handler_unset(settings_unset)
    settings = {
        'test_settings/outside': '123',
        'test_settings/inside': '123',
        'test_settings/not_exists': 123,
        'test_settings/list': 'value2',
        'test_settings/bool': True,
    }
    is_installed = False
    with install_app(outside_test_app, settings) as app:
        is_installed = app.is_installed()
    univention.config_registry.handler_unset(settings_unset)
    assert is_installed
