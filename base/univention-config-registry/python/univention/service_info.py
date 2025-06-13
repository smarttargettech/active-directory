#
# Univention Configuration Registry
#  Service information: read information about registered Config Registry
#  variables
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2007-2025 Univention GmbH
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

import os
import shlex
import subprocess
from collections.abc import Iterable, Iterator, Sequence
from logging import getLogger
from typing import Any

import univention.info_tools as uit


class ServiceError(Exception):
    """Error when starting, stopping or restarting a service."""


class Service(uit.LocalizedDictionary):
    """Description for a system service."""

    REQUIRED = frozenset(('description', 'programs'))
    OPTIONAL = frozenset(('start_type', 'systemd', 'icon', 'name', 'init_script'))
    KNOWN = REQUIRED | OPTIONAL

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        uit.LocalizedDictionary.__init__(self, *args, **kwargs)
        self.running = False

    def __repr__(self) -> str:
        return '%s(%s)' % (
            self.__class__.__name__,
            dict.__repr__(self),
        )

    def check(self) -> list[str]:
        """Check service entry for validity, returning list of incomplete entries."""
        incomplete = [key for key in self.REQUIRED if not self.get(key, None)]
        unknown = [key for key in self.keys() if key.lower() not in self.KNOWN]
        return incomplete + unknown

    def _update_status(self) -> None:
        for prog in self['programs'].split(','):
            prog = prog.strip()
            if prog and not pidof(prog):
                self.running = False
                break
        else:
            self.running = True

    def start(self) -> bool:
        """Start the service."""
        return self._change_state('start')

    def stop(self) -> bool:
        """Stop the service."""
        return self._change_state('stop')

    def restart(self) -> bool:
        """Restart the service."""
        return self._change_state('restart')

    def status(self):
        """Get status of the service."""
        try:
            return self.__change_state('status')[1]
        except OSError:
            return ''

    def _change_state(self, action: str) -> bool:
        rc, output = self.__change_state(action)
        if rc:
            raise ServiceError(self.status() or output)
        return True

    def __change_state(self, action: str) -> tuple[int, str]:
        if self.get('init_script'):
            # samba currently must not be started via systemd
            return self._exec(('/etc/init.d/%s' % (self['init_script'],), action))

        service_name = self._service_name()
        return self._exec(('/usr/sbin/service', service_name, action))

    def _service_name(self) -> str:
        service_name = self.get('systemd') or self['name']
        if service_name.endswith('.service'):
            service_name = service_name.rsplit('.', 1)[0]
        return service_name

    def _exec(self, args: Sequence[str]) -> tuple[int, str]:
        process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, close_fds=True)
        output = process.communicate()[0]
        return process.returncode, output.decode('utf-8', 'replace').strip()


def pidof(name: str, docker: int | str = '/var/run/docker.pid') -> list[int]:
    """
    Return list of process IDs matching name.

    :param name: Procress name.
    :param docker: File name containing process ID of docker process.

    >>> import os,sys;os.getpid() in list(pidof(os.path.realpath(sys.executable))) + list(pidof(sys.executable)) + list(pidof(sys.argv[0]))
    True
    """
    result: set[int] = set()
    log = getLogger(__name__)

    children: dict[int | str, list[int]] = {}
    if isinstance(docker, str):
        try:
            with open(docker) as stream:
                docker = int(stream.read(), 10)
            log.info('Found docker.pid=%d', docker)
        except (OSError, ValueError) as ex:
            log.info('No docker found: %s', ex)

    cmd = shlex.split(name)
    for proc in os.listdir('/proc'):
        try:
            pid = int(proc, 10)
        except ValueError:
            continue
        cmdline = os.path.join('/proc', proc, 'cmdline')
        try:
            with open(cmdline, 'rb') as fd:
                commandline = fd.read().rstrip(b'\x00').decode('UTF-8', 'replace')
            link = os.readlink(os.path.join('/proc', proc, 'exe'))
        except OSError:
            continue
        # kernel thread
        if not commandline:
            continue

        if docker:
            stat = os.path.join('/proc', proc, 'stat')
            status = None
            try:
                with open(stat, 'rb') as fd:
                    status = fd.readline()
                ppid = int(status[status.rfind(b')') + 2:].split()[1], 10)
                children.setdefault(ppid, []).append(pid)
            except (OSError, ValueError) as ex:
                log.error('Failed getting parent: %s: %r', ex, status)

        def _running(cmd: list[str], link: str, commandline: str) -> Iterator[bool]:
            yield cmd == [link]
            args = commandline.split('\x00') if '\x00' in commandline else shlex.split(commandline)
            yield len(cmd) == 1 and cmd[0] in args  # FIXME: it detects "vim /usr/sbin/service" as running process!
            yield len(cmd) > 1 and all(a == c for a, c in zip(args, cmd))
        if any(_running(cmd, link, commandline)):
            log.info('found %d: %r', pid, commandline)
            result.add(pid)

    if docker:
        remove = children.pop(docker, [])
        while remove:
            pid = remove.pop()
            log.debug('Removing docker child %s', pid)
            result.discard(pid)
            remove += children.pop(pid, [])

    return list(result)


class ServiceInfo:
    BASE_DIR = '/etc/univention/service.info'
    SERVICES = 'services'
    CUSTOMIZED = '_customized'
    FILE_SUFFIX = '.cfg'

    def __init__(self, install_mode: bool = False) -> None:
        self.services: dict = {}
        if not install_mode:
            self.__load_services()
            self.update_services()

    def update_services(self) -> None:
        """Update the run state of all services."""
        for serv in self.services.values():
            serv._update_status()

    def check_services(self) -> dict[str, list[str]]:
        """
        Check service descriptions for completeness.

        :returns: dictionary of incomplete service descriptions.
        """
        incomplete: dict[str, list[str]] = {}
        for name, srv in self.services.items():
            miss = srv.check()
            if miss:
                incomplete[name] = miss
        return incomplete

    def write_customized(self) -> bool:
        """Save service cusomization."""
        filename = os.path.join(ServiceInfo.BASE_DIR, ServiceInfo.SERVICES, ServiceInfo.CUSTOMIZED)
        try:
            with open(filename, 'w') as fd:
                cfg = uit.UnicodeConfig()
                for name, srv in self.services.items():
                    cfg.add_section(name)
                    for key in srv.keys():
                        items = srv.normalize(key)
                        for item, value in items.items():
                            cfg.set(name, item, value)

                cfg.write(fd)

                return True
        except OSError:
            return False

    def read_services(self, filename: str | None = None, package: str | None = None, override: bool = False) -> None:
        """
        Read start/stop levels of services.

        :param filename: Explicit filename for loading.
        :param package: Explicit package name.
        :param override: `True` to overwrite already loaded descriptions.
        :raises AttributeError: if neither `filename` nor `package` are given.
        """
        if not filename:
            if not package:
                raise AttributeError("neither 'filename' nor 'package' is specified")
            filename = os.path.join(ServiceInfo.BASE_DIR, ServiceInfo.SERVICES, package + ServiceInfo.FILE_SUFFIX)
        cfg = uit.UnicodeConfig()
        cfg.read(filename)
        for sec in cfg.sections():
            # service already known?
            if not override and sec in self.services:
                continue
            srv = Service()
            srv['name'] = sec
            for name, value in cfg.items(sec):
                srv[name] = value
            for path in srv.get('programs', '').split(','):
                # "programs" defines the "/proc/self/cmdline" of the service,
                # not the executable, therefore we test for a leading "/":
                # check if it is a real file    split to remove parameters
                if path.startswith('/') and not os.path.exists(path.split(' ', 1)[0]):
                    break  # ==> do not execute else
            else:
                self.services[sec] = srv

    def __load_services(self) -> None:
        """Load definition of all defined services."""
        path = os.path.join(ServiceInfo.BASE_DIR, ServiceInfo.SERVICES)
        for entry in os.listdir(path):
            # customized service descrptions are read afterwards
            if entry == ServiceInfo.CUSTOMIZED:
                continue
            cfgfile = os.path.join(path, entry)
            if os.path.isfile(cfgfile) and cfgfile.endswith(ServiceInfo.FILE_SUFFIX):
                self.read_services(cfgfile)
        # read modified/added service descriptions
        self.read_customized()

    def read_customized(self) -> None:
        """Read service cusomization."""
        custom = os.path.join(ServiceInfo.BASE_DIR, ServiceInfo.SERVICES, ServiceInfo.CUSTOMIZED)
        self.read_services(custom, override=True)

    def get_services(self) -> Iterable[str]:
        """
        Return a list fo service names.

        :returns: List of service names.
        """
        return self.services.keys()

    def get_service(self, name: str) -> Service | None:
        """
        Return the service object associated with the given name.

        :param name: Service name.
        :returns: description object or `None`.
        """
        return self.services.get(name, None)

    def add_service(self, name: str, service: Service) -> None:
        """
        Add a new service object or overrides an old entry.

        :param name: Service name.
        :param service: :py:class:`Service` instance.
        """
        if not service.check():
            self.services[name] = service


if __name__ == '__main__':
    import doctest
    doctest.testmod()
