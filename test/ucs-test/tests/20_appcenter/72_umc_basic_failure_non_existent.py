#!/usr/share/ucs-test/runner python3
## desc: |
##  Check basic App-Center Operation failures (non existent apps) via UMC commands within a local testing appcenter.
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
##   - univention-appcenter-dev
## tags: [appcenter]

from univention.lib.umc import ConnectionError, HTTPError  # noqa: A004

import appcentertest as app_test


HTTPException = (HTTPError, ConnectionError)


@app_test.test_case
def test_install_non_existent_dry_run(app_center, application):
    """Try to dry-run install an app that does not exist (must fail)."""
    try:
        app_center.install_dry_run([application])
    except HTTPException:
        pass
    else:
        app_test.fail("Dry-Install of non existent app did not fail.")


@app_test.test_case
def test_install_non_existent(app_center, application):
    """Try to install an app that does not exist (must fail)."""
    try:
        app_center.install([application])
    except HTTPException:
        pass
    else:
        app_test.fail("Dry-Install of non existent app did not fail.")


@app_test.test_case
def test_update_non_existent_dry_run(app_center, application):
    """Try to dry-run update an app that does not exist (must fail)."""
    try:
        app_center.upgrade_dry_run([application])
    except HTTPException:
        pass
    else:
        app_test.fail("Dry-Update of non existent app did not fail.")


@app_test.test_case
def test_update_non_existent(app_center, application):
    """Try to update an app that does not exist (must fail)."""
    try:
        app_center.upgrade([application])
    except HTTPException:
        pass
    else:
        app_test.fail("Dry-Update of non existent app did not fail.")


@app_test.test_case
def test_uninstall_non_existent_dry_run(app_center, application):
    """Try to dry-run uninstall an app that does not exist (must fail)."""
    try:
        app_center.remove_dry_run([application])
    except HTTPException:
        pass
    else:
        app_test.fail("Dry-Uninstall of non existent app did not fail.")


@app_test.test_case
def test_uninstall_non_existent(app_center, application):
    """Try to uninstall an app that does not exist (must fail)."""
    try:
        app_center.remove([application])
    except HTTPException:
        pass
    else:
        app_test.fail("Dry-Update of non existent app did not fail.")


def main():
    app_test.restart_umc()
    test_install_non_existent_dry_run()
    test_install_non_existent()
    test_update_non_existent_dry_run()
    test_update_non_existent()
    test_uninstall_non_existent_dry_run()
    test_uninstall_non_existent()
    app_test.restart_umc()


if __name__ == '__main__':
    main()
