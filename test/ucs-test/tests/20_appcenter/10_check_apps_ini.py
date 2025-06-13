#!/usr/share/ucs-test/runner python3
## desc: Simple check if App's .ini(s) can be used.
## roles-not: [basesystem]
## tags: [basic, apptest]
## bugs: [30508]
## packages:
##   - univention-appcenter
## exposure: safe

from glob import glob
from os import path

from univention.appcenter.actions import get_action
from univention.appcenter.app import App
from univention.testing import utils


failures_counter = 0
apps = []


def check_file(filename, local):
    """
    Tries to create an instance of the App center Application for the given
    'filename'.
    """
    app = App.from_ini(filename, local)
    if app:

        apps.append(app)
        print("OK")

    else:
        global failures_counter
        failures_counter += 1
        print("\nAn error occurred with an .ini file '%s' while trying to "
              "create App center 'App' instance with it'\n"
              % (filename))


def print_all_apps_versions(number_of_files):
    """Prints overall statistics and versions of all Apps that were found."""
    print("\nTotal", number_of_files, ".ini files for", len(apps), "apps were found:\n")

    for app in apps:
        print(repr(app))


def check_ini_files():
    """Checks all .ini files that are found in the CACHE_DIR."""
    test_locales = ('de', 'en')
    test_path = [fname for fname in glob('/var/cache/univention-appcenter/*/*/*.ini') if not path.basename(fname).startswith('.')]

    for local in test_locales:
        for filename in test_path:
            print("Checking", filename, "in", local, "locale:")
            check_file(filename, local)

    print_all_apps_versions(len(test_path))


if __name__ == '__main__':
    update = get_action('update')
    update.call()

    # find and check all .ini files:
    check_ini_files()

    if failures_counter:
        utils.fail("There were App's .ini(s) that cannot be "
                   "evaluated correctly. Total: %d error(s)."
                   % failures_counter)
    else:
        print("\nNo errors were detected.\n")
