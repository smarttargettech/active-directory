#!/usr/share/ucs-test/runner python3
## desc: check if the radius inner-tunnel is working
## tags: [apptest, radius]
## packages:
##   - univention-radius
## join: true
## exposure: dangerous

import subprocess

import univention.testing.udm as udm_test
from univention.testing import utils


def radtest(username):
    subprocess.check_call([
        'radtest',
        '-t',
        'mschap',
        username,
        'univention',
        '127.0.0.1:18120',
        '0',
        'testing123',
    ])


def main():
    with udm_test.UCSTestUDM() as udm:
        username_allowed = udm.create_user(networkAccess=1)[1]
        username_forbidden = udm.create_user(networkAccess=0)[1]
        radtest(username_allowed)
        try:
            radtest(username_forbidden)
        except subprocess.CalledProcessError:
            # OK user has no network access
            pass
        else:
            utils.fail("Authentication at radius without network access possible!")


if __name__ == '__main__':
    main()
