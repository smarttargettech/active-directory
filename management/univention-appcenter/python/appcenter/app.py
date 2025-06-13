#!/usr/bin/python3
#
# Univention App Center
#  Application class
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2015-2025 Univention GmbH
#
# https://www.univention.de/
#
# All rights reserved.
#
# The source code of this program is made available
# under the terms of the GNU Affero General Public License version 3
# (GNU AGPL V3) as published by the Free Software Foundation.
#
# Binary versions of this program provided by Univention to you as
# well as other copyrighted, protected or trademarked materials like
# Logos, graphics, fonts, specific documentations and configurations,
# cryptographic keys etc. are subject to a license agreement between
# you and Univention and not subject to the GNU AGPL V3.
#
# In the case you use this program under the terms of the GNU AGPL V3,
# the program is provided in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public
# License with the Debian GNU/Linux or Univention distribution in file
# /usr/share/common-licenses/AGPL-3; if not, see
# <https://www.gnu.org/licenses/>.
#

from __future__ import annotations

import inspect
import os
import os.path
import platform
import re
from configparser import NoOptionError, NoSectionError, RawConfigParser
from copy import copy
from itertools import zip_longest
from urllib.parse import urlsplit
from weakref import ref

from univention.appcenter.ini_parser import read_ini_file
from univention.appcenter.log import get_base_logger
from univention.appcenter.meta import UniventionMetaClass, UniventionMetaInfo
from univention.appcenter.packages import get_package_manager, packages_are_installed
from univention.appcenter.settings import Setting
from univention.appcenter.ucr import ucr_get, ucr_includes, ucr_is_true, ucr_load, ucr_run_filter
from univention.appcenter.utils import (
    _, app_ports, container_mode, get_current_ram_available, get_free_disk_space, get_locale, mkdir,
)


CACHE_DIR = '/var/cache/univention-appcenter'
LOCAL_ARCHIVE = '/usr/share/univention-appcenter/archives/all.tar.gz'
LOCAL_ARCHIVE_DIR = '/usr/share/univention-appcenter/archives/'
SHARE_DIR = '/usr/share/univention-appcenter/apps'
DATA_DIR = '/var/lib/univention-appcenter/apps'
CONTAINER_SCRIPTS_PATH = '/usr/share/univention-docker-container-mode/'

app_logger = get_base_logger().getChild('apps')


class LooseVersion:  # noqa: PLW1641
    """
    Represents a loose version number for comparison purposes.
    LooseVersion is a class that allows comparison of version numbers in a
    loose manner. It breaks down version strings into components, considering
    all alphanumeric parts, and provides methods for comparison.
    The comparison is based on the order of components and is case-sensitive.

    Examples:
    >>> LooseVersion("1.1") < LooseVersion("1.2")
    True
    >>> LooseVersion("1.1") > LooseVersion("1.2")
    False
    >>> LooseVersion("1.1") <= LooseVersion("1.2")
    True
    >>> LooseVersion("1.1") >= LooseVersion("1.2")
    False
    >>> LooseVersion("1.1") == LooseVersion("1.2")
    False
    >>> LooseVersion("1.1a") < LooseVersion("1.1b")
    True
    >>> LooseVersion("1.1A") < LooseVersion("1.1B")
    True
    >>> LooseVersion("1.1A") < LooseVersion("1.1a")
    True
    >>> LooseVersion("1.1a") < LooseVersion("1.1b")
    True
    >>> LooseVersion("1.1a") < LooseVersion("1.2")
    True
    >>> LooseVersion("5.2 v3") < LooseVersion("5.2 v10")
    True
    >>> LooseVersion("1.0.1") == LooseVersion("1.0-1")
    True
    >>> LooseVersion("1.0.0") != LooseVersion("1.0-1")
    True
    >>> LooseVersion("1.0.1") == "1.0-1"
    True
    >>> LooseVersion("1.0-10") >= "1.0-9"
    True
    >>> LooseVersion("1.0-10") < "1.0-90"
    True
    >>> "1.0.2" <= LooseVersion("1.0.2")
    True
    """

    RE_COMPONENT_SEPARATOR = re.compile(r'(\d+ | [a-z]+ | [A-Z]+)', re.VERBOSE)

    def __init__(self, version: LooseVersion | str):
        self._version = str(version)
        self._components = []
        self._parse()

    def __str__(self) -> str:
        return self._version

    def __repr__(self) -> str:
        return f"LooseVersion('{self}')"

    def __eq__(self, other: LooseVersion | str) -> bool:
        return self._compare(LooseVersion(other)) == 0 if isinstance(other, LooseVersion | str) else NotImplemented

    def __lt__(self, other: LooseVersion | str) -> bool:
        return self._compare(LooseVersion(other)) < 0 if isinstance(other, LooseVersion | str) else NotImplemented

    def __le__(self, other: LooseVersion | str) -> bool:
        return self._compare(LooseVersion(other)) <= 0 if isinstance(other, LooseVersion | str) else NotImplemented

    def __gt__(self, other: LooseVersion | str) -> bool:
        return self._compare(LooseVersion(other)) > 0 if isinstance(other, LooseVersion | str) else NotImplemented

    def __ge__(self, other: LooseVersion | str) -> bool:
        return self._compare(LooseVersion(other)) >= 0 if isinstance(other, LooseVersion | str) else NotImplemented

    def _parse(self) -> None:
        """
        Parse the version string and populate the self._components list.

        >>> v = LooseVersion('1.23 v40-2')
        >>> v._components
        [1, 23, 'v', 40, 2]
        """
        self._components = [self._try_int(obj) for obj in self.RE_COMPONENT_SEPARATOR.split(self._version) if obj.isalnum()]

    def _compare(self, other: LooseVersion) -> int:
        """
        Compare two LooseVersion objects and return -1 if self < other,
        0 if self == other, and 1 if self > other.

        >>> v1 = LooseVersion('1.5.1')
        >>> v2 = LooseVersion('1.5.2b2')
        >>> v1._compare(v2)
        -1
        >>> examples = [
        ...     ('5.0-6+e897', '5.0-6+e12', 1),
        ...     ('5.2 v3', '5.2 v10', -1),
        ...     ('5.2 v10.123', '5.2 v10', 1),
        ...     ('20.1a-44', '20.1-44', 1),
        ...     ('5.v v3', '5.2 v10', 1),
        ...     ('5v3', '5v1', 1),
        ...     ('3.2.pl0', '3.1.1.6', 1),
        ...     ('2g6', '11g', -1),
        ...     ('0.960923', '2.2beta29', -1),
        ...     ('1.13++', '5.5.kw', -1),
        ...     ('3.4j', '1996.07.12', -1),
        ...     ('8.02-0', '8.02.0', 0),
        ...     ('161', '3.10a', 1),
        ...     ('1.5.1', '1.5.2b2', -1),
        ...     ('5.2 v10#$12/3', '5.2 v10.12.33', -1),
        ...     ('5.2-1', '5.2', 1),
        ... ]
        >>> all(LooseVersion(v1)._compare(LooseVersion(v2)) == result for v1, v2, result in examples)
        True
        """
        for i, j in zip_longest(self._components, other._components):
            if not isinstance(i, type(j)) and i is not None and j is not None:
                i = str(i)
                j = str(j)
            if i == j:
                continue
            elif i is None:
                return -1
            elif j is None:
                return 1
            elif i < j:
                return -1
            elif i > j:
                return 1
        return 0

    def _try_int(self, string: str) -> int | str:
        try:
            return int(string)
        except ValueError:
            return string


class CaseSensitiveConfigParser(RawConfigParser):

    def optionxform(self, optionstr):
        return optionstr


class Requirement(UniventionMetaInfo):
    save_as_list = '_requirements'
    auto_set_name = True
    pop = True

    def __init__(self, actions, hard, func):
        self.actions = actions
        self.hard = hard
        self.func = func

    def test(self, app, function, package_manager):
        method = getattr(app, self.name)
        kwargs = {}
        arguments = inspect.getfullargspec(method).args[1:]  # remove self
        if 'function' in arguments:
            kwargs['function'] = function
        if 'package_manager' in arguments:
            kwargs['package_manager'] = package_manager
        return method(**kwargs)

    def contribute_to_class(self, klass, name):
        super().contribute_to_class(klass, name)
        setattr(klass, name, self.func)


def hard_requirement(*actions):
    return lambda func: Requirement(actions, True, func)


def soft_requirement(*actions):
    return lambda func: Requirement(actions, False, func)


class AppAttribute(UniventionMetaInfo):
    save_as_list = '_attrs'
    auto_set_name = True

    def __init__(self, required=False, default=None, regex=None, choices=None, localisable=False, localisable_by_file=None, strict=True):
        super().__init__()
        self.regex = regex
        self.default = default
        self.required = required
        self.choices = choices
        self.localisable = localisable
        self.localisable_by_file = localisable_by_file
        self.strict = strict

    def test_regex(self, regex, value):
        if value is not None and not re.match(regex, value):
            raise ValueError('Invalid format')

    def test_choices(self, value):
        if value is not None and value not in self.choices:
            raise ValueError('Not allowed')

    def test_required(self, value):
        if value is None:
            raise ValueError('Value required')

    def test_type(self, value, instance_type):
        if value is not None:
            if instance_type is None:
                instance_type = str
            if not isinstance(value, instance_type):
                raise ValueError('Wrong type')

    def test(self, value):
        try:
            if self.required:
                self.test_required(value)
            self.test_type(value, str)
            if self.choices:
                self.test_choices(value)
            if self.regex:
                self.test_regex(self.regex, value)
        except ValueError as e:
            if self.strict:
                raise
            else:
                app_logger.warning(str(e))

    def parse(self, value):
        return value

    def get_value(self, component_id, ini_parser, meta_parser, locale):
        ini_attr_name = self.name.replace('_', '')
        priority_sections = [(meta_parser, 'Application'), (ini_parser, 'Application')]
        if self.localisable and locale:
            priority_sections.insert(0, (meta_parser, locale))
            priority_sections.insert(2, (ini_parser, locale))
        value = self.default
        for parser, section in priority_sections:
            try:
                value = parser.get(section, ini_attr_name)
            except (NoSectionError, NoOptionError):
                pass
            else:
                break
        value = self.parse(value)
        self.test(value)
        return value

    def post_creation(self, app):
        pass

    # TODO: remove. deprecated
    def parse_with_ini_file(self, value, ini_file):
        return self.parse(value)

    # TODO: remove. deprecated
    def get(self, value, ini_file):
        if value is None:
            value = copy(self.default)
        try:
            value = self.parse_with_ini_file(value, ini_file)
        except ValueError as exc:
            raise ValueError('%s: %s (%r): %s' % (ini_file, self.name, value, exc))
        else:
            self.test(value)
            return value


class AppComponentIDAttribute(AppAttribute):
    def get_value(self, component_id, ini_parser, meta_parser, locale):
        return component_id


class AppUCSVersionAttribute(AppAttribute):
    def get_value(self, component_id, ini_parser, meta_parser, locale):
        return ucr_get('version/version')


class AppBooleanAttribute(AppAttribute):

    def test_type(self, value, instance_type):
        super().test_type(value, bool)

    def parse(self, value):
        if value in [True, False]:
            return value
        if value is not None:
            value = RawConfigParser.BOOLEAN_STATES.get(str(value).lower())
            if value is None:
                raise ValueError('Invalid value')
        return value


class AppIntAttribute(AppAttribute):

    def test_type(self, value, instance_type):
        super().test_type(value, int)

    def parse(self, value):
        if value is not None:
            return int(value)


class AppListAttribute(AppAttribute):

    def parse(self, value):
        if value == '':
            value = None
        if isinstance(value, str):
            value = re.split(r'\s*,\s*', value)
        if value is None:
            value = []
        return value

    def test_required(self, value):
        if not value:
            raise ValueError('Value required')

    def test_type(self, value, instance_type):
        super().test_type(value, list)

    def test_choices(self, value):
        if not value:
            return
        for val in value:
            super().test_choices(val)

    def test_regex(self, regex, value):
        if not value:
            return
        for val in value:
            super().test_regex(regex, val)


class AppFromFileAttribute(AppAttribute):
    def __init__(self, klass):
        self.klass = klass

    def get_value(self, component_id, ini_file, meta_parser, locale):
        return None

    def post_creation(self, app):
        values = getattr(app, 'get_%s' % self.name)()
        setattr(app, self.name, [value.to_dict() for value in values])

    def contribute_to_class(self, klass, name):
        super().contribute_to_class(klass, name)

        def _get_objects_fn(_self):
            cache_name = '_%s_cache' % name
            if not hasattr(_self, cache_name):
                app_attributes = self.klass.all_from_file(_self.get_cache_file(name), _self.get_locale())
                if name == "settings":
                    custom_settings_file = os.path.join(DATA_DIR, _self.id, 'custom.settings')
                    if os.path.isfile(custom_settings_file):
                        app_logger.debug(f"custom settings {custom_settings_file} file found")
                        app_attributes += self.klass.all_from_file(custom_settings_file, _self.get_locale())
                setattr(_self, cache_name, app_attributes)
            return getattr(_self, cache_name)

        setattr(klass, 'get_%s' % name, _get_objects_fn)


class AppRatingAttribute(AppListAttribute):
    def post_creation(self, app):
        value = []
        ratings = app.get_app_cache_obj().get_appcenter_cache_obj().get_ratings()
        meta_parser = read_ini_file(app.get_cache_file('meta'))
        for rating in ratings:
            try:
                val = int(meta_parser.get('Application', rating.name))
            except (ValueError, TypeError, NoSectionError, NoOptionError):
                pass
            else:
                rating = rating.to_dict()
                rating['value'] = val
                value.append(rating)
        setattr(app, self.name, value)


# TODO: remove; unused
class AppLocalisedListAttribute(AppListAttribute):
    _cache = {}

    @classmethod
    def _translate(cls, fname, locale, value, reverse=False):
        if fname not in cls._cache:
            cls._cache[fname] = translations = {}
            cached_file = os.path.join(CACHE_DIR, '.%s' % fname)
            localiser = read_ini_file(cached_file, CaseSensitiveConfigParser)
            for section in localiser.sections():
                translations[section] = dict(localiser.items(section))
        translations = cls._cache[fname].get(locale)
        if translations:
            if reverse:
                for k, v in translations.items():
                    if v == value:
                        value = k
                        break
            else:
                if value in translations:
                    value = translations[value]
        return value

    def get_value(self, component_id, ini_parser, meta_parser, locale):
        value = super().get_value(component_id, ini_parser, meta_parser, locale)
        if self.localisable_by_file and locale:
            for i, val in enumerate(value):
                value[i] = self._translate(self.localisable_by_file, locale, val)
        return value


class AppLocalisedAppCategoriesAttribute(AppListAttribute):
    def post_creation(self, app):
        value = getattr(app, self.name)
        cache = app.get_app_cache_obj().get_appcenter_cache_obj()
        value = [cache.get_app_categories().get(val.lower(), val) for val in value]
        setattr(app, self.name, value)


class AppAttributeOrFalseOrNone(AppBooleanAttribute):

    def __init__(self, required=False, default=None, regex=None, choices=None, localisable=False, localisable_by_file=None, strict=True):
        choices = (choices or [])[:]
        choices.extend([None, False])
        super().__init__(required, default, regex, choices, localisable, localisable_by_file, strict)

    def parse(self, value):
        if value == 'False':
            value = False
        elif value == 'None':
            value = None
        return value

    def test_type(self, value, instance_type):
        if value is not False and value is not None:
            super(AppBooleanAttribute, self).test_type(value, str)


class AppAttributeOrTrueOrNone(AppBooleanAttribute):
    def parse(self, value):
        if value == 'True':
            value = True
        elif value == 'None':
            value = None
        return value

    def test_type(self, value, instance_type):
        if value is not True and value is not None:
            super(AppBooleanAttribute, self).test_type(value, str)


class AppFileAttribute(AppAttribute):
    # TODO: UCR TOKEN

    def __init__(self, required=False, default=None, regex=None, choices=None, localisable=True):
        # localisable=True !
        super().__init__(required, default, regex, choices, localisable)

    def get_value(self, component_id, ini_parser, meta_parser, locale):
        return None

    def post_creation(self, app):
        value = None
        fname = self.name.upper()
        filenames = [fname, '%s_EN' % fname]
        if self.localisable:
            locale = app.get_locale()
            if locale:
                filenames.insert(0, '%s_%s' % (fname, locale.upper()))
        for filename in filenames:
            try:
                with open(app.get_cache_file(filename)) as fd:
                    value = ''.join(fd.readlines()).strip()
            except OSError:
                pass
            else:
                break
        setattr(app, self.name, value)

    # TODO: remove. deprecated - attention: install_base.py uses it
    def get_filename(self, ini_file):
        directory = os.path.dirname(ini_file)
        component_id = os.path.splitext(os.path.basename(ini_file))[0]
        fname = self.name.upper()
        localised_file_exts = [fname, '%s_EN' % fname]
        if self.localisable:
            locale = get_locale()
            if locale:
                localised_file_exts.insert(0, '%s_%s' % (fname, locale.upper()))
        for localised_file_ext in localised_file_exts:
            filename = os.path.join(directory, '%s.%s' % (component_id, localised_file_ext))
            if os.path.exists(filename):
                return filename


class AppDockerScriptAttribute(AppAttribute):

    def set_name(self, name):
        self.default = os.path.join(CONTAINER_SCRIPTS_PATH, name[14:])
        super().set_name(name)


class AppMetaClass(UniventionMetaClass):

    def __new__(mcs, name, bases, attrs):
        new_cls = super().__new__(mcs, name, bases, attrs)
        # cleanup attrs
        offset = 0
        for i, attr in enumerate(new_cls._attrs[:]):
            try:
                explicit_attr = attrs[attr.name]
            except KeyError:
                pass
            else:
                if not isinstance(explicit_attr, AppAttribute):
                    app_logger.debug('Removing %s for %r' % (attr.name, explicit_attr))
                    new_cls._attrs.pop(i + offset)
                    offset -= 1
            while True:
                old_attr = new_cls.get_attr(attr.name)
                if old_attr is attr:
                    break
                if old_attr is None:
                    break
                app_logger.debug('Removing old %s for new %r' % (old_attr.name, attr))
                new_cls._attrs.remove(old_attr)
        return new_cls


class App(metaclass=AppMetaClass):  # noqa: PLW1641
    """
    This is the main App class. It represents *one version* of the App in
    the Univention App Center. It is mainly a container for a parsed ini
    file.

    The attributes are described below. Technically they are added to the
    class by the metaclass UniventionMetaClass. The magical parsing stuff
    happens in :py:meth:`from_ini()`. In :py:meth:`__init__` you can pass
    any value you want and the App will just accept it.

    Real work with the App class is done in the actions, not this class
    itself.

    :ivar id: A unique ID for the App. Different versions of the same
        App have the same ID, though.
    :ivar code: An internal ID like 2-char value that has no meaning
        other than some internal reporting processing.
        Univention handles this, not the App Provider.
    :ivar component_id: The internal name of the repository on the App
        Center server. Not necessarily (but often) named after
        the *id*. Not part of the ini file.
    :ivar ucs_version: Not part of the ini file.
    :ivar name: The displayed name of the App.
    :ivar version: Version of the App. Needs to be unique together with
        with the *id*. Versions are compared against each other
        using a very loose version comparison.
    :ivar install_permissions: Whether a license needs to be bought in order
        to install the App.
    :ivar install_permissions_message: A message displayed to the user
        when the App needs *install_permissions*, but the user
        has not yet bought the App.
    :ivar logo: The file name of the logo of the App. It is used in the
        App Center overview when all Apps are shown in a
        gallery. As the gallery items are squared, the logo
        should be squared, too. Not part of the App class.
    :ivar logo_detail_page: The file name of a "bigger" logo. It is shown
        in the detail page of the App Center. Useful when there
        is a stretched version with the logo, the name, maybe a
        claim. If not given, the *logo* is used on the detail
        page, too. Not part of the App class.
    :ivar description: A short description of the App. Should not exceed
        90 chars, otherwise it gets unreadable in the App
        Center.
    :ivar long_description: A more complete description of the App. HTML
        allowed and required! Shown before installation, so it
        should contain product highlights, use cases, etc.
    :ivar thumbnails: A list of screenshots and / or YouTube video URLs.
    :ivar categories: Categories this App shall be filed under.
    :ivar app_categories: Categories this App is filed under in
        the App catalog of univention.de.
    :ivar website: Website for more information about the product (e.g.
        landing page).
    :ivar support_url: Website for getting support (or information about
        how to buy a license).
    :ivar contact: Contact email address for the customer.
    :ivar vendor: Display name of the vendor. The actual creator of the
        Software. See also *maintainer*.
    :ivar website_vendor: Website of the vendor itself for more
        information.
    :ivar maintainer: Display name of the maintainer, who actually put
        the App into the App Center. Often, but not necessarily
        the *vendor*. If vendor and maintainer are the same,
        maintainer does not need to be specified again.
    :ivar website_maintainer: Website of the maintainer itself for more
        information.
    :ivar license: An abbreviation of a license category. See also
        *license_agreement*.
    :ivar license_agreement: A file containing the license text the end
        user has to agree to. The file is shipped along with
        the ini file. Not part of the ini file.
    :ivar readme: A file containing information about first steps for
        the end user. E.g., which UCS users have access to the
        App. Shown in the App Center if the App is installed.
        The file is shipped along with the ini file. Not part
        of the ini file.
    :ivar readme_install: A file containing important information for
        the end user which is shown *just before* the
        installation starts. The file is shipped along with
        the ini file. Not part of the ini file.
    :ivar readme_post_install: A file containing important information
        for the end user which is shown *just after* the
        installation is completed. The file is shipped along
        with the ini file. Not part of the ini file.
    :ivar readme_update: A file containing important information for the
        end user which is shown *just before* the update
        starts. Use case: Changelog. The file is shipped along
        with the ini file. Not part of the ini file.
    :ivar readme_post_update: A file containing important information
        for the end user which is shown *just after* the update
        is completed. The file is shipped along with the ini
        file. Not part of the ini file.
    :ivar readme_uninstall: A file containing important information for
        the end user which is shown *just before* the
        uninstallation starts. Use case: Warning about broken
        services. The file is shipped along with the ini
        file. Not part of the ini file.
    :ivar readme_post_uninstall: A file containing important information
        for the end user which is shown *just after* the
        uninstallation is completed. Use case: Instructions how
        to clean up if the App was unable to do it
        automatically. The file is shipped along with the ini
        file. Not part of the ini file.
    :ivar notify_vendor: Whether the App provider shall be informed
        about (un)installation of the App by Univention via
        email.
    :ivar notification_email: Email address that should be used to send
        notifications. If none is provided the address from
        *contact* will be used. Note: An empty email
        (NotificationEmail=) is not valid! Remove the line (or
        put in comments) in this case.
    :ivar web_interface: The path of the App's web interface.
    :ivar web_interface_name: A name for the App's web interface. If not
        given, *name* is used.
    :ivar web_interface_port_http: The port to the web interface (HTTP).
    :ivar web_interface_port_https: The port to the web interface (HTTPS).
    :ivar web_interface_proxy_scheme: Docker Apps only. Whether the web
        interface in the container only supports HTTP, HTTPS
        or both.
    :ivar auto_mod_proxy: Docker Apps only. Whether the web interface
        should be included in the host's apache configuration.
        If yes, the web interface ports of the container are
        used for a proxy configuration, so that the web
        interface is again available on 80/443. In this case
        the *web_interface* itself needs to have a distinct
        path even inside the container (like "/myapp" instead
        of "/" inside).
        If *web_interface_proxy_scheme* is set to http, both
        http and https are proxied to http in the container. If
        set to https, proxy points always to https. If set to
        both, http will go to http, https to https.
    :ivar ucs_overview_category: Whether and if where on the start site
        the *web_interface* should be registered automatically.
    :ivar background_color: Which background color to use on tiles in
        the App Center overview and the portal.
    :ivar web_interface_link_target: Which link_target to add to a portal
        entry. Currently supported:
        useportaldefault: let the portal decide
        embedded: in an iframe within the portal
        newwindow: new browser tab (default)
        samewindow: replaces portal (not recommended)
    :ivar database: Which (if any) database an App wants to use. The App
        Center will setup the database for the App. Useful for
        Docker Apps running against the Host's database.
        Supported: "mysql", "postgresql".
    :ivar database_name: Name of the database to be created. Defaults to
        *id*.
    :ivar database_user: Name of the database user to be created.
        Defaults to *id*. May not be "root" or "postgres".
    :ivar database_password_file: Path to the file in which the password
        will be stored. If not set, a default file will be
        created.
    :ivar docker_env_database_host: Environment variable name for the DB
        host inside the Docker Container.
    :ivar docker_env_database_port: Environment variable name for the DB
        port.
    :ivar docker_env_database_name: Environment variable name for the DB
        name.
    :ivar docker_env_database_user: Environment variable name for the DB
        user.
    :ivar docker_env_database_password: Environment variable name for the
        DB password (of "docker_env_database_user").
    :ivar docker_env_database_password_file: Environment variable name
        for a file that holds the password for the DB. If set,
        this file is created in the Docker Container;
        *docker_env_database_password* will not be used.
    :ivar plugin_of: App ID of the App the "base App" of this App. For
        Docker Apps, the plugin is installed into the container
        of *plugin_of*. For Non-Docker Apps this is just like
        *required_apps*, but important for later migrations.
    :ivar conflicted_apps: List of App IDs that may not be installed
        together with this App. Works in both ways, one only
        needs to specify it on one App.
    :ivar required_apps: List of App IDs that need to be installed along
        with this App.
    :ivar required_apps_in_domain: Like *required_apps*, but the Apps may
        be installed anywhere in the domain, not necessarily
        on this very server.
    :ivar conflicted_system_packages: List of debian package names that
        cannot be installed along with the App.
    :ivar required_ucs_version: The UCS version that is required for the
        App to work (because a specific feature was added or
        a bug was fixed after the initial release of this UCS
        version). Examples: 4.1-1, 4.1-1 errata200.
    :ivar supported_ucs_versions: List of UCS versions that may install
        this App. Only makes sense for Docker Apps. Example:
        4.1-4 errata370, 4.2-0
    :ivar required_app_version_upgrade: The App version that has to be
        installed before an upgrade to this version is allowed.
        Does nothing when installing (not upgrading) the App.
    :ivar end_of_life: If specified, this App does no longer show up in
        the App Center when not installed. For old
        installations, a warning is shown that the user needs
        to find an alternative for the App. Should be
        supported by an exhaustive *readme* file how to
        migrate the App data.
    :ivar without_repository: Whether this App can be installed without
        adding a dedicated repository on the App Center server.
    :ivar default_packages: List of debian package names that shall be
        installed (probably living in the App Center server's
        repository).
    :ivar default_packages_master: List of package names that shall be
        installed on Primary and Backup Directory Node
        systems while this App is installed. Deprecated. Not
        supported for Docker Apps.
    :ivar additional_packages_master: List of package names that shall be
        installed along with *default_packages* when installed
        on a Primary Directory Node. Not supported for Docker Apps.
    :ivar additional_packages_backup: List of package names that shall be
        installed along with *default_packages* when installed
        on a Backup Directory Node. Not supported for Docker Apps.
    :ivar additional_packages_slave: List of package names that shall be
        installed along with *default_packages* when installed
        on a Replica Directory Node. Not supported for Docker Apps.
    :ivar additional_packages_member: List of package names that shall be
        installed along with *default_packages* when installed
        on a Managed Node. Not supported for Docker Apps.
    :ivar rating: Positive rating on specific categories regarding the
        App. Controlled by Univention. Not part of the ini
        file.
    :ivar umc_module_name: If the App installs a UMC module, the ID can
        specified so that a link may be generated by the App
        Center.
    :ivar umc_module_flavor: If the App installs a UMC module with
        flavors, it can be specified so that a link may be
        generated by the App Center.
    :ivar user_activation_required: If domain users have to be somehow
        modified ("activated") to use the application, the App
        Center may generate a link to point the Users
        module of UMC.
    :ivar generic_user_activation: Automatically registers an LDAP schema
        and adds a flag to the UCS user management that should
        then be used to identify a user as "activated for the
        App". If set to True, the name of the attribute is
        *id*Activated. If set to anything else, the value is
        used for the name of the attribute. If a schema file is
        shipped along with the App, this file is used instead
        of the auto generated one.
    :ivar ports_exclusive: A list of ports the App requires to acquire
        exclusively. Implicitly adds *conflicted_apps*. Docker
        Apps will have these exact ports forwarded. The App
        Center will also change the firewall rules.
    :ivar ports_redirection: Docker Apps only. A list of ports the App
        wants to get forwarded from the host to the container.
        Example: 2222:22 will enable an SSH connection to the
        container when the user is doing "ssh docker-host -p
        2222".
    :ivar ports_redirection_udp: Just like *ports_redirection*, but opens
        UDP ports. Can be combined with the same
        *ports_redirection* if needed.
    :ivar server_role: List of UCS roles the App may be installed on.
    :ivar supported_architectures: Non-Docker Apps only. List of
        architectures the App supports. Docker Apps always
        require amd64.
    :ivar min_physical_ram: The minimal amount of memory in MB. This
        value is compared with the currently available memory
        (without Swap) when trying to install the application.
        When the test fails, the user may still override it
        and install it.
    :ivar min_free_disk_space: The minimal amount of free disk space in MB.
        This value is compared with the current free disk space
        at the installation destination when trying to install the
        application. When the test fails, the user may still override it
        and install it.
    :ivar shop_url: If given, a button is added to the App Center which
        users can click to buy a license.
    :ivar ad_member_issue_hide: When UCS is not managing the domain but
        instead is only part of a Windows controlled Active
        Directory domain, the environment in which the App runs
        is different and certain services that this App relies
        on may not not be running. Thus, the App should not be
        shown at all in the App Center.
    :ivar ad_member_issue_password: Like *ad_member_issue_hide* but only
        shows a warning: The App needs a password service
        running on the Windows domain controller, e.g. because
        it needs the samba hashes to authenticate users. This
        can be set up, but not automatically. A link to the
        documentation how to set up that service in such
        environments is shown.
    :ivar app_report_object_type: In some environments, App reports are
        automatically generated by a metering tool. This tool
        counts a specific amount of LDAP objects.
        *app_report_object_type* is the object type of these
        objects. Example: users/user.
    :ivar app_report_object_filter: Part of the App reporting. The
        filter for *app_report_object_type*. Example:
        (myAppActivated=1).
    :ivar app_report_object_attribute: Part of the App reporting. If
        specified, not 1 is counted per object, but the number
        of values in this *app_report_object_attribute*.
        Useful for *app_report_attribute_type = groups/group*
        and *app_report_object_attribute = uniqueMember*.
    :ivar app_report_attribute_type: Same as *app_report_object_type*
        but regarding the list of DNs in
        *app_report_object_attribute*.
    :ivar app_report_attribute_filter: Same as
        *app_report_object_filter* but regarding
        *app_report_object_type*.
    :ivar docker_image: Docker Image for the container. If specified the
        App implicitly becomes a Docker App.
    :ivar docker_inject_env_file: For Multi-Container Docker Apps, this
        attribute specifies whether the (optional) environment file
        shall be injected into the main, all or no services in the
        docker compose file.
    :ivar docker_main_service: For Multi-Container Docker Apps, this
        attribute specifies the main service in the compose
        file. This service's container will be used to run
        scripts like *docker_script_setup*, etc.
    :ivar docker_migration_works: Whether it is safe to install this
        version while a non Docker version is or was installed.
    :ivar docker_migration_link: A link to document where the necessary
        steps to migrate the App from a Non-Docker version to a
        Docker version are described. Only useful when
        *docker_migration_works = False*.
    :ivar docker_allowed_images: List of other Docker Images. Used for
        updates. If the new version has a new *docker_image*
        but the old App runs on an older image specified in
        this list, the image is not exchanged.
    :ivar docker_shell_command: Default command when running
        "univention-app APP shell".
    :ivar docker_volumes: List of volumes that shall be mounted from
        the host to the container. Example:
        /var/lib/host/MYAPP/:/var/lib/container/MYAPP/ mounts
        the first directory in the container under the name
        of the second directory.
    :ivar docker_server_role: Which computer object type shall be
        created in LDAP as the docker container.
    :ivar docker_script_init: The CMD for the Docker App. An
        empty value will use the container's entrypoint / CMD.
    :ivar docker_script_setup: Path to the setup script in the container
        run after the start of the container. If the App comes
        with a setup script living on the App Center server,
        this script is copied to this very path before being
        executed.
    :ivar docker_script_store_data: Like *docker_script_setup*, but for a
        script that is run to backup the data just before
        destroying the old container.
    :ivar docker_script_restore_data_before_setup: Like
        *docker_script_setup*, but for a script that is run to
        restore backuped data just before running the setup
        script.
    :ivar docker_script_restore_data_after_setup: Like
        *docker_script_setup*, but for a script that is run to
        restore backuped data just after running the setup
        script.
    :ivar docker_script_update_available: Like *docker_script_setup*, but
        for a script that is run to check whether an update is
        available (packag or distribution upgrade).
    :ivar docker_script_update_packages: Like *docker_script_setup*, but
        for a script that is run to install package updates
        (like security updates) in the container without
        destroying it.
    :ivar docker_script_update_release: Like *docker_script_setup*, but
        for a script that is run to install distribution
        updates (like new major releases of the OS) in
        the container without destroying it.
    :ivar docker_script_update_app_version: Like *docker_script_setup*,
        but for a script that is run to specifically install
        App package updates in the container without destroying
        it.
    :ivar docker_script_configure: Like *docker_script_setup*,
        but for a script that is run after settings inside the
        container were applied.
    :ivar docker_ucr_style_env: Disable the passing of ucr style ("foo/bar")
        environment variables into the container.
    :ivar host_certificate_access: Docker Apps only. The App gets access
        to the host certificate.
    :ivar listener_udm_modules: List of UDM modules that a listener
        integration shall watch.
    :ivar listener_udm_version: Version number for behavior of the listener integration.
        With version 2 UDM REST API type information are saved.
    """

    id = AppAttribute(regex='^[a-zA-Z0-9]+(([a-zA-Z0-9-_]+)?[a-zA-Z0-9])?$', required=True)
    """The required ID"""

    code = AppAttribute(regex='^[A-Za-z0-9]{2}$', required=True)
    component_id = AppComponentIDAttribute(required=True)
    ucs_version = AppUCSVersionAttribute(required=True)

    name = AppAttribute(required=True, localisable=True)
    version = AppAttribute(required=True)
    install_permissions = AppBooleanAttribute(default=False)
    install_permissions_message = AppAttribute(localisable=True)
    description = AppAttribute(localisable=True)
    long_description = AppAttribute(localisable=True)
    thumbnails = AppListAttribute(localisable=True)
    categories = AppListAttribute()
    app_categories = AppLocalisedAppCategoriesAttribute()

    website = AppAttribute(localisable=True)
    support_url = AppAttribute(localisable=True)
    contact = AppAttribute()
    vendor = AppAttribute()
    website_vendor = AppAttribute(localisable=True)
    maintainer = AppAttribute()
    website_maintainer = AppAttribute(localisable=True)
    license = AppAttribute(default='default')

    license_agreement = AppFileAttribute()
    readme = AppFileAttribute()
    readme_install = AppFileAttribute()
    readme_post_install = AppFileAttribute()
    readme_update = AppFileAttribute()
    readme_post_update = AppFileAttribute()
    readme_uninstall = AppFileAttribute()
    readme_post_uninstall = AppFileAttribute()

    notify_vendor = AppBooleanAttribute(default=True)
    notification_email = AppAttribute()

    web_interface = AppAttribute()
    web_interface_name = AppAttribute(localisable=True)
    web_interface_port_http = AppIntAttribute(default=80)
    web_interface_port_https = AppIntAttribute(default=443)
    web_interface_proxy_scheme = AppAttribute(default='both', choices=['http', 'https', 'both'])
    auto_mod_proxy = AppBooleanAttribute(default=True)
    ucs_overview_category = AppAttributeOrFalseOrNone(default='service', choices=['admin', 'service'])
    background_color = AppAttribute()
    web_interface_link_target = AppAttribute(default='newwindow')

    database = AppAttribute()
    database_name = AppAttribute()
    database_user = AppAttribute(regex='(?!^(root)$|^(postgres)$)')  # anything but db superuser!
    database_password_file = AppAttribute()
    docker_env_database_host = AppAttribute(default='DB_HOST')
    docker_env_database_port = AppAttribute(default='DB_PORT')
    docker_env_database_name = AppAttribute(default='DB_NAME')
    docker_env_database_user = AppAttribute(default='DB_USER')
    docker_env_database_password = AppAttribute(default='DB_PASSWORD')
    docker_env_database_password_file = AppAttribute()

    plugin_of = AppAttribute()
    conflicted_apps = AppListAttribute()
    required_apps = AppListAttribute()
    required_apps_in_domain = AppListAttribute()
    conflicted_system_packages = AppListAttribute()
    required_ucs_version = AppAttribute(regex=r'^(\d+)\.(\d+)-(\d+)(?: errata(\d+))?$')
    supported_ucs_versions = AppListAttribute(regex=r'^(\d+)\.(\d+)-(\d+)(?: errata(\d+))?$')
    required_app_version_upgrade = AppAttribute()
    end_of_life = AppBooleanAttribute()

    without_repository = AppBooleanAttribute()
    default_packages = AppListAttribute()
    default_packages_master = AppListAttribute()
    additional_packages_master = AppListAttribute()
    additional_packages_backup = AppListAttribute()
    additional_packages_slave = AppListAttribute()
    additional_packages_member = AppListAttribute()

    settings = AppFromFileAttribute(Setting)
    rating = AppRatingAttribute()

    umc_module_name = AppAttribute()
    umc_module_flavor = AppAttribute()

    user_activation_required = AppBooleanAttribute()
    generic_user_activation = AppAttributeOrTrueOrNone()
    generic_user_activation_attribute = AppAttributeOrTrueOrNone()
    generic_user_activation_option = AppAttributeOrTrueOrNone()
    umc_options_attributes = AppListAttribute()
    automatic_schema_creation = AppBooleanAttribute(default=True)
    docker_env_ldap_user = AppAttribute()

    ports_exclusive = AppListAttribute(regex=r'^\d+$')
    ports_redirection = AppListAttribute(regex=r'^\d+:\d+$')
    ports_redirection_udp = AppListAttribute(regex=r'^\d+:\d+$')

    server_role = AppListAttribute(default=['domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver'], choices=['domaincontroller_master', 'domaincontroller_backup', 'domaincontroller_slave', 'memberserver'])
    supported_architectures = AppListAttribute(default=['amd64', 'i386'], choices=['amd64', 'i386'])
    min_physical_ram = AppIntAttribute(default=0)
    min_free_disk_space = AppIntAttribute(default=None)

    shop_url = AppAttribute(localisable=True)

    ad_member_issue_hide = AppBooleanAttribute()
    ad_member_issue_password = AppBooleanAttribute()

    app_report_object_type = AppAttribute()
    app_report_object_filter = AppAttribute()
    app_report_object_attribute = AppAttribute()
    app_report_attribute_type = AppAttribute()
    app_report_attribute_filter = AppAttribute()

    docker_image = AppAttribute()
    docker_inject_env_file = AppAttribute()
    docker_main_service = AppAttribute()
    docker_migration_works = AppBooleanAttribute()
    docker_migration_link = AppAttribute()
    docker_allowed_images = AppListAttribute()
    docker_shell_command = AppAttribute(default='/bin/bash')
    docker_volumes = AppListAttribute()
    docker_server_role = AppAttribute(default='memberserver', choices=['memberserver', 'domaincontroller_slave'])
    docker_script_init = AppAttribute()
    docker_script_setup = AppDockerScriptAttribute()
    docker_script_store_data = AppDockerScriptAttribute()
    docker_script_restore_data_before_setup = AppDockerScriptAttribute()
    docker_script_restore_data_after_setup = AppDockerScriptAttribute()
    docker_script_update_available = AppDockerScriptAttribute()
    docker_script_update_packages = AppDockerScriptAttribute()
    docker_script_update_release = AppDockerScriptAttribute()
    docker_script_update_app_version = AppDockerScriptAttribute()
    docker_script_configure = AppAttribute()
    docker_ucr_style_env = AppBooleanAttribute(default=True)
    docker_tmpfs = AppListAttribute(default=["/run", "/run/lock"])

    host_certificate_access = AppBooleanAttribute()

    listener_udm_modules = AppListAttribute()
    listener_udm_version = AppIntAttribute(default=2)

    vote_for_app = AppBooleanAttribute()

    def __init__(self, _attrs, _cache, **kwargs):
        if kwargs:
            _attrs.update(kwargs)
        self._weak_ref_app_cache = None
        self._supports_ucs_version = None
        self._install_permissions_exist = None
        self.set_app_cache_obj(_cache)
        for attr in self._attrs:
            setattr(self, attr.name, _attrs.get(attr.name))
        self.ucs_version = self.get_ucs_version()  # compatibility
        if self.docker:
            if self.min_free_disk_space is None:
                self.min_free_disk_space = 4000
            self.supported_architectures = ['amd64']
            if self.plugin_of:
                for script in ['docker_script_restore_data_before_setup', 'docker_script_restore_data_after_setup']:
                    if getattr(self, script) == self.get_attr(script).default:
                        setattr(self, script, '')
        else:
            self.auto_mod_proxy = False
            self.ports_redirection = []

    def attrs_dict(self):
        ret = {}
        for attr in self._attrs:
            ret[attr.name] = getattr(self, attr.name)
        return ret

    def install_permissions_exist(self):
        if not self.docker:
            return True
        if not self.install_permissions:
            return True
        try:
            from univention.appcenter.docker import access
        except ImportError:
            return True
        if self._install_permissions_exist is None:
            # this should be optimized
            image = self.get_docker_image_name()
            self._install_permissions_exist = access(image)
        return self._install_permissions_exist

    def get_docker_image_name(self):
        if self.uses_docker_compose():
            try:
                from ruamel import yaml
            except ImportError:
                # appcenter-docker is not installed
                return None
            yml_file = self.get_cache_file('compose')
            content = yaml.load(ucr_run_filter(open(yml_file).read()), yaml.RoundTripLoader, preserve_quotes=True)
            image = content['services'][self.docker_main_service]['image']
            return image
        else:
            image = self.get_docker_images()[0]
            if self.is_installed():
                image = ucr_get(self.ucr_image_key) or image
            return image

    def get_docker_images(self):
        return [self.docker_image, *self.docker_allowed_images]

    def has_local_web_interface(self):
        if self.web_interface:
            return self.web_interface.startswith('/')

    @property
    def license_description(self):
        return self.get_app_cache_obj().get_appcenter_cache_obj().get_license_description(self.license)

    def __str__(self):
        from univention.appcenter.app_cache import default_server, default_ucs_version
        annotation = ''
        server = default_server()
        ucs_version = default_ucs_version()
        if ucs_version != self.get_ucs_version():
            annotation = self.get_ucs_version()
        if server != self.get_server():
            server = urlsplit(self.get_server()).netloc
            annotation = '%s@%s' % (annotation, server)
        if annotation:
            annotation += '/'
        return '%s%s=%s' % (annotation, self.id, self.version)

    def __repr__(self):
        return 'App(id="%s", version="%s", ucs_version="%s", server="%s")' % (self.id, self.version, self.get_ucs_version(), self.get_server())

    @classmethod
    def _get_meta_parser(cls, ini_file, ini_parser):
        component_id = os.path.splitext(os.path.basename(ini_file))[0]
        meta_file = os.path.join(os.path.dirname(ini_file), '%s.meta' % component_id)
        return read_ini_file(meta_file)

    @classmethod
    def from_ini(cls, ini_file, locale=True, cache=None):
        # app_logger.debug('Loading app from %s' % ini_file)
        if locale is True:
            locale = get_locale()
        component_id = os.path.splitext(os.path.basename(ini_file))[0]
        ini_parser = read_ini_file(ini_file)
        meta_parser = cls._get_meta_parser(ini_file, ini_parser)
        attr_values = {}
        for attr in cls._attrs:
            value = None
            try:
                value = attr.get_value(component_id, ini_parser, meta_parser, locale)
            except ValueError as e:
                app_logger.warning('Ignoring %s because of %s: %s' % (ini_file, attr.name, e))
                return
            attr_values[attr.name] = value
        return cls(attr_values, cache)

    @property
    def docker(self):
        return self.docker_image is not None or self.docker_main_service is not None

    def uses_docker_compose(self):
        return os.path.exists(self.get_cache_file('compose'))

    @property
    def ucr_status_key(self):
        return 'appcenter/apps/%s/status' % self.id

    @property
    def ucr_autoinstalled_key(self):
        return 'appcenter/apps/%s/autoinstalled' % self.id

    @property
    def ucr_version_key(self):
        return 'appcenter/apps/%s/version' % self.id

    @property
    def ucr_ucs_version_key(self):
        return 'appcenter/apps/%s/ucs' % self.id

    @property
    def ucr_upgrade_key(self):
        return 'appcenter/apps/%s/update/available' % self.id

    @property
    def ucr_container_key(self):
        return 'appcenter/apps/%s/container' % self.id

    @property
    def ucr_hostdn_key(self):
        return 'appcenter/apps/%s/hostdn' % self.id

    @property
    def ucr_image_key(self):
        return 'appcenter/apps/%s/image' % self.id

    @property
    def ucr_docker_params_key(self):
        return 'appcenter/apps/%s/docker/params' % self.id

    @property
    def ucr_ip_key(self):
        return 'appcenter/apps/%s/ip' % self.id

    @property
    def ucr_ports_key(self):
        return 'appcenter/apps/%s/ports/%%s' % self.id

    @property
    def ucr_component_key(self):
        return 'repository/online/component/%s' % self.component_id

    @property
    def ucr_pinned_key(self):
        return 'appcenter/apps/%s/pinned' % self.id

    @classmethod
    def get_attr(cls, attr_name):
        for attr in cls._attrs:
            if attr.name == attr_name:
                return attr

    def get_packages(self, additional=True):
        packages = []
        packages.extend(self.default_packages)
        if additional:
            role = ucr_get('server/role')
            if role == 'domaincontroller_master':
                packages.extend(self.additional_packages_master)
            elif role == 'domaincontroller_backup':
                packages.extend(self.additional_packages_backup)
            elif role == 'domaincontroller_slave':
                packages.extend(self.additional_packages_slave)
            elif role == 'memberserver':
                packages.extend(self.additional_packages_member)
        return packages

    def supports_ucs_version(self):
        if self._supports_ucs_version is None:
            self._supports_ucs_version = False
            if not self.supported_ucs_versions:
                self._supports_ucs_version = self.get_ucs_version() == ucr_get('version/version')
            else:
                for supported_version in self.supported_ucs_versions:
                    if supported_version.startswith('%s-' % ucr_get('version/version')):
                        self._supports_ucs_version = True
        return self._supports_ucs_version

    def is_installed(self):
        if self.docker and not container_mode():
            return ucr_get(self.ucr_status_key) in ['installed', 'stalled'] and ucr_get(self.ucr_version_key) == self.version and ucr_get(self.ucr_ucs_version_key, self.get_ucs_version()) == self.get_ucs_version()
        else:
            if not self.without_repository and not ucr_includes(self.ucr_component_key):
                return False
            return packages_are_installed(self.default_packages, strict=False)

    def is_ucs_component(self):
        english_cache = self.get_app_cache_obj().copy(locale='en')
        app = english_cache.find_by_component_id(self.component_id)
        if app is None:
            # somehow the localized cache and the english cache split brains!
            app_logger.warning('Could not find %r in %r' % (self, english_cache))
            english_cache.clear_cache()
            app = english_cache.find_by_component_id(self.component_id)
            if app is None:
                # giving up. not really harmful
                return False
        return 'UCS components' in app.categories

    def get_share_dir(self):
        return os.path.join(SHARE_DIR, self.id)

    def get_share_file(self, ext):
        return os.path.join(self.get_share_dir(), '%s.%s' % (self.id, ext))

    def get_data_dir(self):
        return os.path.join(DATA_DIR, self.id, 'data')

    def get_conf_dir(self):
        return os.path.join(DATA_DIR, self.id, 'conf')

    def get_conf_file(self, fname):
        fname = fname.removeprefix('/')
        fname = os.path.join(self.get_conf_dir(), fname)
        if not os.path.exists(fname):
            mkdir(os.path.dirname(fname))
        return fname

    def get_compose_dir(self):
        return os.path.join(DATA_DIR, self.id, 'compose')

    def get_compose_file(self, fname):
        return os.path.join(self.get_compose_dir(), fname)

    def get_ucs_version(self):
        app_cache = self.get_app_cache_obj()
        return app_cache.get_ucs_version()

    def get_locale(self):
        app_cache = self.get_app_cache_obj()
        return app_cache.get_locale()

    def get_server(self):
        app_cache = self.get_app_cache_obj()
        return app_cache.get_server()

    def get_cache_dir(self):
        app_cache = self.get_app_cache_obj()
        return app_cache.get_cache_dir()

    def get_app_cache_obj(self):
        if self._weak_ref_app_cache is None:
            from univention.appcenter.app_cache import AppCache
            app_cache = AppCache.build()
            self.set_app_cache_obj(app_cache)
        return self._weak_ref_app_cache()

    def set_app_cache_obj(self, app_cache_obj):
        if app_cache_obj:
            self._weak_ref_app_cache = ref(app_cache_obj)
        else:
            self._weak_ref_app_cache = None

    def get_cache_file(self, ext):
        return os.path.join(self.get_cache_dir(), '%s.%s' % (self.component_id, ext))

    def get_ini_file(self):
        return self.get_cache_file('ini')

    @property
    def logo_name(self):
        return 'apps-%s.svg' % self.component_id

    @property
    def logo_detail_page_name(self):
        if os.path.exists(self.get_cache_file('logodetailpage')):
            return 'apps-%s-detail.svg' % self.component_id

    @property
    def secret_on_host(self):
        return os.path.join(DATA_DIR, self.id, 'machine.secret')

    def get_thumbnail_urls(self):
        if not self.thumbnails:
            return []
        thumbnails = []
        for ithumb in self.thumbnails:
            if ithumb.startswith(('http://', 'https://')):
                # item is already a full URI
                thumbnails.append(ithumb)
                continue

            app_path = '%s/' % self.id
            ucs_version = self.get_ucs_version()
            if ucs_version == '4.0' or ucs_version.startswith('3.'):
                # since UCS 4.1, each app has a separate subdirectory
                app_path = ''
            thumbnails.append('%s/meta-inf/%s/%s%s' % (self.get_server(), ucs_version, app_path, ithumb))
        return thumbnails

    def get_localised(self, key, loc=None):
        from univention.appcenter.actions import get_action
        get = get_action('get')()
        keys = [(loc, key)]
        for _section, _name, value in get.get_values(self, keys, warn=False):
            return value

    def get_localised_list(self, key, loc=None):
        from univention.appcenter.actions import get_action
        get = get_action('get')()
        ret = []
        key = key.replace('_', '').lower()
        keys = [(None, key), ('de', key)]
        for section, _name, value in get.get_values(self, keys, warn=False):
            if value is None:
                continue
            if section is None:
                section = 'en'
            value = '[%s] %s' % (section, value)
            ret.append(value)
        return ret

    @hard_requirement('install', 'upgrade')
    def must_have_install_permissions(self):
        """You need to buy the App to install this version."""
        if not self.install_permissions_exist():
            return {'shop_url': self.shop_url, 'version': self.version}
        return True

    @hard_requirement('upgrade')
    def must_have_fitting_app_version(self):
        """
        To upgrade, at least version %(required_version)s needs to
        be installed.
        """
        from univention.appcenter.app_cache import Apps
        if self.required_app_version_upgrade:
            required_version = LooseVersion(self.required_app_version_upgrade)
            installed_app = Apps().find(self.id)
            installed_version = LooseVersion(installed_app.version)
            if required_version > installed_version:
                return {'required_version': self.required_app_version_upgrade}
        return True

    @hard_requirement('install', 'upgrade')
    def must_have_fitting_ucs_version(self):
        """The application requires UCS version %(required_version)s."""
        required_ucs_version = None
        for supported_version in self.supported_ucs_versions:
            if supported_version.startswith('%s-' % ucr_get('version/version')):
                required_ucs_version = supported_version
                break
        else:
            if self.get_ucs_version() == ucr_get('version/version'):
                if self.required_ucs_version:
                    required_ucs_version = self.required_ucs_version
                else:
                    return True
        if required_ucs_version is None:
            return {'required_version': self.get_ucs_version()}
        major, minor = ucr_get('version/version').split('.', 1)
        patchlevel = ucr_get('version/patchlevel')
        errata = ucr_get('version/erratalevel')
        version_bits = re.match(r'^(\d+)\.(\d+)-(\d+)(?: errata(\d+))?$', required_ucs_version).groups()
        comparisons = zip(version_bits, [major, minor, patchlevel, errata])
        for required, present in comparisons:
            if int(required or 0) > int(present):
                return {'required_version': required_ucs_version}
            if int(required or 0) < int(present):
                return True
        return True

    @hard_requirement('install', 'upgrade')
    def must_have_fitting_kernel_version(self):
        if self.docker:
            kernel = LooseVersion(os.uname()[2])
            if kernel < LooseVersion('4.9'):
                return False
        return True

    @hard_requirement('install', 'upgrade')
    def must_not_be_vote_for_app(self):
        """
        The application is not yet installable. Vote for this app
        now and bring your favorite faster to the Univention App
        Center
        """
        return not self.vote_for_app

    @hard_requirement('install', 'upgrade')
    def must_not_be_docker_if_docker_is_disabled(self):
        """
        The application uses a container technology while the App Center
        is configured to not not support it
        """
        return not self.docker or ucr_is_true('appcenter/docker', True)

    @hard_requirement('install', 'upgrade')
    def must_not_be_docker_in_docker(self):
        """
        The application uses a container technology while the system
        itself runs in a container. Using the application is not
        supported on this host
        """
        return not self.docker or not container_mode()

    @hard_requirement('install', 'upgrade')
    def must_have_valid_license(self):
        """
        For the installation of this application, a UCS license key
        with a key identification (Key ID) is required
        """
        if self.notify_vendor:
            license = ucr_get('uuid/license')
            if license is None:
                ucr_load()
                license = ucr_get('uuid/license')
            return license is not None
        return True

    @hard_requirement('install')
    def must_not_be_installed(self):
        """This application is already installed"""
        return not self.is_installed()

    @hard_requirement('install')
    def must_not_be_end_of_life(self):
        """
        This application was discontinued and may not be installed
        anymore
        """
        return not self.end_of_life

    @hard_requirement('install', 'upgrade')
    def must_have_supported_architecture(self):
        """
        This application only supports %(supported)s as
        architecture. %(msg)s
        """
        supported_architectures = self.supported_architectures
        platform_bits = platform.architecture()[0]
        aliases = {'i386': '32bit', 'amd64': '64bit'}
        if supported_architectures:
            for architecture in supported_architectures:
                if aliases[architecture] == platform_bits:
                    break
            else:
                # For now only two architectures are supported:
                #   32bit and 64bit - and this will probably not change
                #   too soon.
                # So instead of returning lists and whatnot
                #   just return a nice message
                # Needs to be adapted when supporting different archs
                supported = supported_architectures[0]
                if supported == 'i386':
                    needs = 32
                    has = 64
                else:
                    needs = 64
                    has = 32
                msg = _('The application needs a %(needs)s-bit operating system. This server is running a %(has)s-bit operating system.') % {'needs': needs, 'has': has}
                return {'supported': supported, 'msg': msg}
        return True

    @hard_requirement('install', 'upgrade')
    def must_be_joined_if_master_packages(self):
        """This application requires an extension of the LDAP schema"""
        is_joined = os.path.exists('/var/univention-join/joined')
        return bool(is_joined or not self.default_packages_master)

    @hard_requirement('install', 'upgrade', 'remove')
    def must_not_have_concurrent_operation(self, package_manager):
        """Another package operation is in progress"""
        if self.docker:
            return True
        else:
            return package_manager.progress_state._finished  # TODO: package_manager.is_finished()

    @hard_requirement('install', 'upgrade')
    def must_have_correct_server_role(self):
        """
        The application cannot be installed on the current server
        role (%(current_role)s). In order to install the application,
        one of the following roles is necessary: %(allowed_roles)r
        """
        server_role = ucr_get('server/role')
        if not self._allowed_on_local_server():
            return {
                'current_role': server_role,
                'allowed_roles': ', '.join(self.server_role),
            }
        return True

    @hard_requirement('install', 'upgrade')
    def must_have_no_conflicts_packages(self, package_manager):
        """The application conflicts with the following packages: %r"""
        conflict_packages = []
        for pkgname in self.conflicted_system_packages:
            if package_manager.is_installed(pkgname):
                conflict_packages.append(pkgname)
        if conflict_packages:
            return conflict_packages
        return True

    @hard_requirement('install', 'upgrade')
    def must_have_no_conflicts_apps(self):
        """
        The application conflicts with the following applications:
        %r
        """
        from univention.appcenter.app_cache import Apps
        conflictedapps = set()
        apps_cache = Apps()
        # check ConflictedApps
        for app in apps_cache.get_all_apps():
            if not app._allowed_on_local_server():
                # cannot be installed, continue
                continue
            if (app.id in self.conflicted_apps or self.id in app.conflicted_apps) and app.is_installed():
                conflictedapps.add(app.id)
        # check port conflicts
        ports = []
        for i in self.ports_exclusive:
            ports.append(i)  # noqa: PERF402
        for i in self.ports_redirection:
            ports.append(i.split(':', 1)[0])
        for app_id, _container_port, host_port in app_ports():
            if app_id != self.id and str(host_port) in ports:
                conflictedapps.add(app_id)
        if conflictedapps:
            conflictedapps = [apps_cache.find(app_id) for app_id in conflictedapps]
            return [{'id': app.id, 'name': app.name} for app in conflictedapps if app]
        return True

    @hard_requirement('install', 'upgrade')
    def must_have_no_unmet_dependencies(self):
        """The application requires the following applications: %r"""
        from univention.appcenter.app_cache import Apps
        unmet_apps = []

        apps_cache = Apps()
        # RequiredApps
        for app in apps_cache.get_all_apps():
            if app.id in self.required_apps and not app.is_installed():
                unmet_apps.append({'id': app.id, 'name': app.name, 'in_domain': False})

        # Plugin
        if self.plugin_of:
            app = Apps.find(self.plugin_of)
            if not app.is_installed():
                unmet_apps.append({'id': app.id, 'name': app.name, 'in_domain': False})

        # RequiredAppsInDomain
        from univention.appcenter.actions import get_action
        domain = get_action('domain')
        apps = [apps_cache.find(app_id) for app_id in self.required_apps_in_domain]
        apps_info = domain.to_dict(apps)
        for app in apps_info:
            if not app:
                continue
            if not app['is_installed_anywhere']:
                local_allowed = app['id'] not in self.conflicted_apps
                unmet_apps.append({'id': app['id'], 'name': app['name'], 'in_domain': True, 'local_allowed': local_allowed})
        if unmet_apps:
            return unmet_apps
        return True

    @hard_requirement('remove')
    def must_not_be_depended_on(self):
        """
        The application is required for the following applications
        to work: %r
        """
        from univention.appcenter.app_cache import Apps
        depending_apps = []

        apps_cache = Apps()
        # RequiredApps
        # RequiredApps
        for app in apps_cache.get_all_apps():
            if self.id in app.required_apps and app.is_installed():
                depending_apps.append({'id': app.id, 'name': app.name})

        # Plugin
        if not self.docker:
            for app in apps_cache.get_all_apps():
                if self.id == app.plugin_of:
                    depending_apps.append({'id': app.id, 'name': app.name})

        # RequiredAppsInDomain
        apps = [app for app in apps_cache.get_all_apps() if self.id in app.required_apps_in_domain]
        if apps:
            from univention.appcenter.actions import get_action
            domain = get_action('domain')
            self_info = domain.to_dict([self])[0]
            hostname = ucr_get('hostname')
            if not any(inst['version'] for host, inst in self_info['installations'].items() if host != hostname):
                # this is the only installation
                apps_info = domain.to_dict(apps)
                for app in apps_info:
                    if app['is_installed_anywhere']:
                        depending_apps.append({'id': app['id'], 'name': app['name']})

        if depending_apps:
            return depending_apps
        return True

    @hard_requirement('remove')
    def must_not_remove_plugin(self):
        """
        It is currently impossible to remove a plugin once it is
        installed. Remove %r instead.
        """
        from univention.appcenter.app_cache import Apps

        if self.docker and self.plugin_of:
            app = Apps().find(self.plugin_of)
            return {'id': app.id, 'name': app.name}
        return True

    @soft_requirement('remove')
    def shall_not_have_plugins_in_docker(self):
        """
        Uninstalling the App will also remove the following plugins:
        %r
        """
        from univention.appcenter.app_cache import Apps
        depending_apps = []
        if self.docker:
            for app in Apps().get_all_apps():
                if self.id == app.plugin_of:
                    depending_apps.append({'id': app.id, 'name': app.name})
        if depending_apps:
            return depending_apps
        return True

    @soft_requirement('install')
    def shall_have_enough_free_disk_space(self):
        """
        The application requires %(minimum)d MB of free disk space but only
        %(current)d MB are available.
        """
        required_free_disk_space = self.min_free_disk_space or 0
        if required_free_disk_space <= 0:
            return True
        current_free_disk_space = get_free_disk_space()
        if current_free_disk_space and current_free_disk_space < required_free_disk_space:
            return {'minimum': required_free_disk_space, 'current': current_free_disk_space}
        return True

    @soft_requirement('install', 'upgrade')
    def shall_have_enough_ram(self, function):
        """
        The application requires %(minimum)d MB of free RAM but only
        %(current)d MB are available.
        """
        from univention.appcenter.app_cache import Apps
        current_ram = get_current_ram_available()
        required_ram = self.min_physical_ram
        if function == 'upgrade':
            # is already installed, just a minor version upgrade
            #   RAM "used" by this installed app should count
            #   as free. best approach: subtract it
            installed_app = Apps().find(self.id)
            old_required_ram = installed_app.min_physical_ram
            required_ram = required_ram - old_required_ram
        if current_ram < required_ram:
            return {'minimum': required_ram, 'current': current_ram}
        return True

    @soft_requirement('install', 'upgrade')
    def shall_only_be_installed_in_ad_env_with_password_service(self):
        """
        The application requires the password service to be set up
        on the Active Directory domain controller server.
        """
        return not self._has_active_ad_member_issue('password')

    @hard_requirement('install', 'upgrade')
    def shall_not_be_docker_if_discouraged(self):
        """
        The application has not been approved to migrate all
        existing data. Maybe there is a migration guide:
        %(migration_link)s
        """
        problem = self._docker_prudence_is_true() and not self.docker_migration_works
        if problem:
            return {'migration_link': self.docker_migration_link}
        return True

    def _docker_prudence_is_true(self):
        if not self.docker:
            return False
        ret = ucr_is_true('appcenter/prudence/docker/%s' % self.id)
        if not ret and self.plugin_of:
            ret = ucr_is_true('appcenter/prudence/docker/%s' % self.plugin_of)
        return ret

    def check(self, function):
        from univention.appcenter.app_cache import Apps
        package_manager = get_package_manager()
        hard_problems = {}
        soft_problems = {}
        if function == 'upgrade':
            app = Apps().find(self.id)
            if app > self:
                # upgrade is not possible,
                #   special handling
                hard_problems['must_have_candidate'] = False
        for requirement in self._requirements:
            if function not in requirement.actions:
                continue
            result = requirement.test(self, function, package_manager)
            if result is not True:
                if requirement.hard:
                    hard_problems[requirement.name] = result
                else:
                    soft_problems[requirement.name] = result
        return hard_problems, soft_problems

    def _allowed_on_local_server(self):
        server_role = ucr_get('server/role')
        allowed_roles = self.server_role
        return not allowed_roles or server_role in allowed_roles

    def _has_active_ad_member_issue(self, issue):
        return ucr_is_true('ad/member') and getattr(self, 'ad_member_issue_%s' % issue, False)

    def __lt__(self, other):
        """
        >>> from argparse import Namespace
        >>> cache1 = Namespace(get_ucs_version=lambda: '1')
        >>> cache2 = Namespace(get_ucs_version=lambda: '2')
        >>> App({}, cache1, id=1, component_id=1) < App({}, cache1, id=1, component_id=1)
        False
        >>> App({}, cache1, id=1, component_id=1) < App({}, cache1, id=2, component_id=1)
        True
        >>> App({}, cache1, id=1, component_id=1) < App({}, cache2, id=1, component_id=1)
        True
        >>> App({}, cache1, id=1, component_id=1) < App({}, cache1, id=1, component_id=2)
        True
        """
        return (self.id, LooseVersion(self.get_ucs_version()), LooseVersion(self.version), self.component_id) < (other.id, LooseVersion(other.get_ucs_version()), LooseVersion(other.version), other.component_id) if isinstance(other, App) else NotImplemented

    def __le__(self, other):
        return (self.id, LooseVersion(self.get_ucs_version()), LooseVersion(self.version), self.component_id) <= (other.id, LooseVersion(other.get_ucs_version()), LooseVersion(other.version), other.component_id) if isinstance(other, App) else NotImplemented

    def __eq__(self, other):
        return (self.id, LooseVersion(self.get_ucs_version()), LooseVersion(self.version), self.component_id) == (other.id, LooseVersion(other.get_ucs_version()), LooseVersion(other.version), other.component_id) if isinstance(other, App) else NotImplemented

    def __ne__(self, other):
        return (self.id, LooseVersion(self.get_ucs_version()), LooseVersion(self.version), self.component_id) != (other.id, LooseVersion(other.get_ucs_version()), LooseVersion(other.version), other.component_id) if isinstance(other, App) else NotImplemented

    def __ge__(self, other):
        return (self.id, LooseVersion(self.get_ucs_version()), LooseVersion(self.version), self.component_id) >= (other.id, LooseVersion(other.get_ucs_version()), LooseVersion(other.version), other.component_id) if isinstance(other, App) else NotImplemented

    def __gt__(self, other):
        return (self.id, LooseVersion(self.get_ucs_version()), LooseVersion(self.version), self.component_id) > (other.id, LooseVersion(other.get_ucs_version()), LooseVersion(other.version), other.component_id) if isinstance(other, App) else NotImplemented
