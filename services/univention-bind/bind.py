#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2001-2025 Univention GmbH
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

"""
Univention Bind listener script

During the update period, only create the configuration snippets for named and
the proxy.
During the quiet period check the cache directory (is-state) against the
configuration directory (should-state) and reload/restart as appropriate.
"""

import errno
import grp
import os
import signal
import subprocess
import time
from urllib.parse import quote

import univention.debug as ud  # pylint: disable-msg=E0611

import listener


description = 'Update BIND zones'
filter = '(&(objectClass=dNSZone)(sOARecord=*)(zoneName=*))'

NAMED_CONF_FILE = "/etc/bind/univention.conf"
NAMED_CONF_DIR = "/etc/bind/univention.conf.d"
PROXY_CONF_FILE = "/etc/bind/univention.conf.proxy"
NAMED_CACHE_DIR = "/var/cache/bind"
PROXY_CACHE_DIR = "/var/cache/univention-bind-proxy"
RNDC_BIN = "/usr/sbin/rndc"

SIGNAL = {getattr(signal, _): _ for _ in dir(signal) if _.startswith('SIG') and not _.startswith('SIG_')}

__zone_created_or_removed = False


class InvalidZone(Exception):
    pass


class BaseDirRestriction(InvalidZone):
    pass


def prerun() -> None:
    """Called before busy period."""
    listener.configRegistry.load()


def chgrp_bind(filename: str) -> None:
    try:
        bind_gid = grp.getgrnam("bind").gr_gid
    except KeyError:
        ud.debug(ud.LISTENER, ud.WARN, 'Failed to change grp to bind for %s. gid for bind not found' % filename)
        return

    os.chown(filename, 0, bind_gid)


def safe_path_join(basedir: str, filename: str) -> str:
    path = os.path.join(basedir, filename)
    if not os.path.abspath(path).startswith(basedir):
        raise BaseDirRestriction('basedir manipulation: %s' % (filename,))
    return path


def validate_zonename(zonename: str) -> None:
    """
    >>> validate_zonename('foo')
    >>> validate_zonename('foo.bar')
    >>> validate_zonename('foo.zone')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    InvalidZone: ...
    >>> validate_zonename('foo.proxy')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    InvalidZone: ...
    >>> validate_zonename('.')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    InvalidZone: ...
    >>> validate_zonename('..')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    InvalidZone: ...
    >>> validate_zonename('fo..o')  # doctest: +IGNORE_EXCEPTION_DETAIL
    Traceback (most recent call last):
    ...
    InvalidZone: ...
    """
    if not zonename:
        raise InvalidZone('empty zonename not allowed')
    if set(zonename) & set('\x00/' + ''.join(map(chr, range(0x1F + 1)))):
        raise InvalidZone('zone name %r contains invalid characters' % (zonename,))
    if zonename.endswith(('.zone', '.proxy')):
        raise InvalidZone('.zone or .proxy TLD are not supported.')
    if '..' in zonename or zonename == '.':
        raise InvalidZone('zone name must not be ".", ".." or contain "..".')
    if zonename in ('0.in-addr.arpa', '127.in-addr.arpa', '255.in-addr.arpa'):
        raise InvalidZone('zone must not be 0, 127, 255.')


def _quote_config_parameter(arg: str) -> str:
    return arg.replace('\\', '\\\\').replace('"', '\\"')


def handler(dn: str, new: dict[str, list[bytes]], old: dict[str, list[bytes]]) -> None:
    """Handle LDAP changes."""
    base = listener.configRegistry.get('dns/ldap/base')
    if base and not dn.endswith(base):
        return

    listener.setuid(0)
    try:
        if new and not old:
            # Add
            _new_zone(listener.configRegistry, new['zoneName'][0].decode('UTF-8'), dn)
        elif old and not new:
            # Remove
            _remove_zone(old['zoneName'][0].decode('UTF-8'))
        if new.get('zoneName'):
            # Change
            # Create an empty file to trigger the postrun()
            zonename = new['zoneName'][0].decode('UTF-8')
            validate_zonename(zonename)
            zonefile = safe_path_join(PROXY_CACHE_DIR, "%s.zone" % (zonename,))
            proxy_cache = open(zonefile, 'w')
            proxy_cache.close()
            os.chmod(zonefile, 0o640)
            chgrp_bind(zonefile)
    except InvalidZone as exc:
        ud.debug(ud.LISTENER, ud.ERROR, '%s is invalid: %s' % (dn, exc))
    finally:
        listener.unsetuid()


def _ldap_auth_string(ucr: dict[str, str]) -> str:
    """Build extended LDAP query URI part containing bind credentials."""
    account = ucr.get('bind/binddn', ucr['ldap/hostdn'])

    pwdfile = ucr.get('bind/bindpw', '/etc/machine.secret')
    with open(pwdfile) as fd:
        return '????!bindname=%s,!x-bindpw=%s,x-tls' % (quote(account), quote(fd.readline().rstrip()))


def _new_zone(ucr: dict[str, str], zonename: str, dn: str) -> None:
    """Handle addition of zone."""
    ud.debug(ud.LISTENER, ud.INFO, 'DNS: Creating zone %s' % (zonename,))
    if not os.path.exists(NAMED_CONF_DIR):
        os.mkdir(NAMED_CONF_DIR)
        os.chmod(NAMED_CONF_DIR, 0o755)

    validate_zonename(zonename)
    zonefile = safe_path_join(NAMED_CONF_DIR, zonename)

    # Create empty file and restrict permission
    named_zone = open(zonefile, 'w')
    named_zone.close()
    os.chmod(zonefile, 0o640)
    chgrp_bind(zonefile)

    # Now fill zone file
    ldap_uri = "ldap://%s:%s/%s%s" % (
        ucr.get('bind/ldap/server/ip', '127.0.0.1'),
        ucr.get('ldap/server/port', '7389'),
        dn,
        _ldap_auth_string(ucr),
    )
    named_zone = open(zonefile, 'w+')
    named_zone.write('zone "%s" {\n' % (_quote_config_parameter(zonename),))
    named_zone.write('\ttype master;\n')
    named_zone.write('\tnotify yes;\n')
    named_zone.write('\tdatabase "ldap %s 172800";\n' % (_quote_config_parameter(ldap_uri),))
    named_zone.write('};\n')
    named_zone.close()

    # Create proxy configuration file
    proxy_file = safe_path_join(NAMED_CONF_DIR, zonename + '.proxy')
    proxy_zone = open(proxy_file, 'w')
    proxy_zone.write('zone "%s" {\n' % (_quote_config_parameter(zonename),))
    proxy_zone.write('\ttype slave;\n')
    proxy_zone.write('\tfile "%s.zone";\n' % (_quote_config_parameter(zonename),))
    proxy_zone.write('\tmasters port 7777 { 127.0.0.1; };\n')
    proxy_zone.write('};\n')
    proxy_zone.close()
    os.chmod(proxy_file, 0o640)
    chgrp_bind(proxy_file)

    global __zone_created_or_removed
    __zone_created_or_removed = True


def _remove_zone(zonename: str) -> None:
    """Handle removal of zone."""
    ud.debug(ud.LISTENER, ud.INFO, 'DNS: Removing zone %s' % (zonename,))
    validate_zonename(zonename)
    zonefile = safe_path_join(NAMED_CONF_DIR, zonename)
    cached_zonefile = safe_path_join(NAMED_CACHE_DIR, zonename + '.zone')
    # Remove zone file
    if os.path.exists(zonefile):
        os.unlink(zonefile)
    # Remove proxy configuration file
    if os.path.exists(zonefile + '.proxy'):
        os.unlink(zonefile + '.proxy')
    # Remove cached zone file
    if os.path.exists(cached_zonefile):
        os.unlink(cached_zonefile)
    global __zone_created_or_removed
    __zone_created_or_removed = True


def clean() -> None:
    """Reset listener state."""
    listener.setuid(0)
    try:
        if os.path.exists(NAMED_CONF_FILE):
            os.unlink(NAMED_CONF_FILE)
        open(NAMED_CONF_FILE, 'w').close()

        if os.path.isdir(NAMED_CONF_DIR):
            for f in os.listdir(NAMED_CONF_DIR):
                os.unlink(os.path.join(NAMED_CONF_DIR, f))
            os.rmdir(NAMED_CONF_DIR)
    finally:
        listener.unsetuid()


def _reload(zones: list[str], restart: bool = False, dns_backend: str = 'ldap') -> dict[int, list[str]]:
    """Force reload of zones; might restart daemon; returns pids."""
    pids = {}
    # Try to only reload the zones if rndc is available
    if os.path.exists(RNDC_BIN):
        if dns_backend == 'ldap':
            if zones:
                for zone in zones:
                    ud.debug(ud.LISTENER, ud.INFO, 'DNS: Reloading zone %s' % (zone,))
                    cmd = ['rndc', '-p', '55555', 'reload', zone]
                    pid = os.spawnv(os.P_NOWAIT, RNDC_BIN, cmd)  # noqa: S606
                    pids[pid] = cmd
                    cmd = ['rndc', '-p', '953', 'reload', zone]
                    pid = os.spawnv(os.P_NOWAIT, RNDC_BIN, cmd)  # noqa: S606
                    pids[pid] = cmd
        elif dns_backend == 'samba4':
            cmd = [RNDC_BIN, '-p', '953', 'reload']
            p = subprocess.Popen(cmd)
            if p.wait() != 0:
                restart = True
    else:
        restart = True
    # Fall back to restart, which will temporarily interrupt the service
    if restart:
        ud.debug(ud.LISTENER, ud.INFO, 'DNS: Restarting BIND')
        cmd = ['service', 'named', 'restart']
        pid = os.spawnv(os.P_NOWAIT, '/usr/sbin/service', cmd)  # noqa: S606
        pids[pid] = cmd
    return pids


def _wait_children(pids: dict[int, list[str]], timeout: float = 15) -> None:
    """Wait for child termination."""
    # Wait max 15 seconds for forked children
    timeout += time.time()
    while pids:
        try:
            pid, status = os.waitpid(0, os.WNOHANG)  # non-blocking
        except OSError as ex:
            if ex.errno == errno.ECHILD:
                break  # no more own children
            else:
                ud.debug(ud.LISTENER, ud.WARN, 'DNS: Unexpected error: %s' % (ex,))
        else:
            if pid:  # only when waitpid() found one child
                # Ignore unexpected child from other listener modules (Bug #21363)
                cmd = pids.pop(pid, '')
                if os.WIFSIGNALED(status):
                    sig = os.WTERMSIG(status)
                    sig = SIGNAL.get(sig, sig)
                    ud.debug(ud.LISTENER, ud.WARN, 'DNS: %d="%s" exited by signal %s' % (pid, ' '.join(cmd), sig))
                elif os.WIFEXITED(status):
                    ret = os.WEXITSTATUS(status)
                    if ret:
                        ud.debug(ud.LISTENER, ud.WARN, 'DNS: %d="%s" exited with %d' % (pid, ' '.join(cmd), ret))
                else:
                    ud.debug(ud.LISTENER, ud.WARN, 'DNS: %d="%s" exited status %d' % (pid, ' '.join(cmd), status))
                continue

        if time.time() > timeout:
            ud.debug(ud.LISTENER, ud.WARN, 'DNS: Pending children: %s' % (' '.join([str(_pid) for _pid in pids]),))
            break
        time.sleep(1)


def _kill_children(pids: dict[int, list[str]], timeout: float = 5) -> None:
    """Kill children."""
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError as ex:
            if ex.errno != errno.ESRCH:
                ud.debug(ud.LISTENER, ud.WARN, 'DNS: Unexpected error: %s' % (ex,))
    _wait_children(pids, timeout)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError as ex:
            if ex.errno != errno.ESRCH:
                ud.debug(ud.LISTENER, ud.WARN, 'DNS: Unexpected error: %s' % (ex,))
    _wait_children(pids, timeout)


def postrun() -> None:
    """Run pending updates."""
    global __zone_created_or_removed

    # Reload UCR
    listener.configRegistry.load()

    listener.setuid(0)
    try:
        # Re-create named and proxy inclusion file
        named_conf = open(NAMED_CONF_FILE, 'w')
        proxy_conf = open(PROXY_CONF_FILE, 'w')
        if os.path.isdir(NAMED_CONF_DIR):
            for f in os.listdir(NAMED_CONF_DIR):
                if f.startswith("."):
                    continue
                elif f.endswith(".proxy"):
                    proxy_conf.write('include "%s";\n' % _quote_config_parameter(os.path.join(NAMED_CONF_DIR, f)))
                elif not f.endswith(("~", ".bak")):
                    named_conf.write('include "%s";\n' % _quote_config_parameter(os.path.join(NAMED_CONF_DIR, f)))
        named_conf.close()
        proxy_conf.close()

        os.chmod(NAMED_CONF_FILE, 0o644)
        os.chmod(PROXY_CONF_FILE, 0o644)

        # Restart is needed when new zones are added or old zones removed.
        restart = False
        do_reload = True
        zones = []

        dns_backend = listener.configRegistry.get('dns/backend')
        if dns_backend == 'samba4':
            if not __zone_created_or_removed:
                do_reload = False
            else:  # reset flag and continue with reload
                __zone_created_or_removed = False
        elif dns_backend == 'ldap':
            for filename in os.listdir(PROXY_CACHE_DIR):
                os.remove(os.path.join(PROXY_CACHE_DIR, filename))
                if not os.path.exists(os.path.join(NAMED_CACHE_DIR, filename)):
                    ud.debug(ud.LISTENER, ud.PROCESS, 'DNS: %s does not exist. Triggering a named restart.' % (os.path.join(NAMED_CACHE_DIR, filename)))
                    restart = True
                elif filename.endswith('.zone'):
                    zone = filename[:-len('.zone')]
                    zones.append(zone)
            if zones:
                ud.debug(ud.LISTENER, ud.INFO, 'DNS: Zones: %s' % (zones,))
        elif dns_backend == 'none':
            do_reload = False

        if do_reload:
            ud.debug(ud.LISTENER, ud.INFO, 'DNS: Doing reload')
        else:
            ud.debug(ud.LISTENER, ud.INFO, 'DNS: Skip zone reload')
            return

        pids = _reload(zones, restart, dns_backend)
        _wait_children(pids)
        _kill_children(pids)
    except InvalidZone as exc:
        ud.debug(ud.LISTENER, ud.ERROR, 'postrun: invalid: %s' % (exc,))
    finally:
        listener.unsetuid()
