#!/usr/share/ucs-test/runner python3
## desc: |
##  Check App-Center Operations via UMC commands on multi installations at once
## roles-not: [basesystem]
## packages:
##   - univention-management-console-module-appcenter
##   - univention-appcenter-dev
## tags: [appcenter]

import logging

import appcentertest as app_test


@app_test.test_case
def test_resolve_dependent(app_center, application):
    """Install one simple apps with dependency, check resolve status."""
    package = app_test.DebianPackage(name=application + '2')
    app2 = app_test.AppPackage.from_package(package)
    app2.build_and_publish()
    app2.remove_tempdir()
    package = app_test.DebianPackage(name=application + '1')
    app1 = app_test.AppPackage.from_package(package, app_required_apps=[app2])
    app1.build_and_publish()
    app1.remove_tempdir()

    result = app_center.resolve('install', [app1.app_id])
    print(result)
    # order actually matters
    if len(result['apps']) != 2 or result['apps'][0]['id'] != application + '2' or result['apps'][1]['id'] != application + '1':
        app_test.fail('Should have been resolved to two Apps')


@app_test.test_case
def test_install_two(app_center, application):
    """Install and uninstall two simple apps with correctness checks."""
    package = app_test.DebianPackage(name=application + '2')
    app2 = app_test.AppPackage.from_package(package)
    app2.build_and_publish()
    app2.remove_tempdir()
    package = app_test.DebianPackage(name=application + '1')
    app1 = app_test.AppPackage.from_package(package, app_required_apps=[app2])
    app1.build_and_publish()
    app1.remove_tempdir()

    try:
        result = app_center.install([app2.app_id, app1.app_id])
        test = app_test.TestOperations(app_center, app1.app_id)
        if not test.operation_successfull(result):
            app_test.fail('Failed to install two Apps')
    finally:
        result = app_center.remove([app1.app_id, app2.app_id])


def main():
    app_test.app_logger.log_to_stream()
    app_test.app_logger.get_base_logger().setLevel(logging.WARNING)

    with app_test.local_appcenter():
        test_resolve_dependent()
        test_install_two()


if __name__ == '__main__':
    main()
