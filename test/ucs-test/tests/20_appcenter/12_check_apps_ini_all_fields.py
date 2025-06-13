#!/usr/share/ucs-test/runner python3
## desc: Checks Apps .ini field values, description length, optional values.
## roles-not: [basesystem]
## tags: [basic, apptest]
## bugs: [36730]
## packages:
##   - univention-management-console-module-appcenter
## exposure: safe

import re
from configparser import NoOptionError, NoSectionError, RawConfigParser
from optparse import OptionParser
from re import compile as regex_compile
from sys import stderr

from univention.appcenter.app_cache import Apps
from univention.testing import utils


failures = 0


class AppCheck:

    def __init__(self, pname):
        self.pname = pname
        self.config = RawConfigParser()
        self.config.read((pname,))

    def log(self, msg, *args):
        """
        Prints the given 'msg' with 'args' preceded by path to file unless
        '--quiet' argument was given.
        """
        if not parsed.quiet:
            print('FILE:', self.pname, msg % args)

    def check(self):
        """
        Performs the actual 'self.pname' file checks.
        Checks can be skipped when respective App is not installed
        and no '--all' argument was given or if App instance cannot be created.
        """
        print("\nChecking file '%s':" % self.pname)
        try:
            appid = self.config.get('Application', 'ID')
        except (NoSectionError, NoOptionError):
            raise Error('No [Application] ID given...')
        for section in self.config.sections():
            if section == 'Appliances-scenarios':
                continue
            with Section(self, section, appid) as sec:
                if section == 'Application':
                    sec.check_all(sec.APPLICATION)
                elif section.startswith('Sizing: '):
                    sec.check_all(sec.SIZING)
                else:
                    sec.check_all(sec.TRANSLATION)


class Error(Exception):

    def __init__(self, msg):
        global failures
        failures += 1
        print("\nERROR:", msg)


class Optional(Exception):
    # simply an exception to be raised/caught
    # when optional values are checked:
    pass


class Fatal(Exception):

    # raised when required value is missing
    def __init__(self, msg):
        global failures
        failures += 1
        print("\nFATAL:", msg)


class Value:

    DOMAIN = r'(?:[0-9A-Za-z]+(?:[0-9A-Za-z-]*[0-9A-Za-z])?\.)+[0-9A-Za-z-]+(?:[0-9A-Za-z-]*[0-9A-Za-z])?'
    PATH = r'/[!#$%&+,./0-9:;=?@A-Z_a-z-]*'

    RE_EMAIL = regex_compile(r'^.+@' + DOMAIN + r'$')
    RE_WWW = regex_compile(r'^https?://' + DOMAIN + r'(?::\d+)?(?:' + PATH + r')?$')
    RE_CAPACITY = regex_compile(r'\d+(?:\s*[G]B)?$')
    RE_URL = regex_compile(r'^(?:https?://' + DOMAIN + r'(?::\d+)?)?' + PATH + r'$')

    def __init__(self, value, appid):
        self.value = value
        self.appid = appid

    def __str__(self):
        return str(self.value)

    def required(self):
        if not self.value:
            raise Fatal('Required value or/and section is missing.')

    def optional(self):
        if not self.value:
            # raise and catch later the exception to stop checks.
            raise Optional()

    def is_bool(self):
        if self.value in ('True', 'False', 'true', 'false'):
            return
        raise Error('Not a boolean: %s' % self.value)

    def is_n_chars_long(self, length):
        if len(self.value) <= length:
            return
        raise Error('Over %d chars long:\n >%s<>%s<' % (length,
                    self.value[:length + 1], self.value[length + 1:]))

    def is_180c(self):
        return self.is_n_chars_long(180)

    def is_email(self):
        if self.RE_EMAIL.match(self.value):
            return
        raise Error('No email: "%s"' % self.value)

    def is_www(self):
        if self.RE_WWW.match(self.value):
            return
        raise Error('No WWW: "%s"' % self.value)

    def is_url(self):
        if self.RE_URL.match(self.value):
            return
        raise Error('No URL: "%s"' % self.value)

    def is_role(self):
        ALLOWED = {
            'domaincontroller_master',
            'domaincontroller_backup',
            'domaincontroller_slave',
            'memberserver',
        }

        values = map(str.strip, self.value.split(','))
        if set(values) - ALLOWED:
            raise Error('Invalid server role: "%s"' % self.value)

    def is_arch(self):
        ALLOWED = {'amd64', 'i386'}
        if set(re.split(r'\s*,\s*', self.value)) - ALLOWED:
            raise Error('Invalid architectures: "%s"' % self.value)

    def is_capacity(self):
        if self.RE_CAPACITY.match(self.value):
            return
        raise Error('Wrong capacity: "%s"' % self.value)

    def deprecated_master_packages(self):
        if self.value:
            if self.appid not in ['kopano-core', 'agorumcore-pro', 'asterisk4ucs', 'bareos', 'fetchmail', 'openvpn4ucs', 'oxseforucs', 'plucs', 'sugarcrm', 'zarafa', 'self-service']:
                raise Error('Should not have DefaultPackagesMaster!!')

    def is_category(self):
        ALLOWED = {'admin', 'service', 'False'}
        if self.value in ALLOWED:
            return
        raise Error('Not an allowed category: "%s"' % self.value)


class Section:

    APPLICATION = {
        'ADMemberIssueHide': ('optional',),
        'ADMemberIssuePassword': ('optional',),
        'Categories': ('optional',),
        'Code': ('required',),
        'ConflictedApps': ('optional',),
        'ConflictedSystemPackages': ('optional',),
        'Contact': ('required', 'is_email'),
        'DefaultPackagesMaster': ('optional', 'deprecated_master_packages'),
        'DefaultPackages': ('optional',),
        'Description': ('required', 'is_180c'),
        'EmailRequired': ('optional',),
        'EndOfLife': ('optional', 'is_bool'),
        'ID': ('required',),
        'LicenseFile': ('optional',),
        'LongDescription': ('required',),
        'Maintainer': ('optional',),
        'MinPhysicalRAM': ('optional', 'is_capacity'),
        'Name': ('required',),
        'NotificationEmail': ('optional', 'is_email'),
        'NotifyVendor': ('optional', 'is_bool'),
        'RequiredApps': ('optional',),
        'Screenshot': ('optional',),
        'ServerRole': ('optional', 'is_role'),
        'ShopURL': ('optional', 'is_www'),
        'SupportedArchitectures': ('optional', 'is_arch'),
        'SupportURL': ('optional', 'is_www'),
        'UCSOverviewCategory': ('optional', 'is_category'),
        'UMCModuleFlavor': ('optional',),
        'UMCModuleName': ('optional',),
        'UserActivationRequired': ('optional', 'is_bool'),
        'UseShop': ('optional', 'is_bool'),
        'Vendor': ('optional',),
        'Version': ('required',),
        'VisibleInAppCatalogue': ('optional', 'is_bool'),
        'WebInterfaceName': ('optional',),
        'WebInterface': ('optional', 'is_url'),
        'WebsiteMaintainer': ('optional', 'is_www'),
        'Website': ('optional', 'is_www'),
        'Websitevendor': ('optional', 'is_www'),
        'WithoutRepository': ('optional', 'is_bool')}

    SIZING = {
        'CPU': ('optional',),
        'RAM': ('optional', 'is_capacity'),
        'Disk': ('optional', 'is_capacity')}

    TRANSLATION = {
        'Name': ('optional',) + APPLICATION['Name'],
        'Website': APPLICATION['Website'],
        'SupportURL': APPLICATION['SupportURL'],
        'ShopURL': APPLICATION['ShopURL'],
        'Description': APPLICATION['Description'],
        'LongDescription': APPLICATION['LongDescription']}

    def __init__(self, check, section, appid):
        self.config = check.config
        self.section = section
        self.log = check.log
        self.appid = appid

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        if not exc_type:
            return

        if issubclass(exc_type, NoSectionError):
            self.log('[%s] missing', self.section)

    def check_all(self, options):
        for option, checks in options.items():
            self.check(option, *checks)
            self.config.remove_option(self.section, option)

        for option, value in self.config.items(self.section):
            self.log('[%s].%s: Remaining %s', self.section, option, value)

    def check(self, option, *checks):
        value = self.get(option)
        for cname in checks:
            try:
                check = getattr(value, cname)
                check()
            except Fatal as exc:
                self.log('\nSECTION: [%s].%s %s\n',
                         self.section, option, exc)
                return

            except Error as exc:
                self.log('\nSECTION: [%s].%s %s\n',
                         self.section, option, exc)

            except Optional:
                # not a real error, just stops further checks
                return

    def get(self, option):
        try:
            value = self.config.get(self.section, option)
        except NoOptionError as exc:
            if not parsed.quiet:
                print(exc, file=stderr)
            value = None
        return Value(value, self.appid)


def exclude_ignored(names, remove):
    """Removes the given 'remove' from the given 'names' when it is in."""
    for name in remove:
        try:
            names.remove(name)
        except ValueError:
            pass


def parse_args():
    """
    Creates an instance of OptionParser and parses arguments.
    The App Center's 'CACHE_DIR' will be used by default.
    To use args run interactively via: python filename ...
    """
    parser = OptionParser(description=("Check Apps .ini files (Optional values, description length, allowed values, allowed chars)"))

    parser.add_option("-q", "--quiet",
                      default=False,
                      dest="quiet",
                      action="store_true",
                      help="Decrease the verbosity.")

    parser.add_option("-a", "--all",
                      default=False,
                      dest="check_all",
                      action="store_true",
                      help=("Force check of all Apps .ini. By default "
                            "checks only currently installed Apps."))

    options, _args = parser.parse_args()
    return options


if __name__ == '__main__':
    """
    Parses the given arguments or uses defaults.
    Checks either a specified single file or a folder with .ini files.
    By default checks only the installed (according to APPCENTER_FILE) apps.

    WARNING: make sure the App center cache dir has only the most recent
    .ini files, otherwise test might fail when old versions are incorrect.

    (Won't happen with Jenkins instances as those are 'freshly' spawned)
    """
    parsed = parse_args()
    if not parsed.check_all:
        # check only .ini of the apps that are installed
        apps = Apps().get_all_locally_installed_apps()
    else:
        apps = Apps().get_all_apps()

    for app in apps:
        AppCheck(app.get_ini_file()).check()

    if failures:
        utils.fail("\nThere were %d error(s) detected. Please check "
                   "the complete test output.\n" % failures)
    print("\nNo errors were detected.\n")
