#!/usr/share/ucs-test/runner python3
## desc: check if enabling radius works for groups in groups
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
        userdn, username = udm.create_user(set={'networkAccess': 0})
        innergroupdn, _innergroupname = udm.create_group(set={
            'networkAccess': 1,
            'users': userdn,
        })
        outergroupdn, _outergroupname = udm.create_group(set={
            'networkAccess': 1,
            'nestedGroup': innergroupdn,
        })

        # outer group net access = 1, inner group net access = 1
        print("### Test 1 ###")
        try:
            radtest(username)
        except Exception:
            utils.fail("User in group with network access nested in group with network access could not authenticate!")

        # outer group net access = 1, inner group net access = 0
        print("### Test 2 ###")
        udm.modify_object(
            'groups/group',
            dn=innergroupdn,
            set={
                'networkAccess': 0,
            },
        )
        try:
            radtest(username)
        except Exception:
            utils.fail("User in group with network access nested in group without network access could not authenticate!")

        # outer group net access = 0, inner group net access = 0
        print("### Test 3 ###")
        udm.modify_object(
            'groups/group',
            dn=outergroupdn,
            set={
                'networkAccess': 0,
            },
        )
        try:
            radtest(username)
        except subprocess.CalledProcessError:
            pass
        else:
            utils.fail("User in group without network access nested in group without network access was able to authenticate!")

        # outer group net access = 0, inner group net access = 1
        print("### Test 4 ###")
        udm.modify_object(
            'groups/group',
            dn=innergroupdn,
            set={
                'networkAccess': 1,
            },
        )
        try:
            radtest(username)
        except Exception:
            utils.fail("User in group without network access nested in group with network access could not authenticate!")


if __name__ == '__main__':
    main()
