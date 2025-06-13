# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import os
import subprocess
import sys

import ldap
import ldap.dn
from ldap import modlist
from ldap.controls import LDAPControl

import univention.testing.connector_common as tcommon
from univention.config_registry import ConfigRegistry


ucr = ConfigRegistry()
ucr.load()


def get_rdn(dn):
    r"""
    >>> get_rdn(r'a=b\,c+d=e,f=g+h=i\,j')
    'a=b\\,c+d=e'
    >>> get_rdn(r'a=b')
    'a=b'
    """
    rdn = ldap.dn.str2dn(dn)[0]
    return ldap.dn.dn2str([rdn])


def get_parent_dn(dn):
    r"""
    >>> get_parent_dn(r'a=b\,c+d=e,f=g+h=i\,j')
    'f=g+h=i\\,j'
    >>> get_parent_dn(r'a=b')
    """
    parent = ldap.dn.str2dn(dn)[1:]
    return ldap.dn.dn2str(parent) if parent else None


def to_bytes(value):
    if isinstance(value, list):
        return [to_bytes(item) for item in value]
    if not isinstance(value, bytes):
        return value.encode('utf-8')
    return value


def get_first(value):
    if isinstance(value, list | tuple):
        return value[0]
    return value


class LDAPConnection:
    """helper functions to modify LDAP-objects intended as glue for shell-scripts"""

    def __init__(self, no_starttls=False):
        self.ldapbase = ucr['ldap/base']
        self.login_dn = 'cn=admin,%s' % self.ldapbase
        self.pw_file = '/etc/ldap.secret'
        self.host = 'localhost'
        self.port = ucr.get('ldap/server/port', 389)
        self.ca_file = None
        self.protocol = 'ldap'
        self.kerberos = False
        self.serverctrls_for_add_and_modify = []
        self.connect(no_starttls)

    def connect(self, no_starttls=False):
        self.timeout = 5
        tls_mode = 0 if no_starttls else 2

        login_pw = ""
        if self.pw_file:
            with open(self.pw_file) as fp:
                login_pw = fp.readline().rstrip('\n')

        try:
            if self.protocol == 'ldapi':
                import urllib.parse
                socket = urllib.parse.quote(self.socket, '')
                ldapuri = f"{self.protocol}://{socket}"
            else:
                ldapuri = "%s://%s:%d" % (self.protocol, self.host, int(self.port))

            # lo = univention.uldap.access(host=self.host, port=int(self.port), base=self.adldapbase, binddn=self.login_dn , bindpw=self.pw_file, start_tls=tls_mode, ca_certfile=self.ca_file, uri=ldapuri)
            self.lo = ldap.initialize(ldapuri)
            if self.ca_file:
                self.lo.set_option(ldap.OPT_X_TLS_CACERTFILE, self.ca_file)
                self.lo.set_option(ldap.OPT_X_TLS_NEWCTX, 0)
            if tls_mode > 0:
                self.lo.start_tls_s()
        except Exception:
            ex = f'LDAP Connection to "{self.host}:{self.port}" failed (TLS: {not no_starttls}, Certificate: {self.ca_file})\n'
            import traceback
            raise Exception(ex + traceback.format_exc())

        self.lo.set_option(ldap.OPT_REFERRALS, 0)

        try:
            if self.kerberos:
                os.environ['KRB5CCNAME'] = '/tmp/ucs-test-ldap-glue.cc'
                self.get_kerberos_ticket()
                auth = ldap.sasl.gssapi("")
                self.lo.sasl_interactive_bind_s("", auth)
            elif login_pw:
                self.lo.simple_bind_s(self.login_dn, login_pw)
        except Exception:
            if self.kerberos:
                cred_msg = f'{self.principal!r} with Kerberos password {login_pw!r}'
            else:
                cred_msg = f'{self.login_dn!r} with simplebind password {login_pw!r}'
            ex = f'LDAP Bind as {cred_msg} failed over connection to "{self.host}:{self.port}" (TLS: {not no_starttls}, Certificate: {self.ca_file})\n'
            import traceback
            raise Exception(ex + traceback.format_exc())

    def get_kerberos_ticket(self):
        p1 = subprocess.Popen(['kdestroy'], close_fds=True)
        p1.wait()
        cmd_block = ['kinit', '--no-addresses', '--password-file=%s' % self.pw_file, self.principal]
        p1 = subprocess.Popen(cmd_block, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
        stdout, _stderr = p1.communicate()
        if p1.returncode != 0:
            raise Exception('The following command failed: "%s" (%s): %s' % (''.join(cmd_block), p1.returncode, stdout.decode('UTF-8')))

    def exists(self, dn):
        try:
            self.lo.search_ext_s(dn, ldap.SCOPE_BASE, timeout=10)
            return True
        except ldap.NO_SUCH_OBJECT:
            return False

    def get_attribute(self, dn, attribute):
        """Get attributes 'key' of LDAP object at 'dn'."""
        res = self.lo.search_ext_s(dn, ldap.SCOPE_BASE, timeout=10)
        try:
            return res[0][1][attribute]
        except LookupError:
            return []

    def get(self, dn, attr=[], required=False):
        """returns ldap object"""
        if dn:
            try:
                result = self.lo.search_ext_s(dn, ldap.SCOPE_BASE, '(objectClass=*)', attr, timeout=10)
            except ldap.NO_SUCH_OBJECT:
                result = []
            if result:
                return result[0][1]
        if required:
            raise ldap.NO_SUCH_OBJECT({'desc': 'no object'})
        return {}

    def create(self, dn, attrs):
        """Create LDAP object at 'dn' with attributes 'attrs'."""
        # attrs = {key,:[value] if isinstance(value, (str, bytes)) else value for key, value in attrs.items()}
        ldif = modlist.addModlist(attrs)
        print(f'Creating {dn!r} with {ldif!r}', file=sys.stderr)
        self.lo.add_ext_s(dn, ldif, serverctrls=self.serverctrls_for_add_and_modify)

    def delete(self, dn):
        """Delete LDAP object at 'dn'."""
        print(f'Deleting {dn!r}', file=sys.stderr)
        self.lo.delete_s(dn)

    def move(self, dn, newdn):
        """Move LDAP object from 'dn' to 'newdn'."""
        newrdn = get_rdn(newdn)
        parent1 = get_parent_dn(dn)
        parent2 = get_parent_dn(newdn)

        if parent1 != parent2:
            print(f'Moving {dn!r} as {newdn!r} into {parent2!r}', file=sys.stderr)
            self.lo.rename_s(dn, newrdn, parent2)
        else:
            print(f'Renaming {dn!r} to {newrdn!r}', file=sys.stderr)
            self.lo.modrdn_s(dn, newrdn)

    def set_attribute(self, dn, key, value):
        """Set attribute 'key' of LDAP object at 'dn' to 'value'."""
        print(f'Replace {key!r}={value!r} at {dn!r}', file=sys.stderr)
        self.lo.modify_ext_s(dn, [(ldap.MOD_REPLACE, key, value)], serverctrls=self.serverctrls_for_add_and_modify)

    def set_attributes(self, dn, **attributes):
        old_attributes = self.get(dn, attr=attributes.keys())
        attributes = {name: [attr] if not isinstance(attr, list | tuple) else attr for name, attr in attributes.items()}
        ldif = modlist.modifyModlist(old_attributes, attributes)
        comp_dn = dn
        if ldif:
            print(f'Modifying {comp_dn!r}: {ldif!r}', file=sys.stderr)
            self.lo.modify_ext_s(comp_dn, ldif, serverctrls=self.serverctrls_for_add_and_modify)

    def set_attribute_with_provision_ctrl(self, dn, key, value):
        LDB_CONTROL_PROVISION_OID = '1.3.6.1.4.1.7165.4.3.16'
        DSDB_CONTROL_REPLICATED_UPDATE_OID = '1.3.6.1.4.1.7165.4.3.3'
        ctrls = [LDAPControl(LDB_CONTROL_PROVISION_OID, criticality=0), LDAPControl(DSDB_CONTROL_REPLICATED_UPDATE_OID, criticality=0), *self.serverctrls_for_add_and_modify]
        print(f'Replace {key!r}={value!r} at {dn!r} (with provision control)', file=sys.stderr)
        self.lo.modify_ext_s(dn, [(ldap.MOD_REPLACE, key, value)], serverctrls=ctrls)

    def delete_attribute(self, dn, key):
        """Delete attribute 'key' of LDAP object at 'dn'."""
        print(f'Removing {key!r} from {dn!r}', file=sys.stderr)
        self.lo.modify_ext_s(dn, [(ldap.MOD_DELETE, key, None)], serverctrls=self.serverctrls_for_add_and_modify)

    def append_to_attribute(self, dn, key, value):
        """Add 'value' to attribute 'key' of LDAP object at 'dn'."""
        print(f'Appending {key!r}={value!r} to {dn!r}', file=sys.stderr)
        self.lo.modify_ext_s(dn, [(ldap.MOD_ADD, key, value)], serverctrls=self.serverctrls_for_add_and_modify)

    def remove_from_attribute(self, dn, key, value):
        """Remove 'value' from attribute 'key' of LDAP object at 'dn'."""
        print(f'Removing {key!r}={value!r} from {dn!r}', file=sys.stderr)
        self.lo.modify_ext_s(dn, [(ldap.MOD_DELETE, key, value)], serverctrls=self.serverctrls_for_add_and_modify)


class ADConnection(LDAPConnection):
    """helper functions to modify AD-objects"""

    def __init__(self, configbase='connector'):
        self.configbase = configbase
        self.adldapbase = ucr['%s/ad/ldap/base' % configbase]
        self.addomain = self.adldapbase.replace(',DC=', '.').replace('DC=', '')
        self.kerberos = ucr.is_true('%s/ad/ldap/kerberos' % configbase)
        if self.kerberos:  # i.e. if UCR ad/member=true
            # Note: tests/domainadmin/account is an OpenLDAP DN but
            #       we only extract the username from it in ldap_glue
            self.login_dn = ucr['tests/domainadmin/account']
            self.principal = ldap.dn.str2dn(self.login_dn)[0][0][1]
            self.pw_file = ucr['tests/domainadmin/pwdfile']
        else:
            self.login_dn = ucr['%s/ad/ldap/binddn' % configbase]
            self.pw_file = ucr['%s/ad/ldap/bindpw' % configbase]
        self.host = ucr['%s/ad/ldap/host' % configbase]
        self.port = ucr['%s/ad/ldap/port' % configbase]
        self.ca_file = ucr['%s/ad/ldap/certificate' % configbase]
        self.protocol = 'ldap'
        self.serverctrls_for_add_and_modify = []
        no_starttls = ucr.is_false('%s/ad/ldap/ssl' % configbase)
        self.connect(no_starttls)

    def search(self, ldap_filter, attr=[], required=False):
        res = self.lo.search_ext_s(self.adldapbase, ldap.SCOPE_SUBTREE, ldap_filter, attr, timeout=10)
        result = []
        for dn, attr in res:
            if dn:
                result.append((dn, attr))
        if not result and required:
            raise ldap.NO_SUCH_OBJECT({'desc': 'no object'})
        return result

    def get(self, dn, attr=[], required=False):
        """returns ldap object"""
        if dn:
            try:
                result = self.lo.search_ext_s(dn, ldap.SCOPE_BASE, '(objectClass=*)', attr, timeout=10)
            except ldap.NO_SUCH_OBJECT:
                result = []
            if result:
                return result[0][1]
        if required:
            raise ldap.NO_SUCH_OBJECT({'desc': 'no object'})
        return {}

    def set_attributes(self, dn, **attributes):
        old_attributes = self.get(dn, attr=attributes.keys())
        ldif = modlist.modifyModlist(old_attributes, attributes)
        if ldif:
            self.lo.modify_ext_s(dn, ldif)

    def add_to_group(self, group_dn, member_dn):
        self.append_to_attribute(group_dn, 'member', member_dn)

    def remove_from_group(self, group_dn, member_dn):
        self.remove_from_attribute(group_dn, 'member', member_dn)

    def getdn(self, filter):
        for dn, _attr in self.lo.search_ext_s(self.adldapbase, ldap.SCOPE_SUBTREE, filter, timeout=10):
            if dn:
                print(dn)

    def createuser(self, username, position=None, **attributes):
        """
        Create a AD user with attributes as given by the keyword-args
        `attributes`. The created user will be populated with some defaults if
        not otherwise set.

        Returns the dn of the created user.
        """
        cn = to_bytes(attributes.get('cn', username))
        sn = to_bytes(attributes.get('sn', b'SomeSurName'))

        new_position = position or 'cn=users,%s' % self.adldapbase
        new_dn = 'cn=%s,%s' % (ldap.dn.escape_dn_chars(get_first(cn).decode("UTF-8")), new_position)

        defaults = (
            ('objectclass', [b'top', b'user', b'person', b'organizationalPerson']),
            ('cn', cn),
            ('sn', sn),
            ('sAMAccountName', to_bytes(username)),
            ('userPrincipalName', b'%s@%s' % (to_bytes(username), to_bytes(self.addomain))),
            ('displayName', b'%s %s' % (to_bytes(username), get_first(sn))))
        new_attributes = dict(defaults)
        new_attributes.update(attributes)
        self.create(new_dn, new_attributes)
        return new_dn

    def rename_or_move_user_or_group(self, dn, name=None, position=None):
        exploded = ldap.dn.str2dn(dn)
        new_rdn = [("cn", name, ldap.AVA_STRING)] if name else exploded[0]
        new_position = ldap.dn.str2dn(position) if position else exploded[1:]
        new_dn = ldap.dn.dn2str([new_rdn, *new_position])
        self.move(dn, new_dn)
        return new_dn

    def group_create(self, groupname, position=None, **attributes):
        """
        Create a AD group with attributes as given by the keyword-args
        `attributes`. The created group will be populated with some defaults if
        not otherwise set.

        Returns the dn of the created group.
        """
        new_position = position or 'cn=groups,%s' % self.adldapbase
        new_dn = f'cn={ldap.dn.escape_dn_chars(groupname)},{new_position}'

        defaults = (('objectclass', [b'top', b'group']), ('sAMAccountName', to_bytes(groupname)))
        new_attributes = dict(defaults)
        new_attributes.update(attributes)
        self.create(new_dn, new_attributes)
        return new_dn

    def windows_create(self, name, position=None, **attributes):
        """
        Create a AD windows with attributes as given by the keyword-args
        `attributes`. The created windows will be populated with some defaults if
        not otherwise set.

        Returns the dn of the created windows.
        """
        new_position = position or 'cn=Computers,%s' % self.adldapbase
        new_dn = f'cn={ldap.dn.escape_dn_chars(name)},{new_position}'

        defaults = (('userAccountControl', [b'4098']), ('objectclass', [b'top', b'person', b'organizationalPerson', b'user', b'computer']), ('cn', to_bytes(name)))
        new_attributes = dict(defaults)
        new_attributes.update(attributes)
        self.create(new_dn, new_attributes)
        return new_dn

    def getprimarygroup(self, user_dn):
        try:
            res = self.lo.search_ext_s(user_dn, ldap.SCOPE_BASE, timeout=10)
        except Exception:
            return None
        primaryGroupID = res[0][1]['primaryGroupID'][0].decode('UTF-8')
        res = self.lo.search_ext_s(
            self.adldapbase,
            ldap.SCOPE_SUBTREE,
            'objectClass=group',
            timeout=10,
        )

        import re
        regex = '^(.*?)-%s$' % primaryGroupID
        for r in res:
            if r[0] is None or r[0] == 'None':
                continue  # Referral
            if re.search(regex, self.decode_sid(r[1]['objectSid'][0])):
                return r[0]

    def setprimarygroup(self, user_dn, group_dn):
        res = self.lo.search_ext_s(group_dn, ldap.SCOPE_BASE, timeout=10)
        import re
        groupid = (re.search('^(.*)-(.*?)$', self.decode_sid(res[0][1]['objectSid'][0]))).group(2)
        self.set_attribute(user_dn, 'primaryGroupID', groupid.encode('UTF-8'))

    def container_create(self, name, position=None, description=None):

        if not position:
            position = self.adldapbase

        attrs = {}
        attrs['objectClass'] = [b'top', b'container']
        attrs['cn'] = to_bytes(name)
        if description:
            attrs['description'] = to_bytes(description)

        container_dn = f'cn={ldap.dn.escape_dn_chars(name)},{position}'
        self.create(container_dn, attrs)
        return container_dn

    def createou(self, name, position=None, description=None):

        if not position:
            position = self.adldapbase

        attrs = {}
        attrs['objectClass'] = [b'top', b'organizationalUnit']
        attrs['ou'] = to_bytes(name)
        if description:
            attrs['description'] = to_bytes(description)

        dn = f'ou={ldap.dn.escape_dn_chars(name)},{position}'
        self.create(dn, attrs)
        return dn

    def verify_object(self, dn, expected_attributes):
        """
        Verify an object exists with the given `dn` and attributes in the
        AD-LDAP. Setting `expected_attributes` to `None` requires the object to
        not exist. `expected_attributes` is a dictionary of
        `attribute`:`list-of-values`.

        This will throw an `AssertionError` in case of a mismatch.
        """
        if expected_attributes is None:
            assert not self.exists(dn), f"AD object {dn} should not exist"
        else:
            ad_object = self.get(dn)
            for (key, value) in expected_attributes.items():
                ad_value = {tcommon.to_unicode(x).lower() for x in ad_object.get(key, [])}
                expected = set((tcommon.to_unicode(v).lower() for v in value) if isinstance(value, list | tuple) else (tcommon.to_unicode(value).lower(),))
                if not expected.issubset(ad_value):
                    try:
                        ad_value = {tcommon.normalize_dn(dn) for dn in ad_value}
                        expected = {tcommon.normalize_dn(dn) for dn in expected}
                    except ldap.DECODING_ERROR:
                        pass
                error_msg = f'{key}: {expected} not in {ad_value}, object {ad_object}'
                assert expected.issubset(ad_value), error_msg


if __name__ == '__main__':
    import doctest
    doctest.testmod()
