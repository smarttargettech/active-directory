#!/usr/share/ucs-test/runner python3
## desc: Checks if apps are installable (except for apps/packages conflicting with installed apps)
## tags: [basic, apptest, SKIP-UCSSCHOOL]
## roles-not: [basesystem]
## timeout: 7200
## exposure: safe
## packages:
##   - univention-management-console-module-appcenter

import subprocess
import sys
import time

from univention.appcenter.actions import get_action
from univention.appcenter.app_cache import Apps
from univention.appcenter.log import log_to_logfile
from univention.testing.ucr import UCSTestConfigRegistry

from appcentertest import get_requested_apps


requested_apps = get_requested_apps()
if requested_apps and all(app.docker for app in requested_apps):
    # test runs for an hour or so...
    print('Only testing Docker Apps. No need to check other Apps')
    sys.exit(0)

with UCSTestConfigRegistry():

    log_to_logfile()

    def _packages_to_install(app):
        return app.get_packages()

    def _apt_get_update():
        cmd = ['/usr/bin/apt-get', 'update']
        print('Executing the command: %s' % cmd)
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, close_fds=True)
        (stdoutdata, stderrdata) = p.communicate()
        if p.returncode:
            print(f'apt-get update failed: {stdoutdata} {stderrdata}')

    def _apt_get_simulate(app):
        retcode = 0
        for _i in range(3):
            if not app.without_repository:
                print(f'Register app {app.id}')
                # de register app, otherwise a second register (in case of an error) would not do nothing
                register.call(apps=[app], register_task=['component'])
                register.call(apps=[app], register_task=['component'], do_it=True)
                _apt_get_update()
            packages = _packages_to_install(app)
            cmd = ['/usr/bin/apt-get', 'install', '-s', *packages]
            print('Executing the command: %s' % cmd)
            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=1, close_fds=True)
            (stdoutdata, stderrdata) = p.communicate()
            retcode = p.returncode
            if retcode == 0:
                break
            for s in ['/etc/apt/sources.list.d/15_ucs-online-version.list', '/etc/apt/sources.list.d/20_ucs-online-component.list']:
                print(s)
                with open(s) as f:
                    print(f.read())
            print(stdoutdata, stderrdata)
            print('failed, try again ...')
            time.sleep(180)
        if not app.without_repository:
            register.call(apps=[app], register_task=['component'])
            _apt_get_update()
        return retcode == 0

    register = get_action('register')
    print('Installed apps: %s' % [app.id for app in Apps().get_all_locally_installed_apps()])
    failed = []
    _apt_get_update()
    for app in Apps().get_all_apps():
        if app.docker:
            print('Ignoring app %s: Docker App' % app.id)
            continue
        forbidden, warning = app.check('install')
        if forbidden:
            print(f'Ignoring app {app.id!r}: requirements not met -> {forbidden!r}')
            continue

        print('Checking app: %s' % app.id)
        if not _apt_get_simulate(app):
            failed.append(app)
    _apt_get_update()

    if failed:
        print('\nTEST FAILED: the following apps cannot be installed due to broken packages...')
        for app in failed:
            print('[ APP: %s ]' % app.id)
        sys.exit(1)

sys.exit(0)
