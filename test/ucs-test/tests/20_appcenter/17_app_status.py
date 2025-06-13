#!/usr/share/ucs-test/runner python3
## desc: Checks if Apps are installed correctly
## tags: [SKIP-UCSSCHOOL, basic, apptest]
## roles-not: [basesystem]
## packages:
##   - univention-directory-manager-tools
##   - univention-management-console-module-appcenter
## exposure: safe

import subprocess

import lxml.html
import requests
import urllib3

from univention.appcenter.app_cache import Apps
from univention.appcenter.ucr import ucr_get
from univention.testing import utils

from appcentertest import get_requested_apps


# Suppress InsecureRequestWarning: Unverified HTTPS request
urllib3.disable_warnings()


def check_status(app):
    if app.docker:
        print('    Checking running Docker Container')
        assert ucr_get('appcenter/apps/%s/status' % app.id) == 'installed'
        container = ucr_get('appcenter/apps/%s/container' % app.id)
        output = subprocess.check_output(['docker', 'inspect', '-f', '{{.State.Running}}', container]).decode().rstrip('\n')
        if output != 'true':
            utils.fail('ERROR: Container not running!')
        if app.docker_image and app.docker_image.startswith('docker.software-univention.de/ucs-appbox-amd64:'):
            print('    Within container, checking packages', ', '.join(app.default_packages))
            output = subprocess.check_output(['univention-app', 'shell', app.id, 'dpkg', '-s', *app.default_packages], stderr=subprocess.STDOUT).decode('utf-8')
            for line in output.splitlines():
                if line.startswith('Status: ') and line != 'Status: install ok installed':
                    print(output)
                    utils.fail('ERROR: A package is not installed!')
        else:
            print('    No appbox image, not checking packages')
    else:
        packages = app.default_packages
        if ucr_get('server/role') in ['domaincontroller_master', 'domaincontroller_backup']:
            packages.extend(app.default_packages_master)
        print('    Checking packages', ', '.join(packages))
        output = subprocess.check_output(['dpkg', '-s', *packages], stderr=subprocess.STDOUT).decode('utf-8')
        for line in output.splitlines():
            if line.startswith('Status: ') and line != 'Status: install ok installed':
                print(output)
                utils.fail('ERROR: A package is not installed!')


def check_ldap(app, apps):
    dn = 'univentionAppID=%s_%s,cn=%s,cn=apps,cn=univention,%s' % (app.id, app.version, app.id, ucr_get('ldap/base'))
    utils.verify_ldap_object(dn, {'univentionAppVersion': [app.version]})
    utils.verify_ldap_object(dn, {'univentionAppName': ['[en] %s' % app.name], 'univentionAppInstalledOnServer': ['%s.%s' % (ucr_get('hostname'), ucr_get('domainname'))]}, strict=False)
    for app_version in apps.get_all_apps_with_id(app.id):
        if app_version.id == app.id and app_version.version == app.version:
            continue
        dn = 'univentionAppID=%s_%s,cn=%s,cn=apps,cn=univention,%s' % (app_version.id, app_version.version, app_version.id, ucr_get('ldap/base'))
        utils.verify_ldap_object(dn, should_exist=False)


def check_webinterface(app):
    if not app.web_interface:
        print('    Skipping Webinterface check')
        return
    print('    Webinterface for', app)
    if app.has_local_web_interface():
        fqdn = '%s.%s' % (ucr_get('hostname'), ucr_get('domainname'))
        if app.web_interface_port_http:
            port = app.web_interface_port_http
            if app.auto_mod_proxy:
                port = 80
            port = ':%d' % port if port != 80 else ''
            url = 'http://%s%s%s' % (fqdn, port, app.web_interface)
            _check_url(url)
        if app.web_interface_port_https:
            port = app.web_interface_port_https
            if app.auto_mod_proxy:
                port = 443
            port = ':%d' % port if port != 443 else ''
            url = 'https://%s%s%s' % (fqdn, port, app.web_interface)
            _check_url(url)
    else:
        _check_url(app.web_interface)


def _check_url(url):
    print('       Checking', url)
    requests_timeout = 30
    r = requests.get(url, timeout=requests_timeout, verify=False)  # noqa: S501
    print('       ...', r.status_code)
    if r.status_code not in [401, 403]:
        assert not str(r.status_code).startswith(('4', '5'))
    print('       ...', r.url)
    url = r.url

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


apps = Apps()
for app in get_requested_apps():
    print('Checking', app)
    if not app._allowed_on_local_server():
        print('    Not allowed ... skipping')
        continue
    check_status(app)
    check_ldap(app, apps)
    check_webinterface(app)
