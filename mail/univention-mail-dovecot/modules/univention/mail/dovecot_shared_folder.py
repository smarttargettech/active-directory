#!/usr/bin/python3
#
# Univention Mail Dovecot - shared code for listeners
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

import grp
import imaplib
import os
import re
import shutil
import stat
import subprocess
import tempfile
import traceback
from typing import Any

import univention.admin.modules
from univention.admin.uldap import getMachineConnection
from univention.config_registry import handler_set
from univention.lib.misc import custom_username
from univention.mail.dovecot import DovecotListener


# UDM name → (IMAP, doveadm)
dovecot_acls = {
    "read": ("lrws", ["lookup", "read", "write", "write-seen"]),
    "post": ("lrwsp", ["lookup", "read", "write", "write-seen", "post"]),
    "append": ("lrwspi", ["lookup", "read", "write", "write-seen", "post", "insert"]),
    "write": ("lrwspite", ["lookup", "read", "write", "write-seen", "post", "insert", "write-deleted", "expunge"]),
    "all": ("lrwspitekxa", ["lookup", "read", "write", "write-seen", "post", "insert", "write-deleted", "expunge", "create", "delete", "admin"]),
}
global_acl_path = '/etc/dovecot/global-acls'
glocal_acl_pattern1 = re.compile(r'(?P<folder>[^ ]+) "(?P<id>.+)" (?P<acl>\w+)')
glocal_acl_pattern2 = re.compile(r'(?P<folder>[^ ]+) (?P<id>.+) (?P<acl>\w+)')


class DovecotFolderAclEntry:  # noqa: PLW1641
    def __init__(self, folder_name: str, identifier: str, acl: str) -> None:
        self.folder_name = folder_name
        self.identifier = identifier
        self.acl = acl

    def __eq__(self, other):  # type: ignore
        return all((
            self.folder_name == other.folder_name,
            self.identifier == other.identifier,
            self.acl == other.acl,
        ))

    def __repr__(self) -> str:
        return f'{self.folder_name} "{self.identifier}" {self.acl}'

    @classmethod
    def from_str(cls, line):  # type: (str) -> DovecotFolderAclEntry
        # try with quotation marks first
        m = glocal_acl_pattern1.match(line.strip())
        if m:
            val = m.groupdict()
            return cls(val['folder'], val['id'], val['acl'])
        # try without quotation marks (created with univention-mail-dovecot 3.0.1-4)
        m = glocal_acl_pattern2.match(line.strip())
        if m:
            val = m.groupdict()
            return cls(val['folder'], val['id'], val['acl'])
        else:
            raise ValueError(f"Line {line!r} doesn't match ACL pattern.")


class DovecotGlobalAclFile:
    dovemail_gid = grp.getgrnam('dovemail').gr_gid

    def __init__(self, listener: Any) -> None:
        self.listener = listener
        self._acls: list[DovecotFolderAclEntry] = []
        self._fix_permissions()

    def add_acls(self, acl_list: list[DovecotFolderAclEntry]) -> None:
        self._read()
        for acl in acl_list:
            if acl not in self._acls:
                self._acls.append(acl)
        self._write()

    def remove_acls(self, folder_name: str) -> None:
        self._read()
        self._acls = [acl for acl in self._acls if acl.folder_name != folder_name]
        self._write()

    def _fix_permissions(self, path: str = global_acl_path, fileno: int | None = None) -> None:
        def set_perms(fileno: int) -> None:
            os.fchown(fileno, 0, self.dovemail_gid)
            os.fchmod(fileno, stat.S_IRUSR | stat.S_IWUSR | stat.S_IRGRP)

        try:
            self.listener.setuid(0)
            if fileno:
                set_perms(fileno)
            else:
                mode = 'rb' if os.path.exists(path) else 'wb'
                with open(path, mode) as fp:
                    set_perms(fp.fileno())
        finally:
            self.listener.unsetuid()

    def _read(self) -> None:
        self._acls = []
        try:
            self.listener.setuid(0)
            for line in open(global_acl_path):
                self._acls.append(DovecotFolderAclEntry.from_str(line))
        finally:
            self.listener.unsetuid()

    def _write(self) -> None:
        fileno, filename = tempfile.mkstemp(prefix='.global-acls')
        for acl in self._acls:
            os.write(fileno, f'{acl}\n'.encode())
        self._fix_permissions(fileno=fileno)
        os.close(fileno)
        try:
            self.listener.setuid(0)
            shutil.move(filename, global_acl_path)
        finally:
            self.listener.unsetuid()


class DovecotSharedFolderListener(DovecotListener):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.modules = ["mail/folder"]
        self.acl_key = "univentionMailACL"
        self.global_acls = DovecotGlobalAclFile(self.listener)

    def add_shared_folder(self, new: dict[str, list[bytes]]) -> None:
        if "mailPrimaryAddress" in new:
            # use a shared folder
            new_mailbox = new["mailPrimaryAddress"][0].decode('ASCII')
            # the maildir will be autocreated by dovecot
            acls = new.get(self.acl_key, [])[:]
            acls = [acl.decode('UTF-8') for acl in acls]
            # Even if there are no ACL entries, we must still _change_ at
            # least one entry through IMAP, so the shared mailbox list
            # dictionary is updated. Lets remove the (afterwards) unnecessary
            # master-user entry.
            acls.append("dovecotadmin none")
            try:
                # give master-user admin rights on mailbox
                self.doveadm_set_mailbox_acls("shared/%s" % new_mailbox, ["dovecotadmin all"])
                # use IMAP to set actual ACLs, so the shared mailbox list dictionary is updated
                self.imap_set_mailbox_acls(new_mailbox, "INBOX", acls)
                self.add_global_acls(new)
            except Exception as exc:
                self.log_e("Failed setting ACLs on new shared mailbox '%s': %s" % (new_mailbox, exc))
                return
            self.log_p("Created shared mailbox '%s'." % new_mailbox)
        else:
            # use a public folder
            new_mailbox = new["cn"][0].decode('UTF-8')
            try:
                self.update_public_mailbox_configuration()
                self.create_public_folder(new_mailbox)
                acls = new.get(self.acl_key)
                if acls:
                    acls = [acl.decode('UTF-8') for acl in acls]
                    self.doveadm_set_mailbox_acls("%s/INBOX" % new_mailbox, acls)
                    self.log_p("Set ACLs on '%s'." % new_mailbox)
            except Exception:
                self.log_e("Failed creating public mailbox '%s'." % new_mailbox)
                return
            self.log_p("Created public mailbox '%s'." % new_mailbox)

    def del_shared_folder(self, old: dict[str, list[bytes]]) -> None:
        if "mailPrimaryAddress" in old:
            # shared folder
            old_mailbox = old["mailPrimaryAddress"][0].decode('ASCII')
            old_loc, old_domain = old_mailbox.split("@")
            global_mail_home = self.get_maillocation()
            path = str(global_mail_home).replace("%Ld", old_domain).replace("%Ln", old_loc)
            # cannot unsubscribe to non-existing shared folder (a.k.a. private mailbox)
            self.remove_global_acls(old)
        else:
            # public folder
            old_mailbox = old["cn"][0].decode('UTF-8')
            old_loc, old_domain = old_mailbox.split("@")
            path = self.get_public_location(old_mailbox)
            if self.acl_key in old:
                # Only users with ACL entries can potentially have subscribed, unsubscribe them.
                # For performance reasons this intentionally ignores groups.
                folder = "%s/INBOX" % old_mailbox
                self.unsubscribe_from_mailbox([acl.decode('ASCII').split()[0] for acl in old[self.acl_key] if b"@" in acl.split()[0]], folder)
            # update namespaces
            self.update_public_mailbox_configuration(delete_only=old_mailbox)

        # remove mailbox from disk
        if self.listener.configRegistry.is_true("mail/dovecot/mailbox/delete", False):
            try:
                self.listener.setuid(0)
                shutil.rmtree(path, ignore_errors=True)
            except Exception:
                self.log_e("Error deleting mailbox '%s'." % old_mailbox)
                return
            finally:
                self.listener.unsetuid()
            self.log_p("Deleted mailbox '%s'." % old_mailbox)
        else:
            self.log_p("Deleting of mailboxes disabled (mailbox '%s')." % old_mailbox)

    def mod_shared_folder(self, old: dict[str, list[bytes]], new: dict[str, list[bytes]]) -> None:
        if "mailPrimaryAddress" in new:
            # use a shared folder
            new_mailbox = new["mailPrimaryAddress"][0].decode('ASCII')

            if "mailPrimaryAddress" in old:
                # it remains a shared folder
                old_mailbox = old["mailPrimaryAddress"][0].decode('ASCII')
                if new_mailbox != old_mailbox:
                    # rename/move mailbox inside private namespace
                    #
                    # cannot unsubscribe to non-existing shared folder (a.k.a. private mailbox)
                    self.move_user_home(new_mailbox, old_mailbox, True)
                    self.remove_global_acls(old)
                    # self.add_global_acls(new) is further down
                    self.log_p("Moved mailbox '%s' -> '%s'." % (old_mailbox, new_mailbox))
                else:
                    # no address change
                    pass
            else:
                # move mailbox from public to private namespace
                self.log_p("Moving mailbox from public to private namespace...")
                old_mailbox = old["cn"][0].decode('UTF-8')
                try:
                    pub_loc = self.get_public_location(old_mailbox)
                    new_user_home = self.get_user_home(new_mailbox)
                    if self.acl_key in old:
                        old_acl_users = [acl.split()[0].decode('UTF-8') for acl in old[self.acl_key] if b"@" in acl.split()[0]]
                        self.unsubscribe_from_mailbox(old_acl_users, "%s/INBOX" % old_mailbox)
                    # update dovecot config
                    self.update_public_mailbox_configuration()
                    # move mail home
                    self.move_mail_home(pub_loc, new_user_home, new_mailbox, True)
                    old_maildir = os.path.join(new_user_home, ".INBOX")
                    new_maildir = os.path.join(new_user_home, "Maildir")
                    try:
                        # rename mailbox
                        self.listener.setuid(0)
                        shutil.move(old_maildir, new_maildir)
                    except Exception:
                        self.log_e("Failed to move mail home (of '%s') from '%s' to '%s'.\n%s" % (
                            new_mailbox, old_maildir, new_maildir, traceback.format_exc()))
                        raise
                    finally:
                        self.listener.unsetuid()
                except Exception:
                    self.log_e("Could not rename/move mailbox ('%s' -> '%s').\n%s" % (old_mailbox, new_mailbox, traceback.format_exc()))
                    return
                self.log_p("Moved mailbox '%s' -> '%s'." % (old_mailbox, new_mailbox))

            # set ACLs
            acls = self._diff_acls(old, new)
            # Even if there are no ACL entries, we must still _change_ at
            # least one entry through IMAP, so the shared mailbox list
            # dictionary is updated. Lets remove the (afterwards) unnecessary
            # master-user entry.
            acls.append("dovecotadmin none")
            try:
                # give master-user admin rights on mailbox, so it can change its ACL
                self.doveadm_set_mailbox_acls("shared/%s" % new_mailbox, ["dovecotadmin all"])
                # use IMAP to set actual ACLs, so the shared mailbox list dictionary is updated
                self.imap_set_mailbox_acls(new_mailbox, "INBOX", acls)
                self.remove_global_acls(old)
                self.add_global_acls(new)
            except Exception as exc:
                self.log_e("Failed setting ACLs on moved shared mailbox ('%s' -> '%s'): %s" % (old_mailbox, new_mailbox, exc))
                return
            self.log_p("Set ACLs on '%s'." % new_mailbox)
        else:
            # use a public folder
            new_mailbox = new["cn"][0].decode('UTF-8')
            if "mailPrimaryAddress" in old:
                # move mailbox from private to public namespace
                self.log_p("Moving mailbox from private to public namespace...")
                old_mailbox = old["mailPrimaryAddress"][0].decode('ASCII')
                old_loc, old_domain = old_mailbox.rsplit("@", 1)
                # cannot unsubscribe to non-existing shared folder (a.k.a. private mailbox)
                try:
                    global_mail_home = self.get_maillocation()
                    old_path = str(global_mail_home).replace("%Ld", old_domain).replace("%Ln", old_loc).lower()
                    # update dovecot config
                    self.update_public_mailbox_configuration()
                    pub_loc = self.get_public_location(new_mailbox)
                    # move mail home
                    self.move_mail_home(old_path, pub_loc, new_mailbox, True)
                    old_maildir = os.path.join(pub_loc, "Maildir")
                    new_maildir = os.path.join(pub_loc, ".INBOX")
                    try:
                        # rename mailbox
                        self.listener.setuid(0)
                        shutil.move(old_maildir, new_maildir)
                    except Exception:
                        self.log_e("Failed to move mail home (of '%s') from '%s' to '%s'.\n%s" % (
                            new_mailbox, old_maildir, new_maildir, traceback.format_exc()))
                        raise
                    finally:
                        self.listener.unsetuid()
                    self.remove_global_acls(old)
                except Exception:
                    self.log_e("Could not rename/move mailbox ('%s' -> '%s').\n%s" % (old_mailbox, new_mailbox, traceback.format_exc()))
                    return
                self.log_p("Moved mailbox '%s' -> '%s'." % (old_mailbox, new_mailbox))
            else:
                # it remained a public folder
                # renaming of public folders is disabled in UDM
                # quota may have changed, update dovecot config
                self.update_public_mailbox_configuration()

            # set ACLs
            try:
                curacl = self._diff_acls(old, new)
                self.doveadm_set_mailbox_acls("%s/INBOX" % new_mailbox, curacl)
            except Exception:
                self.log_e("Error changing ACLs for mailbox '%s'." % new_mailbox)
            self.log_p("Set ACLs on '%s'." % new_mailbox)

    def get_public_location(self, ns: str) -> str:
        try:
            pub_loc = self.read_from_ext_proc_as_root(["/usr/bin/doveconf", "-h", "namespace/" + ns + "/location"], r"maildir:(\S+):INDEXPVT.*")
        except Exception:
            self.log_e("Failed to get location of public folder '%s' from Dovecot configuration.\n%s" % (ns, traceback.format_exc()))
            raise
        return pub_loc

    def create_public_folder(self, folder_name: str) -> str:
        try:
            user, group = self.get_dovecot_user()
            pub_loc = self.get_public_location(folder_name)
            path = os.path.join(pub_loc, ".INBOX")
            self.mkdir_p(pub_loc)
            self.read_from_ext_proc_as_root(["/usr/bin/maildirmake.dovecot", path, "%s:%s" % (user, group)])
            self.listener.setuid(0)
        except Exception:
            self.log_e("Failed to create maildir '%s'." % folder_name)
            raise
        finally:
            self.listener.unsetuid()
        return path

    def read_from_ext_proc_as_root(self, cmd, regexp=None, stdin=None, stdout=subprocess.PIPE, stderr=None, stdin_input=None):
        """
        Wrapper around Popen(), runs external command as root and return its
        output, optionally the first hit of a regexp. May raise an exception.

        :param cmd: list: with executable path as first item
        :param regexp: string: regexp for re.findall()
        :return: string
        """
        try:
            self.listener.setuid(0)
            cmd_proc = subprocess.Popen(cmd, stdin=stdin, stdout=stdout, stderr=stderr)
            cmd_out, cmd_err = cmd_proc.communicate(input=stdin_input and stdin_input.encode('UTF-8'))
            cmd_exit = cmd_proc.wait()
            if cmd_out and not cmd_err and cmd_exit == 0:
                if regexp:
                    res = re.findall(regexp, cmd_out.decode('UTF-8'))
                    return res[0]
                else:
                    return cmd_out.decode('UTF-8').rstrip()
        finally:
            self.listener.unsetuid()

    def doveadm_set_mailbox_acls(self, mailbox: str, acls: list[str]) -> None:
        for acl in acls:
            identifier, right = self._split_udm_imap_acl_doveadm(acl)
            if right == "none":
                cmd = ["/usr/bin/doveadm", "acl", "delete", "-u", custom_username("Administrator"), mailbox, identifier]
            else:
                cmd = ["/usr/bin/doveadm", "acl", "set", "-u", custom_username("Administrator"), mailbox, identifier]
                cmd.extend(dovecot_acls[right][1])
            try:
                self.read_from_ext_proc_as_root(cmd)
            except Exception:
                self.log_e("Failed to set ACL using doveadm using command '%s'." % cmd)
                raise

    def imap_set_mailbox_acls(self, mb_owner: str, mailbox: str, acls: list[str]) -> None:
        master_name, master_pw = self.get_masteruser_credentials()
        imap = None
        try:
            imap = imaplib.IMAP4("localhost")
            imap.login("%s*%s" % (mb_owner, master_name), master_pw)
            for acl in acls:
                identifier, right = self._split_udm_imap_acl_imap(acl)
                if right == "none":
                    imap.deleteacl(mailbox, identifier)
                else:
                    # Bug #53111: escape double quotes within identifier, then put the string between
                    # double quotes to prevent problems with e.g. whitespace (e.g. group 'Domain Users').
                    imap.setacl(mailbox, '"{}"'.format(identifier.replace('"', r'\"')), dovecot_acls[right][0])
        except Exception:
            self.log_e("Failed to set ACLs '%s' on mailbox '%s' for '%s'.\n%s" % (acls, mailbox, mb_owner, traceback.format_exc()))
            raise
        finally:
            if imap:
                imap.logout()

    def update_public_mailbox_configuration(self, delete_only: str | None = None) -> None:
        """
        Cache public folders and their quota into a UCRV.

        :param delete_only: if True removes only entry 'delete_only', else recreates from scratch.
        :return: None
        """
        # TODO: create distinct configurations for each server (honor univentionMailHomeServer)

        # When deleting, remove only one entry, so in the case of multi-remove
        # subsequent code can still access the remaining namespace configuration.
        # In any other case (add/modify) recreate from scratch to ensure
        # consistency with the LDAP.
        if delete_only:
            try:
                self.listener.setuid(0)
                old_info = self.listener.configRegistry.get("mail/dovecot/internal/sharedfolders", "").split()
                emails_quota = [info for info in old_info if not info.startswith(delete_only + ":")]
            except Exception:
                self.log_e("update_public_mailbox_configuration(): Failed to update public mailbox configuration:\n%s" % traceback.format_exc())
                raise
            finally:
                self.listener.unsetuid()
        else:
            public_folders: list[Any] = []
            for module in self.modules:
                try:
                    public_folders.extend(self.get_udm_infos(module, "(!(mailPrimaryAddress=*))"))
                except Exception:
                    self.log_e("update_public_mailbox_configuration(): Failed to update public mailbox configuration:\n%s" % traceback.format_exc())
                    raise
                finally:
                    self.listener.unsetuid()
            emails_quota = [
                "%s@%s:%s" % (
                    pf["name"] or pf.dn.split("@")[0].split("=")[1],
                    pf["mailDomain"],
                    pf.get("mailQuota", 0),
                )
                for pf in public_folders
            ]
        try:
            self.listener.setuid(0)
            handler_set(["mail/dovecot/internal/sharedfolders=%s" % " ".join(emails_quota)])
            self.read_from_ext_proc_as_root(["/usr/bin/doveadm", "reload"])
        except Exception:
            self.log_e("update_public_mailbox_configuration(): Failed to update public mailbox configuration:\n%s" % traceback.format_exc())
            raise
        finally:
            self.listener.unsetuid()
        self.log_p("Updated shared mailbox configuration.")

    def unsubscribe_from_mailbox(self, users: list[str], mailbox: str) -> None:
        for user in users:
            try:
                self.read_from_ext_proc_as_root(["/usr/bin/doveadm", "mailbox", "unsubscribe", "-u", user, mailbox])
            except Exception:
                self.log_e("Failed to unsubscribe user '%s' from mailbox '%s'." % (user, mailbox))

    def get_udm_infos(self, udm_module: Any, udm_filter: str) -> list[Any]:
        try:
            self.listener.setuid(0)
            univention.admin.modules.update()
            lo, _po = getMachineConnection()
            mod = univention.admin.modules.get(udm_module)
            return mod.lookup(None, lo, udm_filter)
        except Exception:
            self.log_e("get_udm_infos(%s, %s): Failed to retrieve UDM info:\n%s" % (udm_module, udm_filter, traceback.format_exc()))
            raise
        finally:
            self.listener.unsetuid()

    def _diff_acls(self, old: dict[str, list[bytes]], new: dict[str, list[bytes]]) -> list[str]:
        acl_diff = {}
        # find new ACLs
        for acl in new.get(self.acl_key, []):
            acl = acl.decode('UTF-8')
            right = acl.split()[-1]
            identifier = " ".join(acl.split()[:-1])
            acl_diff[identifier] = right
        # remove old ACLs
        for acl in old.get(self.acl_key, []):
            acl = acl.decode('UTF-8')
            identifier = " ".join(acl.split()[:-1])
            if identifier not in acl_diff:
                acl_diff[identifier] = "none"
        return [" ".join(x) for x in acl_diff.items()]

    @staticmethod
    def _split_udm_imap_acl_doveadm(udm_imap_acl: str) -> tuple[str, str]:
        right = udm_imap_acl.split()[-1]
        identifier = " ".join(udm_imap_acl.split()[:-1])
        if "@" in identifier or identifier == "dovecotadmin":
            identifier = "user=" + identifier
        elif identifier in ["anyone", "authenticated"]:
            pass
        else:
            identifier = "group=" + identifier
        return identifier, right

    @staticmethod
    def _split_udm_imap_acl_imap(udm_imap_acl: str) -> tuple[str, str]:
        identifier, right = udm_imap_acl.rsplit(None, 1)
        if "@" in identifier or identifier in ["anyone", "authenticated", "dovecotadmin"]:
            pass
        else:
            # group
            identifier = f'${identifier}'
        return identifier, right

    def add_global_acls(self, new: dict[str, list[bytes]]) -> None:
        new_mailbox = 'shared/{}'.format(new["mailPrimaryAddress"][0].decode('ASCII'))
        acls = new.get(self.acl_key, [])
        folder_acls = []
        for acl in acls:
            acl = acl.decode('UTF-8')
            identifier, right = self._split_udm_imap_acl_doveadm(acl)
            folder_acls.append(DovecotFolderAclEntry(new_mailbox, identifier, dovecot_acls[right][0]))
        self.global_acls.add_acls(folder_acls)

    def remove_global_acls(self, old: dict[str, list[bytes]]) -> None:
        old_mailbox = 'shared/{}'.format(old["mailPrimaryAddress"][0].decode('ASCII'))
        self.global_acls.remove_acls(old_mailbox)
