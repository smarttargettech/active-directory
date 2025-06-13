#!/usr/bin/python3
#
# Univention App Center
#  Utility functions
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

import http.client
import ipaddress
import os
import os.path
import re
import shutil
import socket
import ssl
import time
import urllib.request
from collections import OrderedDict
from configparser import ParsingError, RawConfigParser
from hashlib import md5, sha256
from locale import getlocale
from shlex import quote
from subprocess import PIPE, STDOUT, Popen, list2cmdline
from threading import Thread
from typing import TYPE_CHECKING, Any, TypeVar, overload
from urllib.parse import urlencode
from uuid import uuid4

from ldap.filter import filter_format

from univention.appcenter.log import get_base_logger
from univention.appcenter.ucr import ucr_get, ucr_keys
from univention.config_registry import interfaces
from univention.config_registry.misc import key_shell_escape
from univention.lib.i18n import Translation


if TYPE_CHECKING:
    from collections.abc import Container, Iterable, Mapping, Sequence
    from logging import Logger

    from univention.appcenter.app import App


_ConfigParser = TypeVar("_ConfigParser", bound=RawConfigParser)
_T = TypeVar("_T")

# "global" translation for univention-appcenter
# also provides translation for univention-appcenter-docker etc
_ = Translation('univention-appcenter').translate


utils_logger = get_base_logger().getChild('utils')


@overload
def read_ini_file(filename: str) -> RawConfigParser:
    pass


@overload
def read_ini_file(filename: str, parser_class: type[_ConfigParser]) -> _ConfigParser:
    pass


def read_ini_file(filename, parser_class=RawConfigParser):
    parser = parser_class()
    try:
        with open(filename) as f:
            parser.read_file(f)
    except TypeError:
        pass
    except OSError:
        pass
    except ParsingError as exc:
        utils_logger.warning('Could not parse %s' % filename)
        utils_logger.warning(str(exc))
    else:
        return parser
    # in case of error return empty parser
    return parser_class()


def docker_bridge_network_conflict() -> bool:
    docker0_net = ipaddress.IPv4Network('%s' % (ucr_get('docker/daemon/default/opts/bip', '172.17.42.1/16'),), False)
    for _name, iface in interfaces.Interfaces().ipv4_interfaces:
        if 'address' in iface and 'netmask' in iface:
            my_net = ipaddress.IPv4Network('%s/%s' % (iface['address'], iface['netmask']), False)
            if my_net.overlaps(docker0_net):
                return True
    return False


def app_is_running(app: App | str) -> bool | None:
    from univention.appcenter.app_cache import Apps
    if isinstance(app, str):
        app = Apps().find(app)
    if app:
        if not app.docker:
            return False
        if not app.is_installed():
            return False
        try:
            from univention.appcenter.docker import Docker
        except ImportError:
            return None
        else:
            docker = Docker(app)
            return docker.is_running()
    else:
        return None


def docker_is_running() -> bool:
    return call_process(['invoke-rc.d', 'docker', 'status']).returncode == 0


def app_ports() -> list[tuple[str, int, int]]:
    """
    Returns a list for ports of an App:
    [(app_id, container_port, host_port), ...]
    """
    ret = []
    for key in ucr_keys():
        match = re.match(r'^appcenter/apps/(.*)/ports/(\d*)', key)
        if match:
            try:
                ret.append((match.groups()[0], int(match.groups()[1]), int(ucr_get(key))))
            except ValueError:
                pass
    return sorted(ret)


def app_ports_with_protocol() -> list[tuple[str, int, int, str]]:
    """
    Returns a list for ports of an App:
    [(app_id, container_port, host_port, protocol), ...]
    """
    ret = []
    for app_id, container_port, host_port in app_ports():
        protocol = ucr_get('appcenter/apps/%s/ports/%s/protocol' % (app_id, container_port), 'tcp')
        for proto in protocol.split(', '):
            ret.append((app_id, container_port, host_port, proto))
    return ret


class NoMorePorts(Exception):
    pass


def currently_free_port_in_range(lower_bound: int, upper_bound: int, blacklist: Container[int]) -> int:
    for port in range(lower_bound, upper_bound):
        if port in blacklist:
            continue
        s = socket.socket()
        try:
            s.bind(('', port))
        except OSError:
            pass
        else:
            s.close()
            return port
    raise NoMorePorts()


def generate_password() -> str:
    text = "%s%s" % (uuid4(), time.time())
    return get_sha256(text.encode("utf-8"))


def underscore(value: str) -> str:
    return re.sub('([a-z])([A-Z])', r'\1_\2', value).lower()


def capfirst(value: str) -> str:
    return value[0].upper() + value[1:]


def camelcase(value: str) -> str:
    return ''.join(capfirst(part) for part in value.split('_'))


def shell_safe(value: str) -> str:
    return underscore(key_shell_escape(value))


def mkdir(directory: str) -> None:
    if os.path.exists(directory):
        return
    parent, child = os.path.split(directory)
    mkdir(parent)
    if child:
        os.mkdir(directory)


def rmdir(directory: str) -> None:
    if os.path.exists(directory):
        shutil.rmtree(directory)


def call_process2(cmd: Sequence[str], logger: Logger | None = None, env: Mapping[str, str] | None = None, cwd: str | None = None) -> tuple[int, str]:
    if logger is None:
        logger = utils_logger
    # make sure we log strings only
    str_cmd = [str(x) for x in cmd]
    if cwd:
        logger.debug('Running in %s:' % cwd)
    logger.info('Running command: {}'.format(' '.join(str_cmd)))
    out = ""
    ret = 0
    try:
        p = Popen(cmd, stdout=PIPE, stderr=STDOUT, close_fds=True, env=env, cwd=cwd)
        assert p.stdout is not None
        while p.poll() is None:
            stdout = p.stdout.readline().decode('utf-8')
            if stdout:
                out += stdout
                if logger:
                    logger.info(stdout.strip())
        ret = p.returncode
    except Exception as err:
        out = str(err)
        ret = 1
    if ret:
        logger.error('Command {} failed with: {} ({})'.format(' '.join(str_cmd), out.strip(), ret))
    return ret, out


def call_process(args: Sequence[str], logger: Logger | None = None, env: Mapping[str, str] | None = None, cwd: str | None = None) -> Any:
    process = Popen(args, stdout=PIPE, stderr=PIPE, close_fds=True, env=env, cwd=cwd)
    if logger is not None:
        if cwd:
            logger.debug('Calling in %s:' % cwd)
        logger.debug('Calling %s' % ' '.join(quote(arg) for arg in args))
        remove_ansi_escape_sequence_regex = re.compile(r'\x1B\[[0-9;]*[a-zA-Z]')

        def _handle_output(out, handler):
            for line in iter(out.readline, b''):
                line = line.decode('utf-8')
                line = line.removesuffix('\n')
                line = remove_ansi_escape_sequence_regex.sub(' ', line)
                handler(line)
            out.close()

        stdout_thread = Thread(target=_handle_output, args=(process.stdout, logger.info))
        stdout_thread.daemon = True
        stdout_thread.start()
        stderr_thread = Thread(target=_handle_output, args=(process.stderr, logger.warning))
        stderr_thread.daemon = True
        stderr_thread.start()

        while stdout_thread.is_alive() or stderr_thread.is_alive():
            time.sleep(0.2)
        process.wait()
    else:
        process.communicate()
    return process


def call_process_as(user: str, args: Sequence[str], logger: Logger | None = None, env: Mapping[str, str] | None = None) -> Any:
    args = list2cmdline(args)
    args = ['/bin/su', '-', user, '-c', args]
    return call_process(args, logger, env)


def verbose_http_error(exc: Exception) -> str:
    strerror = ''
    getcode = getattr(exc, "getcode", None)
    if getcode is not None:
        code = getcode()
        if code == 404:
            url = getattr(exc, "url", None)
            strerror = _('%s could not be downloaded. This seems to be a problem with the App Center server. Please try again later.') % url
        elif code >= 500:
            strerror = _('This is a problem with the App Center server. Please try again later.')

    reason = getattr(exc, "reason", None)
    if reason is not None and isinstance(reason, ssl.SSLError):
        strerror = _('There is a problem with the certificate of the App Center server %s.') % get_server()
        strerror += ' (%s)' % (reason,)

    while reason:
        exc = reason
        reason = getattr(exc, "reason", None)

    errno = getattr(exc, "errno", None)
    if errno is not None:
        version = ucr_get('version/version')
        strerror += getattr(exc, 'strerror', '') or ''
        if errno == 1:  # gaierror(1, something like 'SSL Unknown protocol')  SSLError(1, '_ssl.c:504: error:14090086:SSL routines:ssl3_get_server_certificate:certificate verify failed')
            link_to_doc = _('https://docs.software-univention.de/manual-%s.html#ip-config:Web_proxy_for_caching_and_policy_management__virus_scan') % version
            strerror += '. ' + _('This may be a problem with the firewall or proxy of your system. You may find help at %s.') % link_to_doc
        if errno == -2:  # gaierror(-2, 'Name or service not known')
            link_to_doc = _('https://docs.software-univention.de/manual-%s.html#networks:dns') % version
            strerror += '. ' + _('This is probably due to the DNS settings of your server. You may find help at %s.') % link_to_doc

    if not strerror.strip():
        strerror = str(exc)
    if isinstance(exc, ssl.CertificateError):
        strerror = _('There is a problem with the certificate of the App Center server %s.') % get_server() + ' (%s)' % (strerror,)
    if isinstance(exc, http.client.BadStatusLine):
        strerror = _('There was a problem with the HTTP response of the server (BadStatusLine). Please try again later.')
    return strerror


class HTTPSConnection(http.client.HTTPSConnection):
    """Verified HTTP Connection, Bug #30620"""

    def __init__(self, *args, **kwargs):
        ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        ssl_context.set_alpn_protocols(['http/1.1'])
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.load_verify_locations("/etc/ssl/certs/ca-certificates.crt")
        super().__init__(*args, context=ssl_context, **kwargs)


class HTTPSHandler(urllib.request.HTTPSHandler):

    def https_open(self, req):
        return self.do_open(HTTPSConnection, req)


def urlopen(request):
    if not urlopen._opener_installed:
        handler = []
        proxy_http = ucr_get('proxy/http')
        if proxy_http:
            handler.append(urllib.request.ProxyHandler({'http': proxy_http, 'https': proxy_http}))
        handler.append(HTTPSHandler())
        opener = urllib.request.build_opener(*handler)
        urllib.request.install_opener(opener)
        urlopen._opener_installed = True
    return urllib.request.urlopen(request, timeout=60)  # noqa: S310


urlopen._opener_installed = False  # type: ignore


def get_md5(content: bytes) -> str:
    m = md5()
    if isinstance(content, str):
        content = content.encode('utf-8')
    m.update(content)
    return m.hexdigest()


def get_md5_from_file(filename: str) -> str | None:
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return get_md5(f.read())


def get_sha256(content: bytes) -> str:
    m = sha256()
    if isinstance(content, str):
        content = content.encode('utf-8')
    m.update(content)
    return m.hexdigest()


def get_sha256_from_file(filename: str) -> str | None:
    if os.path.exists(filename):
        with open(filename, 'rb') as f:
            return get_sha256(f.read())


def get_current_ram_available() -> float:
    """Returns RAM currently available in MB, excluding Swap"""
    # return (psutil.avail_phymem() + psutil.phymem_buffers() + psutil.cached_phymem()) / (1024*1024) # psutil is outdated. re-enable when methods are supported
    # implement here. see http://code.google.com/p/psutil/source/diff?spec=svn550&r=550&format=side&path=/trunk/psutil/_pslinux.py
    with open('/proc/meminfo') as f:
        splitlines = map(lambda line: line.split(), f.readlines())
        meminfo = {line[0]: int(line[1]) * 1024 for line in splitlines}  # bytes
    avail_phymem = meminfo['MemFree:']  # at least MemFree is required

    # see also http://code.google.com/p/psutil/issues/detail?id=313
    phymem_buffers = meminfo.get('Buffers:', 0)  # OpenVZ does not have Buffers, calculation still correct, see Bug #30659
    cached_phymem = meminfo.get('Cached:', 0)  # OpenVZ might not even have Cached? Don't know if calculation is still correct but it is better than raising KeyError
    return (avail_phymem + phymem_buffers + cached_phymem) / (1024 * 1024)


def get_free_disk_space() -> float:
    """Returns disk space currently free in MB"""
    docker_path = '/var/lib/docker'
    try:
        fd = os.open(docker_path, os.O_RDONLY)
        try:
            stats = os.fstatvfs(fd)
            bytes_free = stats.f_frsize * stats.f_bavail  # block size * number of free blocks
            mb_free = bytes_free * 1e-6
            return mb_free
        finally:
            os.close(fd)
    except Exception:
        utils_logger.debug('Free disk space could not be determined.')
    return 0.0


def flatten(list_of_lists: Iterable[Any]) -> list[Any]:
    # return [item for sublist in list_of_lists for item in sublist]
    # => does not work well for strings in list
    ret = []
    for sublist in list_of_lists:
        if isinstance(sublist, list | tuple):
            ret.extend(flatten(sublist))
        else:
            ret.append(sublist)
    return ret


def unique(sequence: Iterable[_T]) -> list[_T]:
    # uniquifies any list; preserves ordering
    return list(OrderedDict.fromkeys(sequence))


def get_locale() -> str | None:
    # returns currently set locale: de_AT.UTF-8 -> de
    # may return None if not set (i.e. 'C')
    locale = getlocale()[0]
    if locale:
        locale = locale.split('_', 1)[0]
    return locale


def gpg_verify(filename: str, signature: str | None = None) -> tuple[int, str]:
    if signature is None:
        signature = filename + '.gpg'
    cmd = (
        'apt-key',
        'verify',
        '--verbose',
        signature,
        filename,
    )
    p = Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, close_fds=True)
    _stdout, stderr = p.communicate()
    return (p.returncode, stderr.decode('utf-8'))


def get_local_fqdn() -> str:
    return '%s.%s' % (ucr_get('hostname'), ucr_get('domainname'))


def get_server() -> str:
    from univention.appcenter.app_cache import default_server
    return default_server()


def container_mode() -> bool:
    """returns True if this system is a container"""
    return bool(ucr_get('docker/container/uuid'))


def send_information(action: str, app: App | None = None, status: int = 200, value: str | None = None) -> None:
    app_id = app and app.id
    utils_logger.debug('send_information: action=%s app=%s value=%s status=%s' % (action, app_id, value, status))

    server = get_server()
    url = '%s/postinst' % server

    uuid = '00000000-0000-0000-0000-000000000000'
    system_uuid: str | None = '00000000-0000-0000-0000-000000000000'
    if not app or app.notify_vendor:
        uuid = ucr_get('uuid/license', uuid)
        system_uuid = ucr_get('uuid/system', system_uuid)
    if action == 'search':
        uuid = '00000000-0000-0000-0000-000000000000'
        system_uuid = None

    values = {
        'action': action,
        'status': status,
        'uuid': uuid,
        'role': ucr_get('server/role'),
    }
    if app:
        values['app'] = app.id
        values['version'] = app.version
    if value:
        values['value'] = value
    if system_uuid:
        values['system-uuid'] = system_uuid
    utils_logger.debug('tracking information: %s' % str(values))
    try:
        request_data = urlencode(values).encode('utf-8')
        request = urllib.request.Request(url, request_data)  # noqa: S310
        urlopen(request)
    except Exception as exc:
        utils_logger.info('Error sending app infos to the App Center server: %s' % exc)


def find_hosts_for_master_packages() -> list[tuple[str, bool]]:
    from univention.appcenter.udm import get_machine_connection, search_objects
    lo, pos = get_machine_connection()
    hosts = []
    for host in search_objects('computers/domaincontroller_master', lo, pos):
        hosts.append((host.info.get('fqdn'), True))
    for host in search_objects('computers/domaincontroller_backup', lo, pos):
        hosts.append((host.info.get('fqdn'), False))
    try:
        local_fqdn = '%s.%s' % (ucr_get('hostname'), ucr_get('domainname'))
        local_is_master = ucr_get('server/role') == 'domaincontroller_master'
        hosts.remove((local_fqdn, local_is_master))
    except ValueError:
        # not in list
        pass
    return hosts


def resolve_dependencies(apps: list[App], action: str) -> list[App]:
    from univention.appcenter.app_cache import Apps
    from univention.appcenter.udm import get_machine_connection
    lo, _pos = get_machine_connection()
    utils_logger.info('Resolving dependencies for %s' % ', '.join(app.id for app in apps))
    apps_with_their_dependencies = []
    depends: dict[int, list[int]] = {}
    checked = []
    apps = apps[:]
    if action == 'remove':
        # special case: do not resolve dependencies as
        # we are going to uninstall the app
        # do not removed dependant apps either: the admin may want to keep them
        # => will get an error afterwards
        # BUT: reorder the apps if needed
        original_app_ids = [_app.id for _app in apps]
        for app in apps:
            checked.append(app)
            depends[app.id] = []
            for app_id in app.required_apps:
                if app_id not in original_app_ids:
                    continue
                depends[app.id].append(app_id)
            for app_id in app.required_apps_in_domain:
                if app_id not in original_app_ids:
                    continue
                depends[app.id].append(app_id)
        apps = []
    while apps:
        app = apps.pop()
        if app in checked:
            continue
        checked.insert(0, app)
        dependencies = depends[app.id] = []
        for app_id in app.required_apps:
            required_app = Apps().find(app_id)
            if required_app is None:
                utils_logger.warning('Could not find required App %s' % app_id)
                continue
            if not required_app.is_installed():
                utils_logger.info('Adding %s to the list of Apps' % required_app.id)
                apps.append(required_app)
                dependencies.append(app_id)
        for app_id in app.required_apps_in_domain:
            required_app = Apps().find(app_id)
            if required_app is None:
                utils_logger.warning('Could not find required App %s' % app_id)
                continue
            if required_app.is_installed():
                continue
            if lo.search(filter_format('(&(univentionObjectType=appcenter/app)(univentionAppInstalledOnServer=*)(univentionAppID=%s_*))', [required_app.id])):
                continue
            utils_logger.info('Adding %s to the list of Apps' % required_app.id)
            apps.append(required_app)
            dependencies.append(app_id)
    max_loop = len(checked) ** 2
    i = 0
    while checked:
        app = checked.pop(0)
        if not depends[app.id]:
            apps_with_their_dependencies.append(app)
            for app_id, required_apps in depends.items():
                try:
                    required_apps.remove(app.id)
                except ValueError:
                    pass
        else:
            checked.append(app)
        i += 1
        if i > max_loop:
            # this should never happen unless we release apps with dependency cycles
            raise RuntimeError('Cannot resolve dependency cycle!')
    if action == 'remove':
        # another special case:
        # we need to reverse the order: the app with the dependencies needs to be
        # removed first
        apps_with_their_dependencies.reverse()
    return apps_with_their_dependencies
