#!/usr/share/ucs-test/runner python3
## desc: "Checks if DRS replication works after a server password change"
## roles:
## - domaincontroller_backup
## - domaincontroller_slave
## exposure: dangerous
## packages:
## - univention-samba4

import datetime
import os
import subprocess
import time

import univention.config_registry
import univention.uldap
from univention.testing.ucr import UCSTestConfigRegistry
from univention.testing.udm import UCSTestUDM
from univention.testing.umc import Client
from univention.testing.utils import fail, wait_for_listener_replication


default_password = 'univention'
new_password = 'Univention.2'

with UCSTestConfigRegistry() as ucr_test:
    changed_password = False
    today = datetime.datetime.today()
    yesterday = today - datetime.timedelta(1)
    today = today.strftime("%y%m%d")
    yesterday = yesterday.strftime("%y%m%d")
    if os.path.isfile('/etc/machine.secret.old'):
        with open('/etc/machine.secret.old') as f:
            for line in f:
                if line.startswith((today, yesterday)):
                    changed_password = True
                    print('A server password change has already been executed within the last two days.\nNot executing it again.\n')
                    break

    ldap_master = ucr_test.get('ldap/master')
    umc_client = Client(ldap_master)
    role = ucr_test.get('server/role')

    if not changed_password:
        # server password change
        univention.config_registry.handler_set(['server/password/interval=-1'])

        print('Executing a server password change')
        try:
            cmd = ['/usr/lib/univention-server/server_password_change']
            output = subprocess.check_output(cmd).decode('UTF-8', 'replace')
            print('Output of server_password_change:\n%s' % (output))
        except subprocess.CalledProcessError:
            fail('Error running server_password_change')
        else:
            wait_for_listener_replication()

    # Checking drs replication
    with UCSTestUDM() as udm:
        # create user
        try:
            user_dn, user_name = udm.create_user(password='univention')
        except Exception as exc:
            fail('Creating user failed: %s' % (exc))
        else:
            print('Creating user %s succeeded: ' % user_name)
        # Check if user can be authenticated with current password
        try:
            umc_client.authenticate(user_name, default_password)
        except Exception as exc:
            fail('User cannot be authenticated: %s' % exc)
        else:
            print(f'User {user_name} could authenticate against UMC of {ldap_master}')
        # Wait for replication
        samba_found = False
        t0 = time.monotonic()
        timeout = 200
        while (not samba_found) and (time.monotonic() < t0 + timeout):
            print('Checking if user %s can be found in samba-tool user list' % (user_name))
            output = subprocess.check_output(['samba-tool', 'user', 'list']).decode('UTF-8')
            output = output.splitlines()
            for line in output:
                if line == user_name:
                    samba_found = True
            if not samba_found:
                time.sleep(5)
        if not samba_found:
            fail('user %s could not be found in samba-tool user list after %d seconds' % (user_name, timeout))

        # prepare for samba password change
        try:
            output = subprocess.check_output(['samba-tool', 'domain', 'passwordsettings', 'show']).decode('UTF-8')
            min_pwd_age_key = "Minimum password age (days): "
            for line in output.splitlines():
                if line.startswith(min_pwd_age_key):
                    min_pwd_age = line[len(min_pwd_age_key):]
            p3 = subprocess.Popen(['samba-tool', 'domain', 'passwordsettings', 'set', '--min-pwd-age=0'])
        except Exception as exc:
            fail(f'Could not save the samba settings for cleanup {exc}')

        # samba setpassword
        try:
            p4 = subprocess.Popen(['samba-tool', 'user', 'setpassword', user_name, '--newpassword=' + new_password])
            stdout, stderr = p4.communicate()
            if stderr:
                raise Exception(stderr)
        except Exception as exc:
            fail(f'Could not set the user password with samba-tool domain passwordsettings: {exc}')
        finally:
            # revert samba passwordsetting changes
            if min_pwd_age:
                subprocess.Popen(['samba-tool', 'domain', 'passwordsettings', 'set', f'--min-pwd-age={min_pwd_age}'])

        # Wait for replication
        print('Trying to log in with the new password')
        new_password_worked = False
        t = time.monotonic()
        timeout = 600
        while (not new_password_worked) and (time.monotonic() < t + timeout):
            try:
                umc_client.authenticate(user_name, new_password)
            except Exception:
                time.sleep(5)
            else:
                new_password_worked = True

        if not new_password_worked:
            fail(f'Drs replication to {ldap_master} does not seem to be working after server password change')
