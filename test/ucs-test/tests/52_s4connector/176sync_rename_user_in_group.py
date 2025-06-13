#!/usr/share/ucs-test/runner python3
## desc: "Rename users which are in a group and test sync"
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

        # create users and add them to a group
        new_users = [uts.random_name(), uts.random_name()]
        group_dn = udm.create_group()[0]
        users = [udm.create_user()[0], udm.create_user()[0]]
        s4connector.wait_for_sync()
        user_sids = [(s4connector.get_object_sid(user)) for user in users]
        udm.modify_object('groups/group', dn=group_dn, append={'users': list(users)})
        s4connector.wait_for_sync()

        # check users (ldap objects and if synced )
        s4connector.verify_users(group_dn, users)
        [(s4connector.check_object(user)) for user in users]
        s4connector.check_object(group_dn)

        # modify users
        modified_users = []
        for user, new_user in zip(users, new_users):
            modified_users.append(s4connector.modify_username(user, new_user, udm))
        s4connector.wait_for_sync()

        # check group and users again (ldap objects and if synced)
        s4connector.check_object(group_dn)
        s4connector.verify_users(group_dn, modified_users)
        for modified_user, user_sid, user in zip(modified_users, user_sids, users):
            s4connector.check_object(modified_user, user_sid, user)

    s4connector.wait_for_sync()
