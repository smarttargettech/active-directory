#!/usr/share/ucs-test/runner python3
## desc: |
##  Check App-Center Operation failures with broken dependencies via UMC commands within a local testing appcenter.
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
##   - univention-appcenter-dev
## tags: [appcenter]
## bugs: [44769]

import logging

import appcentertest as app_test


class DebianMockPackage:

    def __init__(self, name="testdeb", version="1.0"):
        self.name = name
        self.version = version
        self.name_version = f"{name} (>= {version})"

    def get_package_name(self):
        return self.name


@app_test.test_case
def test_install_missing_depends(app_center, application):
    """Try to install an app where dependencies are not met (must fail)."""
    dependency = DebianMockPackage("impossible-dependency-" + application)

    app = app_test.AppPackage.with_package(name=application, depends=[dependency])
    app.build_and_publish()
    app.remove_tempdir()

    test = app_test.TestOperations(app_center, app.app_id)
    try:
        test.test_install(test_installed=False)
    except app_test.AppCenterCheckError:
        pass
    else:
        error = "Install of app with missing dependency did not fail."

        info = app_center.get(app.app_id)
        if not app_test.CheckOperations.uninstalled(app.app_id, info):
            error += " And the installation left traces."
        if app_center.is_installed(app.app_id, info=info):
            error += " And is marked as installed."
            #  lets try to be safe and remove the broken app
            app_center.remove([app.app_id])

        app_test.fail(error.strip())


@app_test.test_case
def test_upgrade_missing_depends(app_center, application):
    """
    Try to upgrade an app where dependencies are not met during upgrade
    (must fail).
    """
    dependency = DebianMockPackage("impossible-dependency-" + application)

    old = app_test.AppPackage.with_package(name=application, app_version="1.0")

    new = app_test.AppPackage.with_package(name=application, app_version="2.0", app_code=old.app_code, depends=[dependency])
    old.build_and_publish()
    old.remove_tempdir()

    test = app_test.TestOperations(app_center, old.app_id)
    with test.test_install_safe():
        new.build_and_publish()
        new.remove_tempdir()

        try:
            test.test_upgrade(test_installed=False)
        except app_test.AppCenterCheckError:
            pass
        else:
            error = "Upgrade of app with missing dependency did not fail."
            app_test.fail(error.strip())


@app_test.test_case
def test_install_breaking_packages_dry_run(app_center, application):
    """
    Try to dry-run install an app where breaking packages are installed
    (must fail).
    """
    package_ok = app_test.DebianPackage(application)
    app_ok = app_test.AppPackage.from_package(package_ok)
    app_ok.build_and_publish()
    app_ok.remove_tempdir()

    package_break = app_test.DebianPackage(application + "-break", breaks=[package_ok])
    app_break = app_test.AppPackage.from_package(package_break, app_conflicted_apps=[app_ok])
    app_break.build_and_publish()
    app_break.remove_tempdir()

    test_ok = app_test.TestOperations(app_center, app_ok.app_id)
    with test_ok.test_install_safe():
        test_break = app_test.TestOperations(app_center, app_break.app_id)
        result = app_center.install_dry_run([app_break.app_id])
        if test_break.dry_run_successful(result):
            msg = "Dry-Install of app with breaking app installed did not fail."
            app_test.fail(msg)


@app_test.test_case
def test_install_breaking_packages(app_center, application):
    """
    Try to install an app where breaking packages are installed
    (must fail).
    """
    package_ok = app_test.DebianPackage(application)
    app_ok = app_test.AppPackage.from_package(package_ok)
    app_ok.build_and_publish()
    app_ok.remove_tempdir()

    package_break = app_test.DebianPackage(application + "-break", breaks=[package_ok])
    app_break = app_test.AppPackage.from_package(package_break, app_conflicted_apps=[app_ok])
    app_break.build_and_publish()
    app_break.remove_tempdir()

    test_ok = app_test.TestOperations(app_center, app_ok.app_id)
    with test_ok.test_install_safe():
        test_break = app_test.TestOperations(app_center, app_break.app_id)
        result = app_center.install([app_break.app_id])
        if test_break.operation_successfull(result):
            if app_center.is_installed(app_break.app_id):
                app_center.remove([app_break.app_id])
            app_test.fail("Install of app with breaking app installed did not fail.")


@app_test.test_case
def test_install_conflicting_packages_dry_run(app_center, application):
    """
    Try to dry-run install an app where conflicting packages are installed
    (must fail).
    """
    package_ok = app_test.DebianPackage(application)
    app_ok = app_test.AppPackage.from_package(package_ok)
    app_ok.build_and_publish()
    app_ok.remove_tempdir()

    package_conflict = app_test.DebianPackage(application + "-conflict", conflicts=[package_ok])
    app_conflict = app_test.AppPackage.from_package(package_conflict, app_conflicted_apps=[app_ok])
    app_conflict.build_and_publish()
    app_conflict.remove_tempdir()

    test_ok = app_test.TestOperations(app_center, app_ok.app_id)
    with test_ok.test_install_safe():
        test_conflict = app_test.TestOperations(app_center, app_conflict.app_id)
        result = app_center.install_dry_run([app_conflict.app_id])
        if test_conflict.dry_run_successful(result):
            msg = "Dry-Install of app with conflicting app installed did not fail."
            app_test.fail(msg)


@app_test.test_case
def test_install_conflicting_packages(app_center, application):
    """
    Try to install an app where conflicting packages are installed
    (must fail).
    """
    package_ok = app_test.DebianPackage(application)
    app_ok = app_test.AppPackage.from_package(package_ok)
    app_ok.build_and_publish()
    app_ok.remove_tempdir()

    package_conflict = app_test.DebianPackage(application + "-conflict", conflicts=[package_ok])
    app_conflict = app_test.AppPackage.from_package(package_conflict, app_conflicted_apps=[app_ok])
    app_conflict.build_and_publish()
    app_conflict.remove_tempdir()

    test_ok = app_test.TestOperations(app_center, app_ok.app_id)
    with test_ok.test_install_safe():
        test_conflict = app_test.TestOperations(app_center, app_conflict.app_id)
        result = app_center.install([app_conflict.app_id])
        if test_conflict.operation_successfull(result):
            if app_center.is_installed(app_conflict.app_id):
                app_center.remove([app_conflict.app_id])
            app_test.fail("Install of app with conflicting app installed did not fail.")


def main():
    app_test.app_logger.log_to_stream()
    app_test.app_logger.get_base_logger().setLevel(logging.WARNING)

    with app_test.local_appcenter():
        test_install_missing_depends()
        test_upgrade_missing_depends()
        test_install_breaking_packages_dry_run()
        test_install_breaking_packages()
        test_install_conflicting_packages_dry_run()
        test_install_conflicting_packages()


if __name__ == '__main__':
    main()
