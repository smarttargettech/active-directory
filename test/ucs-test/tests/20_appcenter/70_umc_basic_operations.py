#!/usr/share/ucs-test/runner python3
## desc: |
##  Check basic App-Center Operations via UMC commands within a local testing appcenter.
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
##   - univention-appcenter-dev
## tags: [appcenter]

import logging

import appcentertest as app_test


@app_test.test_case
def test_install_remove(app_center, application):
    """Install and uninstall a simple app with correctness checks."""
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    test.test_install_remove_cycle()


@app_test.test_case
def test_install_remove_twice(app_center, application):
    """
    Install and uninstall a simple app twice. This checks if the app is
    installable after being uninstalled once.
    """
    package = app_test.AppPackage.with_package(name=application)
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    test.test_install_remove_cycle()
    test.test_install_remove_cycle()


@app_test.test_case
def test_install_remove_dependencies(app_center, application):
    """Install and uninstall a simple app with one dependency."""
    dependency = app_test.DebianPackage("my-dependency")
    dependency.build()

    package = app_test.AppPackage.with_package(name=application, depends=[dependency])
    package.build_and_publish()
    package.remove_tempdir()

    test = app_test.TestOperations(app_center, package.app_id)
    test.test_install_remove_cycle()


@app_test.test_case
def test_install_upgrade_remove(app_center, application):
    """Install, upgrade and uninstall a simple app."""
    old = app_test.AppPackage.with_package(name=application, app_version="1.0")

    new = app_test.AppPackage.with_package(name=application, app_version="2.0", app_code=old.app_code)
    old.build_and_publish()
    old.remove_tempdir()

    test = app_test.TestOperations(app_center, old.app_id)
    with test.test_install_safe():
        new.build_and_publish()
        new.remove_tempdir()
        app_test.restart_umc()
        test.test_upgrade()
        test.test_remove()


@app_test.test_case
def test_install_upgrade_remove_dependencies(app_center, application):
    """
    Install, upgrade and uninstall a simple app with one dependency. Both the
    app version and the dependency version change.
    """
    dependency_old = app_test.DebianPackage(name="my-dependency-upgrade", version="1.0")
    dependency_old.build()

    old = app_test.AppPackage.with_package(name=application, app_version="1.0", depends=[dependency_old])

    dependency_new = app_test.DebianPackage(name="my-dependency-upgrade", version="1.0")
    dependency_new.build()

    new = app_test.AppPackage.with_package(name=application, app_version="2.0", app_code=old.app_code, depends=[dependency_new])
    old.build_and_publish()
    old.remove_tempdir()

    test = app_test.TestOperations(app_center, old.app_id)
    with test.test_install_safe():
        new.build_and_publish()
        new.remove_tempdir()
        test.test_upgrade()
        test.test_remove()


def main():
    app_test.app_logger.log_to_stream()
    app_test.app_logger.get_base_logger().setLevel(logging.WARNING)

    with app_test.local_appcenter():
        test_install_remove()
        test_install_remove_twice()
        test_install_remove_dependencies()
        test_install_upgrade_remove()
        test_install_upgrade_remove_dependencies()


if __name__ == '__main__':
    main()
