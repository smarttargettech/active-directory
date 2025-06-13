# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from __future__ import annotations

import subprocess

import ldap

import univention.config_registry
import univention.testing.strings as tstrings
from univention.testing.udm import verify_udm_object


configRegistry = univention.config_registry.ConfigRegistry()
configRegistry.load()

UTF8_CHARSET = tstrings.STR_UMLAUT + "КирилицаКириллицаĆirilicaЋирилица" + "普通話普通话"
# the CON sync can't # handle them (see bug #44373)
SPECIAL_CHARSET = "".join(set(tstrings.STR_SPECIAL_CHARACTER) - set('\\#"?'))
# We exclude '$' as it has special meaning . A '.' (dot) may not be the last
# character in a samAccountName, so we forbid it as well.
FORBIDDEN_SAMACCOUNTNAME = "\\/[]:;|=,+*?<>@ $."
SPECIAL_CHARSET_USERNAME = "".join(set(SPECIAL_CHARSET) - set(FORBIDDEN_SAMACCOUNTNAME))


def random_string(length: int = 10, alpha: bool = False, numeric: bool = False, charset: str = "", encoding: str = 'utf-8') -> str:
    return tstrings.random_string(length, alpha, numeric, charset, encoding)


def random_bytestring(length: int = 10, alpha: bool = False, numeric: bool = False, charset: str = "") -> bytes:
    string = random_string(length, alpha, numeric, charset)
    if not isinstance(string, bytes):
        return string.encode('utf-8')
    return string


def normalize_dn(dn: str) -> str:
    r"""
    Normalize a given dn. This removes some escaping of special chars in the
    DNs. Note: The CON-LDAP returns DNs with escaping chars, OpenLDAP does not.

    >>> normalize_dn(r"cn=peter\#,cn=groups")
    'cn=peter#,cn=groups'
    """
    return ldap.dn.dn2str(ldap.dn.str2dn(dn))


def to_unicode(string: bytes | str) -> str:
    if isinstance(string, bytes):
        return string.decode('utf-8')
    return string


def restart_univention_cli_server() -> None:
    print("Restarting Univention-CLI-Server")
    subprocess.call(["pkill", "-f", "univention-cli-server"])


class TestUser:
    def __init__(self, user, rename={}, container=None, selection=None):
        selection = selection or ("username", "firstname", "lastname")
        self.basic = {k: v for (k, v) in user.items() if k in selection}
        self.user = user
        self.rename = dict(self.basic)
        self.rename.update(rename)
        self.container = container

    @classmethod
    def to_unicode(cls, dictionary):
        return {k: to_unicode(v) for k, v in dictionary.items()}

    def __repr__(self):
        args = (self.user, self.rename, self.container)
        return "{}({})".format(self.__class__.__name__, ", ".join(repr(a) for a in args))


class NormalUser(TestUser):
    def __init__(self, selection=None):
        super().__init__(
            user={
                "username": tstrings.random_username().encode('UTF-8'),
                "firstname": tstrings.random_name().encode('UTF-8'),
                "lastname": tstrings.random_name().encode('UTF-8'),
                "description": random_bytestring(alpha=True, numeric=True),
                "street": random_bytestring(alpha=True, numeric=True),
                "city": random_bytestring(alpha=True, numeric=True),
                "postcode": random_bytestring(numeric=True),
                "profilepath": random_bytestring(alpha=True, numeric=True),
                "scriptpath": random_bytestring(alpha=True, numeric=True),
                "phone": random_bytestring(numeric=True),
                "homeTelephoneNumber": random_bytestring(numeric=True),
                "mobileTelephoneNumber": random_bytestring(numeric=True),
                "pagerTelephoneNumber": random_bytestring(numeric=True),
                "sambaUserWorkstations": random_bytestring(numeric=True),
            },
            rename={"username": tstrings.random_username().encode('UTF-8')},
            container=tstrings.random_name(),
            selection=selection,
        )


class Utf8User(TestUser):
    def __init__(self, selection=None):
        super().__init__(
            user={
                "username": random_bytestring(charset=UTF8_CHARSET),
                "firstname": random_bytestring(charset=UTF8_CHARSET),
                "lastname": random_bytestring(charset=UTF8_CHARSET),
                "description": random_bytestring(charset=UTF8_CHARSET),
                "street": random_bytestring(charset=UTF8_CHARSET),
                "city": random_bytestring(charset=UTF8_CHARSET),
                "postcode": random_bytestring(numeric=True),
                "profilepath": random_bytestring(charset=UTF8_CHARSET),
                "scriptpath": random_bytestring(charset=UTF8_CHARSET),
                "phone": random_bytestring(numeric=True),
                "homeTelephoneNumber": random_bytestring(numeric=True),
                "mobileTelephoneNumber": random_bytestring(numeric=True),
                "pagerTelephoneNumber": random_bytestring(numeric=True),
                "sambaUserWorkstations": random_bytestring(numeric=True),
            },
            rename={"username": random_bytestring(charset=UTF8_CHARSET)},
            container=random_string(charset=UTF8_CHARSET),
            selection=selection,
        )


class SpecialUser(TestUser):
    def __init__(self, selection=None):
        super().__init__(
            user={
                "username": random_bytestring(charset=SPECIAL_CHARSET_USERNAME),
                "firstname": tstrings.random_name_special_characters().encode('UTF-8'),
                "lastname": tstrings.random_name_special_characters().encode('UTF-8'),
                "description": random_bytestring(charset=SPECIAL_CHARSET),
                "street": random_bytestring(charset=SPECIAL_CHARSET),
                "city": random_bytestring(charset=SPECIAL_CHARSET),
                "postcode": random_bytestring(numeric=True),
                "profilepath": random_bytestring(charset=SPECIAL_CHARSET),
                "scriptpath": random_bytestring(charset=SPECIAL_CHARSET),
                "phone": random_bytestring(numeric=True),
                "homeTelephoneNumber": random_bytestring(numeric=True),
                "mobileTelephoneNumber": random_bytestring(numeric=True),
                "pagerTelephoneNumber": random_bytestring(numeric=True),
                "sambaUserWorkstations": random_bytestring(numeric=True),
            },
            rename={"username": random_bytestring(charset=SPECIAL_CHARSET_USERNAME)},
            container=random_string(charset=SPECIAL_CHARSET),
            selection=selection,
        )


class TestGroup:
    def __init__(self, group, rename={}, container=None):
        self.group = group
        self.rename = dict(self.group)
        self.rename.update(rename)
        self.container = container

    @classmethod
    def to_unicode(cls, dictionary):
        return {k: to_unicode(v) for k, v in dictionary.items()}

    def __repr__(self):
        args = (self.group, self.rename, self.container)
        return "{}({})".format(self.__class__.__name__, ", ".join(repr(a) for a in args))


class NormalGroup(TestGroup):
    def __init__(self):
        super().__init__(
            group={
                "name": tstrings.random_groupname().encode('UTF-8'),
                "description": random_bytestring(alpha=True, numeric=True),
            },
            rename={"name": tstrings.random_groupname().encode('UTF-8')},
            container=tstrings.random_name(),
        )


class Utf8Group(TestGroup):
    def __init__(self):
        super().__init__(
            group={
                "name": random_bytestring(charset=UTF8_CHARSET),
                "description": random_bytestring(charset=UTF8_CHARSET),
            },
            rename={"name": random_bytestring(charset=UTF8_CHARSET)},
            container=random_string(charset=UTF8_CHARSET),
        )


class SpecialGroup(TestGroup):
    def __init__(self):
        super().__init__(
            group={
                "name": random_bytestring(charset=SPECIAL_CHARSET_USERNAME),
                "description": random_bytestring(charset=SPECIAL_CHARSET),
            },
            rename={"name": random_bytestring(charset=SPECIAL_CHARSET_USERNAME)},
            container=random_string(charset=SPECIAL_CHARSET),
        )


class TestObject:
    def __init__(self, obj, rename={}, container=None):
        self.obj = obj
        self.rename = dict(self.obj)
        self.rename.update(rename)
        self.container = container

    @classmethod
    def to_unicode(cls, dictionary):
        return {k: to_unicode(v) for k, v in dictionary.items()}

    def __repr__(self):
        args = (self.obj, self.rename, self.container)
        return "{}({})".format(self.__class__.__name__, ", ".join(repr(a) for a in args))


class NormalWindows(TestObject):
    def __init__(self):
        super().__init__(
            obj={
                "name": tstrings.random_groupname().encode('UTF-8'),
                "description": random_bytestring(alpha=True, numeric=True),
                # "inventoryNumber": random_bytestring(alpha=False, numeric=True),
                "operatingSystem": b"Windows",
                "operatingSystemVersion": b"11",
            },
            rename={"name": tstrings.random_groupname().encode('UTF-8')},
            container=tstrings.random_name(),
        )


class NormalContainer(TestObject):
    def __init__(self):
        super().__init__(
            obj={
                "name": tstrings.random_groupname().encode('UTF-8'),
                "description": random_bytestring(alpha=True, numeric=True),
            },
            rename={"name": tstrings.random_groupname().encode('UTF-8')},
            container=tstrings.random_name(),
        )


class NormalOU(TestObject):
    def __init__(self):
        super().__init__(
            obj={
                "name": tstrings.random_groupname().encode('UTF-8'),
                "description": random_bytestring(alpha=True, numeric=True),
            },
            rename={"name": tstrings.random_groupname().encode('UTF-8')},
            container=tstrings.random_name(),
        )


def map_udm_user_to_con(user):
    """
    Map a UDM user given as a dictionary of `property`:`values` mappings to a
    dictionary of `attributes`:`values` mappings as required by the CON-LDAP.
    Note: This expects the properties from the UDM users/user module and not
    OpenLDAP-attributes!.
    """
    mapping = {
        "username": "sAMAccountName",
        "firstname": "givenName",
        "lastname": "sn",
        "description": "description",
        "street": "streetAddress",
        "city": "l",
        "postcode": "postalCode",
        "profilepath": "profilePath",
        "scriptpath": "scriptPath",
        "phone": "telephoneNumber",
        "homeTelephoneNumber": "homePhone",
        "mobileTelephoneNumber": "mobile",
        "pagerTelephoneNumber": "pager",
        "sambaUserWorkstations": "userWorkstations"}
    # return {mapping[key]: value for (key, value) in user.items() if key in mapping}
    return {mapping[key]: ([value] if not isinstance(value, list | tuple) else value) for (key, value) in user.items() if key in mapping}


def map_udm_group_to_con(group):
    """
    Map a UDM group given as a dictionary of `property`:`values` mappings to a
    dictionary of `attributes`:`values` mappings as required by the CON-LDAP.
    Note: This expects the properties from the UDM groups/group module and not
    OpenLDAP-attributes!.
    """
    mapping = {"name": "sAMAccountName", "description": "description"}
    # return {mapping[key]: value for (key, value) in group.items() if key in mapping}
    return {mapping[key]: ([value] if not isinstance(value, list | tuple) else value) for (key, value) in group.items() if key in mapping}


def map_udm_windows_to_con(windows):
    """
    Map a UDM computers/windows given as a dictionary of `property`:`values` mappings to a
    dictionary of `attributes`:`values` mappings as required by the CON-LDAP.
    Note: This expects the properties from the UDM computers/windows module and not
    OpenLDAP-attributes!.
    """
    mapping = {
        "name": "sAMAccountName",
        "description": "description",
        "operatingSystem": "operatingSystem",
        "operatingSystemVersion": "operatingSystemVersion",
    }
    return {mapping[key]: ([value] if not isinstance(value, list | tuple) else value) for (key, value) in windows.items() if key in mapping}


def map_udm_container_to_con(container):
    """
    Map a UDM container/* given as a dictionary of `property`:`values` mappings to a
    dictionary of `attributes`:`values` mappings as required by the CON-LDAP.
    Note: This expects the properties from the UDM container/* module and not
    OpenLDAP-attributes!.
    """
    mapping = {
        "name": "cn",
        "description": "description",
    }
    return {mapping[key]: ([value] if not isinstance(value, list | tuple) else value) for (key, value) in container.items() if key in mapping}


def map_udm_ou_to_con(container):
    """
    Map a UDM container/* given as a dictionary of `property`:`values` mappings to a
    dictionary of `attributes`:`values` mappings as required by the CON-LDAP.
    Note: This expects the properties from the UDM container/* module and not
    OpenLDAP-attributes!.
    """
    mapping = {
        "name": "ou",
        "description": "description",
    }
    return {mapping[key]: ([value] if not isinstance(value, list | tuple) else value) for (key, value) in container.items() if key in mapping}


def create_udm_user(udm, con, user, wait_for_sync, verify=True):
    print(f"\nCreating UDM user {user.basic}\n")
    (udm_user_dn, username) = udm.create_user(**user.to_unicode(user.basic))
    con_user_dn = ldap.dn.dn2str([[("CN", to_unicode(username), ldap.AVA_STRING)], [("CN", "users", ldap.AVA_STRING)], *ldap.dn.str2dn(con.adldapbase)])
    wait_for_sync()
    if verify:
        con.verify_object(con_user_dn, map_udm_user_to_con(user.basic))
    return (udm_user_dn, con_user_dn)


def delete_udm_user(udm, con, udm_user_dn, con_user_dn, wait_for_sync):
    print("\nDeleting UDM user\n")
    udm.remove_object('users/user', dn=udm_user_dn)
    wait_for_sync()
    con.verify_object(con_user_dn, None)


def create_con_user(con, udm_user, wait_for_sync):
    basic_con_user = map_udm_user_to_con(udm_user.basic)

    print(f"\nCreating CON user {basic_con_user}\n")
    username = udm_user.basic.get("username")
    con_user_dn = con.createuser(username, **basic_con_user)
    udm_user_dn = ldap.dn.dn2str([[("uid", to_unicode(username), ldap.AVA_STRING)], [("CN", "users", ldap.AVA_STRING)], *ldap.dn.str2dn(configRegistry.get("ldap/base"))])
    wait_for_sync()
    verify_udm_object("users/user", udm_user_dn, udm_user.basic)
    return (basic_con_user, con_user_dn, udm_user_dn)


def delete_con_user(con, con_user_dn, udm_user_dn, wait_for_sync):
    print("\nDeleting CON user\n")
    con.delete(con_user_dn)
    wait_for_sync()
    verify_udm_object("users/user", udm_user_dn, None)


def create_udm_group(udm, con, group, wait_for_sync):
    print(f"\nCreating UDM group {group}\n")
    (udm_group_dn, groupname) = udm.create_group(**group.to_unicode(group.group))
    con_group_dn = ldap.dn.dn2str([[("CN", to_unicode(groupname), ldap.AVA_STRING)], [("CN", "groups", ldap.AVA_STRING)], *ldap.dn.str2dn(con.adldapbase)])
    wait_for_sync()
    con.verify_object(con_group_dn, map_udm_group_to_con(group.group))
    return (udm_group_dn, con_group_dn)


def delete_udm_group(udm, con, udm_group_dn, con_group_dn, wait_for_sync):
    print("\nDeleting UDM group\n")
    udm.remove_object('groups/group', dn=udm_group_dn)
    wait_for_sync()
    con.verify_object(con_group_dn, None)


def create_con_group(con, udm_group, wait_for_sync):
    con_group = map_udm_group_to_con(udm_group.group)

    print(f"\nCreating CON group {con_group}\n")
    groupname = to_unicode(udm_group.group.get("name"))
    con_group_dn = con.group_create(groupname, **con_group)
    udm_group_dn = ldap.dn.dn2str([[("cn", groupname, ldap.AVA_STRING)], [("CN", "groups", ldap.AVA_STRING)], *ldap.dn.str2dn(configRegistry.get("ldap/base"))])
    wait_for_sync()
    verify_udm_object("groups/group", udm_group_dn, udm_group.group)
    return (con_group, con_group_dn, udm_group_dn)


def delete_con_group(con, con_group_dn, udm_group_dn, wait_for_sync):
    print("\nDeleting CON group\n")
    con.delete(con_group_dn)
    wait_for_sync()
    verify_udm_object("groups/group", udm_group_dn, None)
