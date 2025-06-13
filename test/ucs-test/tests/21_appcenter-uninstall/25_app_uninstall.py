#!/usr/share/ucs-test/runner python3
## desc: Checks if apps are uninstalled
## tags: [appuninstalltest]
## roles-not: [basesystem]
## packages:
##   - univention-directory-manager-tools
##   - univention-management-console-module-appcenter
## exposure: safe


import re
import subprocess

from univention.appcenter.ucr import ucr_get, ucr_is_true, ucr_keys
from univention.testing import utils

from appcenteruninstalltest import get_requested_apps


def check_status(app):
    if app.docker:
        print('    Checking removed Docker Container')
        assert ucr_get('appcenter/apps/%s/status' % app.id) is None
    else:
        packages = app.default_packages
        print('    Checking packages', ', '.join(packages))
        for package in packages:
            try:
                output = subprocess.check_output(['dpkg', '-s', package], stderr=subprocess.STDOUT).decode('utf-8')
            except subprocess.CalledProcessError:
                pass
            else:
                for line in output.splitlines():
                    if line.startswith('Status: ') and line != 'Status: deinstall ok config-files':
                        print(output)
                        utils.fail('ERROR: A package is not uninstalled!')
        if ucr_get('server/role') in ['domaincontroller_master', 'domaincontroller_backup']:
            packages = app.default_packages_master
            if packages:
                try:
                    output = subprocess.check_output(['dpkg', '-s', *packages], stderr=subprocess.STDOUT).decode('utf-8')
                except subprocess.CalledProcessError:
                    utils.fail('ERROR: MasterPackages are not installed!')
                else:
                    for line in output.splitlines():
                        if line.startswith('Status: ') and line != 'Status: install ok installed':
                            print(output)
                            utils.fail('ERROR: A package is not installed!')
        print('    Checking component')
        if ucr_is_true('repository/online/component/%s' % app.component_id):
            utils.fail('FAIL: component %s still active' % app.component)


def check_ldap(app):
    dn = 'univentionAppID=%s_%s,cn=%s,cn=apps,cn=univention,%s' % (app.id, app.version, app.id, ucr_get('ldap/base'))
    try:
        utils.verify_ldap_object(dn, should_exist=False)
    except utils.LDAPUnexpectedObjectFound:
        utils.fail('FAIL: %s still exists' % dn)


def check_webinterface(app):
    print('    Webinterface for', app)
    for key in ucr_keys():
        if re.match('ucs/web/overview/entries/.*/%s/link', key):
            utils.fail('FAIL: webinterface still configured' % app.id)


def _check_url(url):
    print('       Checking', url)
    import lxml
    import requests
    requests_timeout = 30
    r = requests.get(url, timeout=requests_timeout, verify=False)  # noqa: S501
    print('       ...', r.status_code)
    assert not str(r.status_code).startswith(('4', '5'))

    # check meta refresh
    soup = lxml.html.fromstring(r.text)
    refresh = soup.cssselect('meta[http-equiv="refresh"]')
    if refresh:
        refresh_url = refresh[0].get('content')
        if refresh_url:
            print('Found meta refresh: %s' % refresh_url)
            # e.g., 0;URL=controller.pl?action=LoginScreen/user_login
            index = refresh_url.lower().find('url=')
            if index > 0:
                refresh_url = refresh_url[index + 4:]
                if not refresh_url.lower().startswith('http'):
                    refresh_url = '%s%s' % (url, refresh_url)
                _check_url(refresh_url)


for app in get_requested_apps():
    print('Checking', app)
    if not app._allowed_on_local_server():
        print('Not allowed ... skipping')
        continue
    check_status(app)
    check_ldap(app)
    check_webinterface(app)
