#!/usr/share/ucs-test/runner python3
## desc: "Rename a group with users in it and test sync"
## exposure: dangerous
## packages:
##   - univention-config
##   - univention-directory-manager-tools
##   - univention-samba4
##   - univention-s4-connector
#
#  Bug #31324

import univention.testing.strings as uts
import univention.testing.udm as udm_test

import s4connector


if __name__ == '__main__':
    with udm_test.UCSTestUDM() as udm:
        s4connector.exit_if_connector_not_running()

        # create random group and fill it with random users
        new_group_name = uts.random_name()
        group_dn = udm.create_group()[0]
        users = [udm.create_user()[0], udm.create_user()[0]]
        udm.modify_object('groups/group', dn=group_dn, append={'users': users})

        # verify users and group sync
        s4connector.wait_for_sync()
        s4connector.verify_users(group_dn, users)
        s4connector.check_object(group_dn)

        # modify group
        group_sid = s4connector.get_object_sid(group_dn)
        udm.modify_object('groups/group', dn=group_dn, name=new_group_name)
        modified_group_dn = s4connector.correct_cleanup(group_dn, new_group_name, udm, True)

        # verify sync of modified group and users
        s4connector.wait_for_sync()
        s4connector.check_object(modified_group_dn, group_sid, group_dn)
        s4connector.verify_users(modified_group_dn, users)

    s4connector.wait_for_sync()
