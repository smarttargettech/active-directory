#!/usr/share/ucs-test/runner python3
## desc: Check App version registration in LDAP
## tags: [SKIP-UCSSCHOOL, basic, apptest]
## bugs: [35896]
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
## exposure: careful

import sys
from time import sleep

from univention.appcenter.app_cache import Apps
from univention.appcenter.ucr import ucr_get
from univention.appcenter.udm import ApplicationLDAPObject, get_machine_connection
from univention.testing import utils
from univention.testing.codes import Reason


APP_ID = 'univention-demo-data'


def get_app_dn(App):
    """Returns the given 'App' DN."""
    app_dn = ("univentionAppID=%s_%s,cn=%s,cn=apps,cn=univention,%s"
              % (App.id, App.version, App.id, ldap_base))
    return app_dn


def check_app_version_ldap_registraton(new_version: str) -> None:
    """
    Tries to create an LDAP object for App with 'APP_ID' and 'new_version'
    and verifies it after.
    """
    print("\nChecking if App's new version '%s' can be registered in LDAP"
          % new_version)

    App = Apps().find(APP_ID)
    if not App:
        print("\nThe App with id '%s' could not be found, skipping the test."
              % APP_ID)
        sys.exit(int(Reason.SKIP))

    App.version = new_version

    lo, pos = get_machine_connection()
    print("\nCreating an App LDAP object:")
    try:
        ldap_object = ApplicationLDAPObject(App, lo, pos, create_if_not_exists=True)
        if not ldap_object:
            utils.fail("The App LDAP object was neither created, "
                       "nor already exist.")
    except Exception as exc:
        utils.fail("An error occurred while trying to create an LDAP object: "
                   "%r" % exc)

    sleep(5)  # wait a bit before the check
    app_dn = get_app_dn(App)
    print("\nPerforming a check of App LDAP object with a DN '%s'" % app_dn)

    try:
        utils.verify_ldap_object(app_dn,
                                 {'univentionAppID': [f'{App.id}_{App.version}'],
                                  'univentionAppVersion': [App.version]})

        print("\nRemoving the App object from LDAP:")
        ldap_object.remove_from_directory()
    except (utils.LDAPObjectNotFound, utils.LDAPUnexpectedObjectFound,
            utils.LDAPObjectValueMissing, utils.LDAPObjectUnexpectedValue) as exc:
        utils.fail("An error occurred while verifying App's LDAP object: %r" % exc)


if __name__ == '__main__':
    """
    The test loads 'APP_ID' App and changes its version to a one from the
    'test_versions', tries to register the App in LDAP and than checks
    created LDAP object.
    """
    test_versions = ("0.1 (rev 1.0)", "0.1 [rev 1.1]", "0.1 {rev 1.2}",
                     "0.1 'rev 1.3'", "0.1 !@#$%^*-")

    print("\nChecking an App with id '%s'" % APP_ID)
    ldap_base = ucr_get('ldap/base')

    for version in test_versions:
        check_app_version_ldap_registraton(version)
