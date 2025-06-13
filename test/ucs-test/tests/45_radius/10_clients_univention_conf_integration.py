#!/usr/share/ucs-test/runner python3
## desc: check if client setup through udm is working with PEAP
## tags: [apptest, radius]
## packages:
##   - univention-radius
## join: true
## exposure: dangerous

import subprocess
from tempfile import NamedTemporaryFile

import univention.testing.strings as uts
import univention.testing.udm as udm_test
from univention.testing import utils


class DummyInterface:
    def __init__(self, ip):
        self.network = f'{ip}/32'

    def __enter__(self):
        subprocess.check_output(['ip', 'link', 'add', 'eth99', 'type', 'dummy'])
        subprocess.check_output(['ip', 'addr', 'add', self.network, 'dev', 'eth99'])
        subprocess.check_output(['ip', 'link', 'set', 'up', 'eth99'])

    def __exit__(self, *args):
        subprocess.check_output(['ip', 'link', 'del', 'eth99'])


def get_wpa_config(username, password):
    wpa_config = f'''
network={{
    ssid="DoesNotMatterForThisTest"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="{username}"
    password="{password}"
    eapol_flags=3
}}
    '''
    return wpa_config


def eap_test(username, password, password_ap, addr_ap):
    with NamedTemporaryFile() as tmp_file:
        wpa_config = get_wpa_config(username, password)
        tmp_file.write(wpa_config.encode('UTF-8'))
        tmp_file.seek(0)
        print("wpa_config:")
        print(tmp_file.read().decode('UTF-8'))
        subprocess.check_call([
            'eapol_test',
            '-c',
            tmp_file.name,
            '-a',
            '127.0.0.1',
            '-p',
            '1812',
            '-A',
            addr_ap,
            '-s',
            password_ap,
            '-t',
            '10',
            '-r0',
        ])


def main():
    with udm_test.UCSTestUDM() as udm:
        password = 'univention'
        username_allowed = udm.create_user(networkAccess=1)[1]
        name = uts.random_string()
        addr = '10.254.254.254'
        secret = uts.random_string()
        nas_type = 'other'
        role = 'computers/ipmanagedclient'
        udm.create_object(
            role,
            name=name,
            ip=[addr],
            options=['kerberos', 'samba', 'posix', 'radiusAuthenticator'],
            univentionRadiusClientSharedSecret=secret,
            univentionRadiusClientType=nas_type,
            wait_for_replication=False,
        )
        utils.wait_for_replication_and_postrun()
        with DummyInterface(addr):
            # Right password, right ip
            eap_test(username_allowed, password, secret, addr)
            # Wrong password, right ip
            try:
                eap_test(username_allowed, password, secret + 'foo', addr)
            except subprocess.CalledProcessError:
                # OK Authenticator has no radius access
                pass
            else:
                utils.fail("Authenticator has network access with wrong secret")
        wrong_addr = '10.254.254.253'
        with DummyInterface(wrong_addr):
            # Right password, wrong ip
            try:
                eap_test(username_allowed, password, secret, wrong_addr)
            except subprocess.CalledProcessError:
                # OK Authenticator has no radius access
                pass
            else:
                utils.fail("Authenticator has network access with wrong ip")
            # wrong password, wrong ip
            try:
                eap_test(username_allowed, password, secret, wrong_addr)
            except subprocess.CalledProcessError:
                # OK Authenticator has no radius access
                pass
            else:
                utils.fail("Authenticator has network access with wrong ip and wrong password")


if __name__ == '__main__':
    main()
