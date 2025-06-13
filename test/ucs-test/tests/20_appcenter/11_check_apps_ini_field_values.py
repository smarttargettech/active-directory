#!/usr/share/ucs-test/runner python3
## desc: Check if App .ini has values in settings that are present.
## roles-not: [basesystem]
## tags: [basic, apptest]
## bugs: [33902]
## packages:
##   - univention-management-console-module-appcenter
## exposure: safe

from configparser import Error, RawConfigParser
from glob import glob
from os import path

from univention.appcenter.app_cache import Apps
from univention.testing import utils


OPTIONS_TO_CHECK = ('Contact', 'NotificationEmail')
failures_counter = 0


def fail_the_test():
    """Simply increases the global failures counter."""
    global failures_counter
    failures_counter += 1


def check_file(filename):
    """
    Creates an instance of RawConfigParser, reads a given 'filename' and
    checks if any option from the 'OPTIONS_TO_CHECK' has empty value, i.e:
    test fails if Contact='', but it won't fail if there is no Contact
    option found in the .ini file. Also fails if there is no '@' sign found.
    """
    print("\nChecking file '%s':" % filename)
    IniConfig = RawConfigParser()
    IniConfig.read(filename)

    for option in OPTIONS_TO_CHECK:
        # it is allowed to have no 'option' in the .ini file.
        if IniConfig.has_option('Application', option):
            # if an 'option' is present - it should have a value assigned:
            option_value = IniConfig.get('Application', option)

            if not option_value:
                # 'option' has no value assigned, a failure case:
                fail_the_test()
                print("FAIL: the '%s' option for '%s' file exists, but has"
                      " no value assigned." % (option, filename))
            elif '@' not in option_value:
                # 'option' has no '@' sign in its value,
                # possibly an incorrect e-mail address was specified:
                fail_the_test()
                print("FAIL: the '@' sign for the '%s' option in file '%s'"
                      " was not found. Probably incorrect e-mail address: '%s'"
                      % (option, filename, option_value))


def check_ini_files(dirname):
    """
    Determines the path to App Center Cache dir with .ini files and checks
    all .inis there one by one.
    """
    print("\nThe path to Appcenter .ini files is:", dirname)
    if not path.exists(dirname):
        utils.fail("The path to App center .ini files does not exist.")

    test_path = [fname for fname in glob(path.join(dirname, '*.ini')) if not path.basename(fname).startswith('.')]
    for filename in test_path:
        try:
            check_file(filename)
        except Error as exc:
            fail_the_test()
            print("\nAn error ocured while trying to check the '%s' .ini "
                  "file. Error: %r" % (filename, exc))


def check_ini_files_in_all_directories():
    for appcenter_cache in Apps().get_appcenter_caches():
        for cache in appcenter_cache.get_app_caches():
            check_ini_files(cache.get_cache_dir())


if __name__ == '__main__':
    # find and check all .ini files:
    check_ini_files_in_all_directories()

    if failures_counter:
        utils.fail("\nThere were %d problem(s) detected in the .ini files, "
                   "please check a complete test output." % failures_counter)
    else:
        print("\nNo errors were detected.\n")
