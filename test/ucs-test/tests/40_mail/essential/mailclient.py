"""
.. module:: mailclient
.. moduleauthor:: Ammar Najjar <najjar@univention.de>
"""
from __future__ import annotations

import email
import imaplib
import time

import univention.testing.strings as uts


class WrongAcls(Exception):
    pass


class LookupFail(Exception):
    pass


class ReadFail(Exception):
    pass


class AppendFail(Exception):
    pass


class WriteFail(Exception):
    pass


class BaseMailClient:
    """
    BaseMailClient is a Base (interface) for imaplib.IMAP4_SSL and imaplib.IMAP4
    Does not work alone, can be used only as a super class of other child class.
    """

    def login_plain(self, user, password, authuser=None):
        def plain_callback(response):
            if authuser is None:
                return f"{user}\x00{user}\x00{password}"
            else:
                return f"{user}\x00{authuser}\x00{password}"
        return self.authenticate('PLAIN', plain_callback)

    def log_in(self, usermail: str, password: str) -> None:
        """
        wrap the super login method with try except

        :usermail: string, user mail
        :password: string, user password
        """
        print(f'Logging in with username={usermail!r} and password={password!r}')
        try:
            self.login(usermail, password)
            self.owner = usermail
        except Exception as ex:
            print("Login Failed with exception:%r" % ex)
            raise

    def login_ok(self, usermail, password, expected_to_succeed=True):
        """
        Check if login is OK

        :usermail: string, user mail
        :password: string, user password
        :expected_to_succeed: boolean, True if expected to be OK
        :return: 0 if the result = expected, else 1
        """
        try:
            self.login(usermail, password)
            self.logout()
        except Exception as ex:
            if expected_to_succeed:
                print("Login Failed with exception:%r" % ex)
                return 1
        return 0

    def get_quota_root(self, mailbox):
        """docstring for get_quota_root"""
        response, quota_list = self.getquotaroot(mailbox)
        quota = quota_list[1][0].split(')')[0].split()[-1]
        return response, quota

    def getMailBoxes(self):
        """
        Get Mail boxes for the user logged in

        :returns: list of strings, list of existing mailboxes
        """
        result = []
        mBoxes = self.list()[1]
        if mBoxes[0]:
            result = [x.split(b'" ')[-1].decode('UTF-8') for x in mBoxes if b'Noselect' not in x.split()[0]]
            for i, item in enumerate(result):
                if '"' in item:
                    item = item.replace('"', '')
                    result[i] = item
        return result

    def get_acl(self, mailbox: str) -> dict[str, dict[str, str]]:
        """
        get the exact acls from getacl

        :mailbox: string, user mailbox name
        :returns: string, acl strign or permission denied
        """
        _code, acls = self.getacl(mailbox)

        # parse string into tokens
        tokens = []
        merge = False
        for token in acls[0].decode('UTF-8').split():
            if merge:
                # append to last token
                tokens[-1] = f'{tokens[-1]} {token}'
                if token.endswith('"'):
                    merge = False
                    tokens[-1] = tokens[-1].strip('"')
            else:
                tokens.append(token)
                if token.startswith('"'):
                    merge = True
            # Bug #51629: TODO: if global ACLs for other users are used, we may have to remove leading hashes
            tokens[-1] = tokens[-1].lstrip('#')

        if tokens:
            mailbox = tokens.pop(0)
        acl_result = {}
        while len(tokens) >= 2:
            identifier = tokens.pop(0)
            rights = tokens.pop(0)
            acl_result[identifier] = rights

        return {mailbox: acl_result}

    def check_acls(self, expected_acls: str) -> None:
        """
        Check if the the correct acls are set

        :expected_acls: string
        The expected acls are also mapped to the new set of
        acls are shown in the permissions_map

        Raises an Exception if the set acls are not correct
        """
        permissions_map = {
            "a": "a",
            "l": "l",
            "r": "r",
            "s": "s",
            "w": "w",
            "i": "i",
            "p": "p",
            "k": "kc",
            "x": "xc",
            "t": "td",
            "e": "ed",
            "c": "kxc",
            "d": "ted",
        }
        for mailbox in expected_acls:
            current = self.get_acl(mailbox)
            print('Current = ', current)
            for who in expected_acls.get(mailbox):
                permissions = expected_acls.get(mailbox).get(who)
                set1 = set(''.join([permissions_map[x] for x in permissions]))
                set2 = current.get(mailbox).get(who)
                set2 = set() if set2 is None else set(set2)

                if not (who in current.get(mailbox).keys() or set1 == set2):
                    raise WrongAcls(f'\nExpected = {expected_acls.get(mailbox).get(who)}\nCurrent = {current.get(mailbox).get(who)}\n')

    def check_lookup(self, mailbox_owner, expected_result):
        """
        Checks the lookup access of a certain mailbox

        :expected_result: dict{mailbox : bool}
        """
        print(f'check_lookup() mailbox_owner={mailbox_owner!r} expected_result={expected_result!r}')
        for mailbox, retcode in expected_result.items():
            if mailbox_owner != self.owner:
                mailbox = self.mail_folder(mailbox_owner, mailbox)
            data = self.getMailBoxes()
            print('Lookup :', mailbox, data)
            if (mailbox in data) != retcode:
                raise LookupFail('Un-expected result for listing the mailbox %s' % mailbox)

    def check_read(self, mailbox_owner, expected_result):
        """
        Checks the read access of a certain mailbox

        :expected_result: dict{mailbox : bool}
        """
        for mailbox, retcode in expected_result.items():
            if mailbox_owner != self.owner:
                mailbox = self.mail_folder(mailbox_owner, mailbox)
            self.select(mailbox)
            typ, data = self.status(mailbox, '(MESSAGES RECENT UIDNEXT UIDVALIDITY UNSEEN)')
            print('Read Retcode:', typ, data)
            if (typ == 'OK') != retcode:
                raise ReadFail('Unexpected read result for the inbox %s' % mailbox)
            if 'OK' in typ:
                # typ, data = self.search(None, 'ALL')
                # for num in data[0].split():
                #     typ, data = self.fetch(num, '(RFC822)')
                #     print 'Message %s\n%s\n' % (num, data[0][1])
                self.close()

    def check_append(self, mailbox_owner, expected_result):
        """
        Checks the append access of a certain mailbox

        :expected_result: dict{mailbox : bool}
        """
        for mailbox, retcode in expected_result.items():
            if mailbox_owner != self.owner:
                mailbox = self.mail_folder(mailbox_owner, mailbox)
            self.select(mailbox)
            typ, data = self.append(
                mailbox, '',
                imaplib.Time2Internaldate(time.time()),
                str(email.message_from_string('TEST %s' % mailbox)),
            )
            print('Append Retcode:', typ, data)
            if (typ == 'OK') != retcode:
                raise AppendFail('Unexpected append result to inbox %s' % mailbox)
            if 'OK' in typ:
                self.close()

    def check_write(self, mailbox_owner, expected_result):
        """
        Checks the write access of a certain mailbox

        :expected_result: dict{mailbox : bool}
        """
        for mailbox, retcode in expected_result.items():
            # actual Permissions are given to shared/owner/INBOX
            # This is different than listing
            if mailbox_owner != self.owner and mailbox == 'INBOX':
                mailbox = f'shared/{mailbox_owner}/INBOX'
            subname = uts.random_name()
            typ, data = self.create(f'{mailbox}/{subname}')
            print('Create Retcode:', typ, data)
            if (typ == 'OK') != retcode:
                raise WriteFail('Unexpected create sub result mailbox in %s' % mailbox)
            if 'OK' in typ:
                typ, data = self.delete(f'{mailbox}/{subname}')
                print('Delete Retcode:', typ, data)
                if (typ == 'OK') != retcode:
                    raise WriteFail('Unexpected delete sub result mailbox in %s' % mailbox)

    def mail_folder(self, mailbox_owner, mailbox):
        if mailbox == 'INBOX':
            return f'shared/{mailbox_owner}'
        if '/' not in mailbox:
            return f'shared/{mailbox_owner}/{mailbox}'
        return mailbox

    def check_permissions(self, owner_user, mailbox, permission):
        """Check Permissions all together"""
        permissions = {
            'lookup': 'l',
            'read': 'lrs',
            'post': 'lrsp',
            'append': 'lrspi',
            'write': 'lrspiwcd',
            'all': 'lrspiwcda',
        }

        def lookup_OK(permission):
            return set(permissions.get('lookup')).issubset(permission)

        def read_OK(permission):
            return set(permissions.get('read')).issubset(permission)

        def post_OK(permission):
            return set(permissions.get('post')).issubset(permission)

        def append_OK(permission):
            return set(permissions.get('append')).issubset(permission)

        def write_OK(permission):
            return set(permissions.get('write')).issubset(permission)

        def all_OK(permission):
            return set(permissions.get('all')).issubset(permission)

        self.check_lookup(owner_user, {mailbox: lookup_OK(permission)})
        self.check_read(owner_user, {mailbox: read_OK(permission)})
        self.check_append(owner_user, {mailbox: append_OK(permission)})
        self.check_write(owner_user, {mailbox: write_OK(permission)})


class MailClient_SSL(imaplib.IMAP4_SSL, BaseMailClient):
    """MailClient_SSL is a wrapper for imaplib.IMAP4_SSL"""

    def __init__(self, host: str, port: int = 993) -> None:
        imaplib.IMAP4_SSL.__init__(self, host, port)


class MailClient(imaplib.IMAP4, BaseMailClient):
    """MailClient is a wrapper for imaplib.IMAP4"""

    def __init__(self, host, port=143):
        imaplib.IMAP4.__init__(self, host, port)
