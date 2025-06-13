#!/usr/share/ucs-test/runner python3
## desc: check if client with PEAP is working
## tags: [apptest, radius]
## packages:
##   - univention-radius
## join: true
## exposure: dangerous

import subprocess
from tempfile import NamedTemporaryFile

import univention.testing.udm as udm_test
from univention.testing import utils


UNIVENTION_CACERT = "/etc/univention/ssl/ucsCA/CAcert.pem"
DEFAULT_CACERT = "/etc/default/cacert"


def get_wpa_config(username, password, ca_cert):
    comment = "#" if ca_cert == "" else ""
    wpa_config = f'''
network={{
    ssid="DoesNotMatterForThisTest"
    key_mgmt=WPA-EAP
    eap=PEAP
    identity="{username}"
    password="{password}"
    {comment}ca_cert="{ca_cert}"
    eapol_flags=3
}}
    '''
    return wpa_config


def eap_test(username, password, ca_cert):
    with NamedTemporaryFile() as tmp_file:
        wpa_config = get_wpa_config(username, password, ca_cert)
        tmp_file.write(wpa_config.encode("UTF-8"))
        tmp_file.seek(0)
        print("wpa_config:")
        print(tmp_file.read().decode("UTF-8"))
        subprocess.check_call([
            'eapol_test',
            '-c',
            tmp_file.name,
            '-a',
            '127.0.0.1',
            '-p',
            '1812',
            '-s',
            'testing123',
            '-r0',
        ])


def main():
    with udm_test.UCSTestUDM() as udm:
        password = 'univention'
        username_forbidden = udm.create_user(networkAccess=0)[1]
        for ca_cert in (UNIVENTION_CACERT, DEFAULT_CACERT, ''):
            # all certs shouldn't have network access
            try:
                eap_test(username_forbidden, password, ca_cert)
            except subprocess.CalledProcessError:
                # OK user has no network access
                pass
            else:
                utils.fail("Authentication at radius without network access possible!")
        username_allowed = udm.create_user(networkAccess=1)[1]
        for ca_cert in (UNIVENTION_CACERT, ''):
            eap_test(username_allowed, password, ca_cert)
        try:
            # Worng cert should fail on client side
            eap_test(username_allowed, password, DEFAULT_CACERT)
        except subprocess.CalledProcessError:
            # OK user has no network access
            pass
        else:
            utils.fail("Client connects to network with wrong certificate!")


if __name__ == '__main__':
    main()
