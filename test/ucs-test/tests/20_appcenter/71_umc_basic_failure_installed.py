#!/usr/share/ucs-test/runner python3
## desc: |
##  Check basic App-Center Operation failures (already installed, not installed) via UMC commands within a local testing appcenter.
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
##   - univention-appcenter-dev
## tags: [appcenter]
import logging

import appcentertest as app_test


@app_test.test_case
def test_already_installed_dry_run(app_center, application):
    """Try to dry-run install an app although it is already installed (must fail)."""
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    with test.test_install_safe():
        result = app_center.install_dry_run([package.app_id])
        if test.dry_run_successful(result):
            app_test.fail("Dry-Install of already installed app did not fail.")


@app_test.test_case
def test_already_installed(app_center, application):
    """
    Try to install an app although it is already installed without prior
    dry-run (must fail).
    """
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    with test.test_install_safe():
        result = app_center.install([package.app_id])
        if test.operation_successfull(result):
            app_test.fail("Install of already installed app did not fail.")


@app_test.test_case
def test_upgrade_without_dry_run(app_center, application):
    """Test a dry-run upgrade without having the app installed (must fail)."""
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    result = app_center.upgrade_dry_run([package.app_id])
    if test.dry_run_successful(result):
        app_test.fail("Upgrade of not installed app did not fail.")


@app_test.test_case
def test_upgrade_without(app_center, application):
    """Test an upgrade without having the app installed (must fail)."""
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    result = app_center.upgrade([package.app_id])
    if test.operation_successfull(result):
        app_test.fail("Upgrade of not installed app did not fail.")


@app_test.test_case
def test_uninstall_without_dry_run(app_center, application):
    """Test a dry-run uninstall without having the app installed (must fail)."""
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    result = app_center.remove_dry_run([package.app_id])
    if test.dry_run_successful(result):
        app_test.fail("Uninstall of not installed app did not fail.")


@app_test.test_case
def test_uninstall_without(app_center, application):
    """Test an uninstall without having the app installed (must fail)."""
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    result = app_center.remove([package.app_id])
    if test.operation_successfull(result):
        app_test.fail("Uninstall of not installed app did not fail.")


def main():
    app_test.app_logger.log_to_stream()
    app_test.app_logger.get_base_logger().setLevel(logging.WARNING)

    with app_test.local_appcenter():
        test_already_installed_dry_run()
        test_already_installed()
        test_upgrade_without_dry_run()
        test_upgrade_without()
        test_uninstall_without_dry_run()
        test_uninstall_without()


if __name__ == '__main__':
    main()
