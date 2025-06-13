#!/usr/share/ucs-test/runner python3
## desc: |
##  Collisions between user uidNumbers and group gidNumbers
##  Check different scenarios where the user uidNumbers can collide with group
##  gidNumbers and vice versa
## bugs: [38796]
## tags: [udm]
## roles: [domaincontroller_master]
## versions:
##  4.0-3: found
##  4.1-0: fixed
## exposure: dangerous
## packages:
##   - python3-univention-directory-manager
import univention.admin.modules as udm_modules
import univention.config_registry
import univention.testing.ucr as ucr_test
import univention.testing.udm as udm_test
from univention.testing import utils


UCR = ucr_test.UCSTestConfigRegistry()
UCR.load()

LO = utils.get_ldap_connection(admin_uldap=True)


class Failure:

    def __init__(self, message):
        self.message = message


def get_max_id():
    base_dn = UCR['ldap/base']
    users = udm_modules.lookup('users/user', None, LO, base=base_dn, scope='sub')
    groups = udm_modules.lookup('groups/group', None, LO, base=base_dn, scope='sub')

    highest_uid = max(int(user['uidNumber']) for user in users if user['uidNumber'])
    highest_gid = max(int(group['gidNumber']) for group in groups if group['gidNumber'])

    id_to_collide_with = max(highest_uid, highest_gid) + 2

    return id_to_collide_with


def consecutive_user_creation():
    id_to_collide_with = get_max_id()
    UDM.create_group(gidNumber=id_to_collide_with)

    UDM.create_user(uidNumber=id_to_collide_with - 1)
    testcase_user_dn = UDM.create_user()[0]

    if int(LO.getAttr(testcase_user_dn, 'uidNumber')[0]) == id_to_collide_with:
        return Failure("Acquired user uidNumber which collides with a groups gidNumber by consecutivley adding users.")


def consecutive_group_creation():
    id_to_collide_with = get_max_id()
    UDM.create_user(uidNumber=id_to_collide_with)

    UDM.create_group(gidNumber=id_to_collide_with - 1)
    testcase_group_dn = UDM.create_group()[0]

    if int(LO.getAttr(testcase_group_dn, 'gidNumber')[0]) == id_to_collide_with:
        return Failure("Acquired a group gidNumber which collides with a users uidNumber by consecutively adding users.")


def explicit_user_creation():
    id_to_collide_with = get_max_id()
    UDM.create_group(gidNumber=id_to_collide_with)

    try:
        UDM.create_user(uidNumber=id_to_collide_with)
    except udm_test.UCSTestUDM_CreateUDMObjectFailed:
        return
    return Failure("Explicitly added a user setting the uidNumber to an existing groups gidNumber.")


def explicit_group_creation():
    id_to_collide_with = get_max_id()
    UDM.create_user(uidNumber=id_to_collide_with)

    try:
        UDM.create_group(gidNumber=id_to_collide_with)
    except udm_test.UCSTestUDM_CreateUDMObjectFailed:
        return
    return Failure("Explicitly added a group setting the gidNumber to an existing users uidNumber.")


if __name__ == '__main__':
    udm_modules.update()
    TESTS = [
        consecutive_user_creation,
        consecutive_group_creation,
        explicit_user_creation,
        explicit_group_creation,
    ]

    TESTS_UNIQUENESS = [explicit_user_creation, explicit_group_creation]

    with udm_test.UCSTestUDM() as UDM:
        # make sure UNIQUENESS is set right
        if UCR['directory/manager/uid_gid/uniqueness']:
            univention.config_registry.handler_unset(['directory/manager/uid_gid/uniqueness'])

        FAILURES = [test() for test in TESTS if test()]

        # now test with uniqueness set to false
        univention.config_registry.handler_set(['directory/manager/uid_gid/uniqueness=no'])
        UDM.stop_cli_server()

        # with uniqueness set to false failure case inverts
        FAILURES.extend([Failure("Not able to collide ids with uid gid uniqueness off for: %s", test) for test in TESTS_UNIQUENESS if not test()])

    UCR.revert_to_original_registry()
    failure_msg = '\n'.join(
        failure.message for failure in FAILURES)

    assert not any(FAILURES), failure_msg
