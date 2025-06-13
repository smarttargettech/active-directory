#!/usr/share/ucs-test/runner python3
## desc: a framework to create arbitrary objects with hacking purposes
## bugs: [41799]
## versions:
##  4.1-2: skip
##  4.2-0: fixed
## roles-not:
##  - basesystem
## packages:
##  - python3-univention-lib
##  - python3-ldap
## exposure: dangerous

import sys

import ldap

import univention.testing.strings as uts
import univention.uldap
from univention.testing import utils


class Hacked(Exception):
    pass


class HackingAttempt:

    def __init__(self, ml, search_filter=None, exclude=None):
        self.ml = ml
        self.search_filter = search_filter or 'objectClass=*'
        if exclude:
            self.exclude = exclude

    def exclude(self, dn):
        return 'cn=users' in ldap.explode_dn(dn)

    def modlists(self, basedn):
        if self.exclude(basedn):
            return
        yield basedn, self.ml


class HackingAttemptAdd(HackingAttempt):

    def __init__(self, ml, search_filter=None, exclude=None):
        super().__init__(ml, search_filter, exclude)
        self.uid = uts.random_username()

    def modlists(self, basedn):
        for basedn, ml in super().modlists(basedn):
            for attr in ['cn', 'krb5PrincipalName', 'SAMLServiceProviderIdentifier', 'sambaDomainName', 'dc', 'univentionAppID', 'relativeDomainName', 'uid', 'ou', 'zoneName', 'univentionVirtualMachineUUID']:
                if any(x[0] == attr for x in ml):
                    yield (f'{attr}={self.uid},{basedn}', [*ml, ('uid', b'', self.uid.encode('UTF-8')), ('cn', b'', self.uid.encode('UTF-8'))])


class Hacking:

    def __init__(self, creations=None, modifications=None):
        self.creations = creations or _creations
        self.modifications = modifications or _modifications
        self.lo_admin = utils.get_ldap_connection()  # TODO: use connection to DC master because this has only partly replicated objects

    def __call__(self, lo):
        failures = set()
        lo_admin = utils.get_ldap_connection()
        print(f'Testing for {lo.binddn!r}', file=sys.stderr)

        for dn, al in self.testcases(self.creations):
            try:
                lo.add(dn, al)
            except ldap.INSUFFICIENT_ACCESS:
                print(f"OK: ldapadd of {dn} denied")
            except (ldap.OBJECT_CLASS_VIOLATION, ldap.CONSTRAINT_VIOLATION, ldap.TYPE_OR_VALUE_EXISTS, ldap.NO_SUCH_OBJECT) as exc:
                print(f'SKIP: {dn}: {exc}')
            else:
                print(f"FAIL: ldapadd of {dn} (al={al!r}) successful", file=sys.stderr)
                failures.add(dn)
                lo_admin.delete(dn)

        for dn, ml in self.testcases(self.modifications):
            try:
                lo.modify(dn, ml)
            except ldap.INSUFFICIENT_ACCESS:
                print(f"OK: ldapmodify of {dn} denied")
            except (ldap.OBJECT_CLASS_VIOLATION, ldap.CONSTRAINT_VIOLATION, ldap.TYPE_OR_VALUE_EXISTS, ldap.NO_SUCH_OBJECT, ldap.ALREADY_EXISTS) as exc:
                print(f'SKIP: {dn}: {exc}')
            else:
                print(f"FAIL: ldapmodify of {dn} (ml={ml!r}) successful", file=sys.stderr)
                failures.add(dn)
                lo_admin.modify(dn, [(attr, new, old) for attr, old, new in ml])
        print('')

        if failures:
            raise Hacked('hijacking by %s succeeded for the following %d DNs: %s' % (lo.binddn, len(failures), '\n'.join(failures)))

    def testcases(self, cases):
        for hack in cases:
            for dn in set(self.lo_admin.searchDn(hack.search_filter)):
                for dn, ml in hack.modlists(dn):
                    yield (dn, ml)


# TODO: add shares with write access to /etc/ on the DC master
_creations = [
    HackingAttemptAdd([
        ('cn', b'', b'hacker'),
        ('objectClass', b'', b'organizationalRole'),
        ('objectClass', b'', b'posixAccount'),
        ('uidNumber', b'', b'0'),
        ('gidNumber', b'', b'0'),
        ('userPassword', b'', b'{crypt}$6$H.05VD/DuPnyIoNC$yIJwYBZNWU4fkCV8SE0qiP7yDB3IQWnFPR08Ui.MKcHQBZvy7OImU2avb22GTYGlzBg4FjttMYCUz8FWSp0Jl/'),
        ('homeDirectory', b'', b'/foo/'),
    ]),
]
_modifications = [
    # try modify all existing objects and add a user account to existing object
    HackingAttempt([
        ('objectClass', b'', b'posixAccount'),
        ('uid', b'', uts.random_username().encode("UTF-8")),
        ('uidNumber', b'', b'0'),
        ('gidNumber', b'', b'0'),
        ('userPassword', b'', b'{crypt}$6$H.05VD/DuPnyIoNC$yIJwYBZNWU4fkCV8SE0qiP7yDB3IQWnFPR08Ui.MKcHQBZvy7OImU2avb22GTYGlzBg4FjttMYCUz8FWSp0Jl/'),
        ('homeDirectory', b'', b'/foo/'),
    ]),
    # upgrade a posixGroup to a posixAccount
    HackingAttempt(search_filter='objectClass=univentionGroup', ml=[
        ('objectClass', b'', b'posixAccount'),
        ('uid', b'', uts.random_username().encode("UTF-8")),
        ('uidNumber', b'', b'0'),
        ('homeDirectory', b'', b'/foo/'),
    ]),
]


if __name__ == "__main__":
    # TODO: create more objects, e.g. Apps, UVMM, UCS@school things prior to testing
    # TODO: test also with ldap bind of users, memberservers, etc.
    hacking = Hacking()
    for lo in [univention.uldap.getMachineConnection(ldap_master=True)]:
        try:
            hacking(lo)
        except Hacked:
            raise
# vim: set ft=python :
