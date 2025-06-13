#!/usr/share/ucs-test/runner python3
## desc: check if a radius login via DOMAIN\USERNAME is working
## tags: [apptest, radius]
## packages:
##   - univention-radius
## join: true
## exposure: dangerous

import subprocess
import tempfile

import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test


def eapol_test(username):
    testdata = f'''network={{
        key_mgmt=WPA-EAP
        eap=PEAP
        identity="{username}"
        anonymous_identity="anonymous"
        password="univention"
        phase2="autheap=MSCHAPV2"
}}
'''
    with tempfile.NamedTemporaryFile() as fd:
        fd.write(testdata.encode('UTF-8'))
        fd.flush()
        subprocess.check_call(['/usr/sbin/eapol_test', '-c', fd.name, '-s', 'testing123'])


def main():
    with ucr_test.UCSTestConfigRegistry() as ucr, udm_test.UCSTestUDM() as udm:
        username_allowed = udm.create_user(networkAccess=1)[1]
        eapol_test(username_allowed)
        eapol_test('{}\\{}'.format(ucr.get('windows/domain'), username_allowed))


if __name__ == '__main__':
    main()
