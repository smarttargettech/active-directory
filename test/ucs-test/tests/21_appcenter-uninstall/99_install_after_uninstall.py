#!/usr/share/ucs-test/runner python3
## desc: Checks if apps can be re-installed after uninstalling
## tags: [appuninstalltest]
## roles-not: [basesystem]
## packages:
##   - univention-directory-manager-tools
##   - univention-management-console-module-appcenter
## exposure: dangerous
## versions:
##  4.4-5: skip

# skip this, we now install the app via the cfg file

import univention.config_registry
from univention import uldap
from univention.appcenter.actions import get_action
from univention.appcenter.log import log_to_stream
from univention.testing import utils

from appcenteruninstalltest import get_requested_apps


log_to_stream()
ucr = univention.config_registry.ConfigRegistry()
ucr.load()
username = uldap.explodeDn(ucr['tests/domainadmin/account'], 1)[0]
pwdfile = ucr['tests/domainadmin/pwdfile']
install = get_action('install')
info = get_action('info')

apps = []
for app in get_requested_apps():
    print('Checking', app)
    if not app._allowed_on_local_server():
        print('Not allowed ... skipping')
        continue
    apps.append(app)

if not install.call(app=apps, noninteractive=True, pwdfile=pwdfile, username=username):
    info.call()
    utils.fail('Failed to re-install apps')
