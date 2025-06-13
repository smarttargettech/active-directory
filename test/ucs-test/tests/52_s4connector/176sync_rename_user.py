#!/usr/share/ucs-test/runner python3
## desc: "Rename a user and test sync"
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
from univention.testing import utils

import s4connector


if __name__ == '__main__':
    with udm_test.UCSTestUDM() as udm:
        s4connector.exit_if_connector_not_running()

        # create random users
        new_user_name = uts.random_name()
        user_dn = udm.create_user()[0]

        # verify ldap object and sync
        utils.verify_ldap_object(user_dn)
        s4connector.wait_for_sync()
        s4connector.check_object(user_dn)
        user_sid = s4connector.get_object_sid(user_dn)

        # modify user
        modified_user_dn = s4connector.modify_username(user_dn, new_user_name, udm)
        s4connector.wait_for_sync()

        # test ldap object and sync
        s4connector.check_object(modified_user_dn, user_sid, user_dn)
        utils.verify_ldap_object(modified_user_dn)

    s4connector.wait_for_sync()
