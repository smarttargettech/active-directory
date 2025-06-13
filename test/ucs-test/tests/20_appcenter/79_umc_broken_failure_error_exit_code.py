#!/usr/share/ucs-test/runner python3
## desc: |
##  Check App-Center Operation failures with broken apps (exit 1 in {pre,post}{inst,rm}) via UMC commands within a local testing appcenter.
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
##   - univention-appcenter-dev
## tags: [appcenter]

import logging
import os
import subprocess

from univention.config_registry import ConfigRegistry

import appcentertest as app_test


def _test_app_installation_fails(test):
    try:
        with test.test_install_safe(test_installed=False):
            pass
    except app_test.AppCenterCheckError:
        if test.app_center.is_installed(test.application):
            app_test.fail("Broken application remained on the system.")
    else:
        app_test.fail("Install of broken app did not produce dpkg errors.")
    finally:
        cleanup(test.application)


def _test_app_uninstallation_fails(test):
    try:
        with test.test_install_safe():
            try:
                test.test_remove(test_uninstalled=True)
            except app_test.AppCenterCheckError:
                pass
            else:
                app_test.fail("Uninstall of broken app did not produce dpkg errors.")
    finally:
        cleanup(test.application)


@app_test.test_case
def test_install_preinst_error(app_center, application):
    """
    Try to install and uninstall an app that contains an error in `preinst`
    (exit 1). No traces must be left and the app must be reinstallable.
    """
    package = app_test.DebianPackage(name=application)
    package.create_debian_file_from_buffer("preinst", "\nexit 1\n")

    app = app_test.AppPackage.from_package(package)
    app.build_and_publish()
    app.remove_tempdir()

    test = app_test.TestOperations(app_center, app.app_id)
    _test_app_installation_fails(test)


@app_test.test_case
def test_install_postinst_error(app_center, application):
    """
    Try to install and uninstall an app that contains an error in `postinst`
    (exit 1). No traces must be left and the app must be reinstallable.
    """
    package = app_test.DebianPackage(name=application)
    package.create_debian_file_from_buffer("postinst", "\nexit 1\n")

    app = app_test.AppPackage.from_package(package)
    app.build_and_publish()
    app.remove_tempdir()

    test = app_test.TestOperations(app_center, app.app_id)
    _test_app_installation_fails(test)


@app_test.test_case
def test_uninstall_prerm_error(app_center, application):
    """
    Try to install and uninstall an app that contains an error in `prerm`
    (exit 1). No traces must be left and the app must be reinstallable.
    """
    package = app_test.DebianPackage(name=application)
    package.create_debian_file_from_buffer("prerm", "\nexit 1\n")

    app = app_test.AppPackage.from_package(package)
    app.build_and_publish()
    app.remove_tempdir()

    test = app_test.TestOperations(app_center, app.app_id)
    _test_app_uninstallation_fails(test)


@app_test.test_case
def test_uninstall_postrm_error(app_center, application):
    """
    Try to install and uninstall an app that contains an error in `postrm`
    (exit 1). No traces must be left and the app must be reinstallable.
    """
    package = app_test.DebianPackage(name=application)
    package.create_debian_file_from_buffer("postrm", "\nexit 1\n")

    app = app_test.AppPackage.from_package(package)
    app.build_and_publish()
    app.remove_tempdir()

    test = app_test.TestOperations(app_center, app.app_id)
    _test_app_uninstallation_fails(test)


def cleanup(application):
    ucr = ConfigRegistry()
    ucr.load()
    username = ucr.get('tests/domainadmin/account').split(',')[0][len('uid='):]
    pwdfile = ucr.get('tests/domainadmin/pwdfile')
    subprocess.check_call(['univention-app', 'register', application, '--undo-it', '--noninteractive', '--username', username, '--pwdfile', pwdfile])
    ext = application.split('-')[2]
    try:
        os.unlink(f'/var/lib/dpkg/info/{application}.{ext}')
    except OSError:
        pass
    else:
        subprocess.check_call(['dpkg', '--remove', application])


def main():
    app_test.app_logger.log_to_stream()
    app_test.app_logger.get_base_logger().setLevel(logging.WARNING)

    with app_test.local_appcenter():
        test_install_preinst_error()
        test_install_postinst_error()
        test_uninstall_prerm_error()
        test_uninstall_postrm_error()


if __name__ == '__main__':
    main()
