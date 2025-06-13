#!/usr/share/ucs-test/runner python3
## desc: check if enabling radius per group works
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
        userdn, username = udm.create_user(set={'networkAccess': 1})
        groupdn, _groupname = udm.create_group(set={
            'networkAccess': 1,
            'users': userdn,
        })

        # user net access = 1, group net access = 1
        print("### Test 1 ###")
        try:
            radtest(username)
        except Exception:
            utils.fail("User with network access in group with network access could not authenticate!")

        # user net access = 1, group net access = 0
        print("### Test 2 ###")
        udm.modify_object(
            'groups/group',
            dn=groupdn,
            set={
                'networkAccess': 0,
            },
        )
        try:
            radtest(username)
        except Exception:
            utils.fail("User with network access in group without network access could not authenticate!")

        # user net access = 0, group net access = 0
        print("### Test 3 ###")
        udm.modify_object(
            'users/user',
            dn=userdn,
            set={
                'networkAccess': 0,
            },
        )
        try:
            radtest(username)
        except subprocess.CalledProcessError:
            pass
        else:
            utils.fail("User without network access in group without network access was able to authenticate!")

        # user net access = 0, group net access = 1
        print("### Test 4 ###")
        udm.modify_object(
            'groups/group',
            dn=groupdn,
            set={
                'networkAccess': 1,
            },
        )
        try:
            radtest(username)
        except Exception:
            utils.fail("User without network access in group with network access could not authenticate!")


if __name__ == '__main__':
    main()
