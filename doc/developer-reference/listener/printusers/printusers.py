# SPDX-FileCopyrightText: 2021-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Example for a listener module, which logs changes to users."""

import errno
import os
from collections import namedtuple
from typing import Dict, List

import univention.debug as ud

from listener import SetUID


description = 'print all names/users/uidNumbers into a file'
filter = ''.join("""\
(&
    (|
        (&
            (objectClass=posixAccount)
            (objectClass=shadowAccount)
        )
        (objectClass=univentionMail)
        (objectClass=sambaSamAccount)
        (objectClass=simpleSecurityObject)
        (objectClass=inetOrgPerson)
    )
    (!(objectClass=univentionHost))
    (!(uidNumber=0))
    (!(uid=*$))
)""".split())
attributes = ['uid', 'uidNumber', 'cn']
_Rec = namedtuple('_Rec', 'uid uidNumber cn')

USER_LIST = '/root/UserList.txt'


def handler(dn: str, new: Dict[str, List[bytes]], old: Dict[str, List[bytes]]) -> None:
    """
    Write all changes into a text file.
    This function is called on each change.
    """
    if new and old:
        _handle_change(dn, new, old)
    elif new and not old:
        _handle_add(dn, new)
    elif old and not new:
        _handle_remove(dn, old)


def _handle_change(dn: str, new: Dict[str, List[bytes]], old: Dict[str, List[bytes]]) -> None:
    """Called when an object is modified."""
    o_rec = _rec(old)
    n_rec = _rec(new)
    ud.debug(ud.LISTENER, ud.INFO, 'Edited user "%s"' % (o_rec.uid,))
    _writeit(o_rec, u'edited. Is now:')
    _writeit(n_rec, u'')


def _handle_add(dn: str, new: Dict[str, List[bytes]]) -> None:
    """Called when an object is newly created."""
    n_rec = _rec(new)
    ud.debug(ud.LISTENER, ud.INFO, 'Added user "%s"' % (n_rec.uid,))
    _writeit(n_rec, u'added')


def _handle_remove(dn: str, old: Dict[str, List[bytes]]) -> None:
    """Called when an previously existing object is removed."""
    o_rec = _rec(old)
    ud.debug(ud.LISTENER, ud.INFO, 'Removed user "%s"' % (o_rec.uid,))
    _writeit(o_rec, u'removed')


def _rec(data: Dict[str, List[bytes]]) -> _Rec:
    """Retrieve symbolic, numeric ID and name from user data."""
    return _Rec(*(data.get(attr, (None,))[0] for attr in attributes))


def _writeit(rec: _Rec, comment: str) -> None:
    """Append CommonName, symbolic and numeric User-IDentifier, and comment to file."""
    nuid = u'*****' if rec.uid in ('root', 'spam') else rec.uidNumber
    indent = '\t' if comment is None else ''
    try:
        with SetUID(), open(USER_LIST, 'a') as out:
            print(u'%sName: "%s"' % (indent, rec.cn), file=out)
            print(u'%sUser: "%s"' % (indent, rec.uid), file=out)
            print(u'%sUID: "%s"' % (indent, nuid), file=out)
            if comment:
                print(u'%s%s' % (indent, comment), file=out)
    except IOError as ex:
        ud.debug(
            ud.LISTENER, ud.ERROR,
            'Failed to write "%s": %s' % (USER_LIST, ex))


def initialize() -> None:
    """
    Remove the log file.
    This function is called when the module is forcefully reset.
    """
    try:
        with SetUID():
            os.remove(USER_LIST)
        ud.debug(
            ud.LISTENER, ud.INFO,
            'Successfully deleted "%s"' % (USER_LIST,))
    except OSError as ex:
        if ex.errno == errno.ENOENT:
            ud.debug(
                ud.LISTENER, ud.INFO,
                'File "%s" does not exist, will be created' % (USER_LIST,))
        else:
            ud.debug(
                ud.LISTENER, ud.WARN,
                'Failed to delete file "%s": %s' % (USER_LIST, ex))
