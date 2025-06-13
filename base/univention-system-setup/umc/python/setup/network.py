#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2013-2025 Univention GmbH
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
Univention Management Console Module System-Setup
Network interfaces
"""

from __future__ import annotations

import ipaddress
import re
from typing import TYPE_CHECKING, Any, TypeVar

from univention.config_registry import ConfigRegistry
from univention.lib.i18n import Translation
from univention.management.console.log import MODULE
from univention.management.console.modules.setup.util import detect_interfaces


if TYPE_CHECKING:
    from collections.abc import Mapping


_TD = TypeVar("_TD", bound="Device", covariant=True)  # noqa: PLC0105

ucr = ConfigRegistry()
ucr.load()

_translation = Translation('univention-management-console-module-setup')
_ = _translation.translate

RE_INTERFACE = re.compile(r'^interfaces/(?!(?:primary|restart/auto|handler)$)([^/]+?)(_[0-9]+)?/')
RE_IPV6_ID = re.compile(r'^[a-zA-Z0-9]+\Z')
# VALID_NAME_RE = re.compile(r'^(?![.]{1,2}\Z)[^/ \t\n\r\f]{1,15}\Z')

PHYSICAL_INTERFACES = [dev['name'] for dev in detect_interfaces()]


class DeviceError(ValueError):

    def __init__(self, msg: str, device: str | None = None) -> None:
        if device is not None:
            msg = '%s: %s' % (device, msg)
        self.device = device
        ValueError.__init__(self, msg)


class IP4Set(set):

    def add(self, ip: str) -> None:
        set.add(self, ipaddress.IPv4Address('%s' % (ip,)))

    def __contains__(self, ip: object) -> bool:
        return set.__contains__(self, ipaddress.IPv4Address('%s' % (ip,)))


class IP6Set(set):

    def add(self, ip: str) -> None:
        set.add(self, ipaddress.IPv6Address('%s' % (ip,)))

    def __contains__(self, ip: object) -> bool:
        return set.__contains__(self, ipaddress.IPv6Address('%s' % (ip,)))


class Interfaces(dict[str, "Device"]):
    """All network interfaces"""

    def __init__(self) -> None:
        """Loads all network devices from UCR variables"""
        super().__init__()

        ucr.load()

        # get all available interfaces
        interfaces = {_.group(1) for _ in (RE_INTERFACE.match(key) for key in ucr) if _}
        for name in interfaces:
            device = Device(name, self)
            device.parse_ucr()
            self[device.name] = device

    def from_dict(self, interfaces: Mapping[str, str]) -> None:
        """Replaces all interfaces with the given interfaces and removes non existing interfaces"""
        ucr.load()

        # remove old devices
        to_remove = set(self.keys()) - set(interfaces.keys())
        for name in to_remove:
            device = _RemovedDevice(name, self)
            self[device.name] = device

        # append new devices
        for values in interfaces.values():
            device = Device.from_dict(values, self)
            self[device.name] = device

    def to_ucr(self) -> dict[str, str | None]:
        """Returns a UCR representation of all interfaces"""
        ucr.load()

        ucrv = {}
        for device in self.values():
            ucrv.update(device.to_ucr())

        return ucrv

    def to_dict(self) -> dict[str, dict[str, str]]:
        """Returns a dict structure of all interfaces"""
        return {device.name: device.dict for device in self.values()}

    def check_consistency(self) -> None:
        """Checks and partly enforces the consistency of all network interfaces"""
        for device in self.values():
            device.prepare_consistency()
            device.validate()

        self.check_unique_ip4_address()
        self.check_unique_ip6_address()

        # make sure at least one interface is configured with an IPv4 or IPv6 address
        if not self or not any(device.ip4 or device.ip6 or device.ip4dynamic or device.ip6dynamic for device in self.values()):
            raise DeviceError(_('There is no device configured. At least one IPv4 or IPv6 address or DHCP or SLAAC has to be specified.'))

        self.set_device_order()

    def check_unique_ip4_address(self) -> None:
        all_ip4s = IP4Set()
        for device in self.values():
            if not device.ip4dynamic:
                for address, _netmask in device.ip4:
                    # check for duplicated IP's
                    if address in all_ip4s:
                        raise DeviceError(_('Duplicated IP address: %r') % (address), device.name)
                    all_ip4s.add(address)

    def check_unique_ip6_address(self) -> None:
        all_ip6s = IP6Set()
        for device in self.values():
            if not device.ip6dynamic:
                for address, _prefix, _identifier in device.ip6:
                    # check for duplicated IP's
                    if address in all_ip6s:
                        raise DeviceError(_('Duplicated IP address: %r') % (address), device.name)
                    all_ip6s.add(address)

    def set_device_order(self) -> None:
        if not any(isinstance(device, VLAN | Bridge | Bond) for device in self.values()):
            # no VLAN, Bridge or Bond devices
            # we don't need to set the device order
            return

        devices = {device: device.subdevices for device in self.values()}

        i = 1
        while devices:
            leave = {device for device, subdevs in devices.items() if not subdevs}
            if not leave:
                if devices:
                    # cyclic dependency
                    raise DeviceError("Cyclic dependency detected: %s" % '; '.join('%s -> %s' % (dev, ', '.join([s.name for s in sd])) for dev, sd in devices.items()))
                break

            for device in leave:
                # set device order
                device.order = i
                i += 1

            devices = {device: (subdevs - leave) for device, subdevs in devices.items() if device not in leave}


class Device:
    """Abstract base class for network interfaces"""

    def __new__(cls: type[_TD], name: str, interfaces: Any) -> _TD:  # noqa: PYI019
        # make it abstract ;)
        if cls is Device:
            # detect type of interface
            device = Ethernet(name, interfaces)
            device.parse_ucr()
            cls = Ethernet  # type: ignore  # noqa: PLW0642
            if '.' in name:
                cls = VLAN  # type: ignore  # noqa: PLW0642
            elif device.options:
                if any(opt.startswith('bridge_ports') for opt in device.options):
                    cls = Bridge  # type: ignore  # noqa: PLW0642
                elif any(opt.startswith('bond-slaves') for opt in device.options):
                    cls = Bond  # type: ignore  # noqa: PLW0642
                elif any(opt.startswith('vlan-raw-device') for opt in device.options):
                    cls = VLAN  # type: ignore  # noqa: PLW0642
        return object.__new__(cls)

    @property
    def primary_ip4(self) -> tuple[str | None, str | None]:
        if self.ip4:
            return self.ip4[0]
        return (None, None)

    def __init__(self, name: str, interfaces: Interfaces) -> None:
        """
        :param name: the interface name, e.g. wlan0, eth0, br0, eth0.2, bond0

        :param interfaces: a Interfaces instance
        :type  interfaces: Interfaces
        """
        self.name = name
        self.interfaces = interfaces

        # set initial values
        self.clear()

    def clear(self) -> None:
        # array of IP4 addresses and netmask assigned to this interface
        # e.g. [('1.2.3.4', '255.255.255.0'), ('1.2.3.5', '24')]
        self.ip4: list[tuple[str, str]] = []

        # array of IPv6 addresses, prefix and identifier
        # e.g. [('::1', '64', 'default'), ('::2', '64', 'foobar')]
        self.ip6: list[tuple[str, str, str]] = []

        # flags whether this interface gets its IP addresses via DHCP or SLAAC
        self.ip4dynamic = False
        self.ip6dynamic = False

        # flag indicating that this interface should automatically start at system startup
        self.start: bool | None = None

        # type of network for this interface e.g. static, manual, dhcp
        self.type: str | None = None

        # topological ordering for interface dependency
        self.order: int | None = None

        # additional options for this interface
        self.options: list[str] = []

        # unknown UCR variables
        self._leftover: list[tuple[str, str | None]] = []

        # TODO: MAC address ?

    @property
    def subdevice_names(self) -> set[str]:
        return set()

    @property
    def subdevices(self) -> set[Device]:
        """Returns a set of subdevices of this device if there are any, leavong out not existing devices"""
        return {self.interfaces[name] for name in self.subdevice_names if name in self.interfaces}

    def prepare_consistency(self) -> None:
        self._remove_old_fallback_variables()

        self.order = None
        self.start = True
        self.type = 'manual'

        if self.ip4dynamic:
            self.type = 'dhcp'
        elif self.ip4 or self.ip6:
            self.type = 'static'

    def _remove_old_fallback_variables(self) -> None:
        # removes deprecated UCR variables from UCS <= 3.1-1... can be removed in future
        self._leftover = [
            (leftover[0], None) if leftover[0].startswith('interfaces/%s/fallback/' % (self.name,))
            else leftover for leftover in self._leftover]

    def validate(self) -> None:
        self.validate_name()
        self.validate_ip4()
        self.validate_ip6()

    def validate_name(self) -> None:
        """
        Valid interface name: max 15 characters, no slash, no space, not . or ..
        See linux/net/core/dev.c:933#dev_valid_name()
        >>> Device('eth0', {}).validate_name()
        >>> Device('0a1b2c3d4e5f_-:', {}).validate_name()
        >>> Device('', {}).validate_name()
        Traceback (most recent call last):
                ...
        DeviceError: Invalid device name: ''
        >>> Device('.', {}).validate_name()
        Traceback (most recent call last):
                ...
        DeviceError: Invalid device name: '.'
        >>> Device('..', {}).validate_name()
        Traceback (most recent call last):
                ...
        DeviceError: Invalid device name: '..'
        >>> Device(' ', {}).validate_name()
        Traceback (most recent call last):
                ...
        DeviceError: Invalid device name: ' '
        >>> Device('abcdefghijklmnop', {}).validate_name()
        Traceback (most recent call last):
                ...
        DeviceError: Invalid device name: 'abcdefghijklmnop'
        """
        if not self.name:
            pass
        elif len(self.name) >= 16:  # IFNAMSIZ
            pass
        elif self.name in ('.', '..'):
            pass
        elif any(_ == '/' or _.isspace() for _ in self.name):
            pass
        else:
            return
        raise DeviceError(_('Invalid device name: %r') % (self.name,))

    def validate_ip4(self) -> None:
        # validate IPv4
        if not self.ip4dynamic:
            for address, netmask in self.ip4:
                # validate IP address
                try:
                    int(ipaddress.IPv4Address('%s' % (address,)))
                except (ValueError, ipaddress.AddressValueError):
                    raise DeviceError(_('Invalid IPv4 address: %r') % (address), self.name)

                # validate netmask
                try:
                    ipaddress.IPv4Network('%s/%s' % (address, netmask), False)
                except (ValueError, ipaddress.NetmaskValueError, ipaddress.AddressValueError):
                    raise DeviceError(_('Invalid IPv4 netmask: %r') % (netmask), self.name)

    def validate_ip6(self) -> None:
        # validate IPv6
        if not self.ip6dynamic:
            for address, prefix, identifier in self.ip6:
                # validate IP address
                try:
                    int(ipaddress.IPv6Address('%s' % (address,)))
                except ipaddress.AddressValueError:
                    raise DeviceError(_('Invalid IPv6 address: %r') % (address), self.name)

                # validate IPv6 netmask
                try:
                    ipaddress.IPv6Network('%s/%s' % (address, prefix), False)
                except (ValueError, ipaddress.NetmaskValueError, ipaddress.AddressValueError):
                    raise DeviceError(_('Invalid IPv6 netmask: %r') % (prefix), self.name)

                # validate IPv6 identifier
                if not RE_IPV6_ID.match(identifier):
                    raise DeviceError(_('Invalid IPv6 identifier: %r') % (identifier), self.name)

            # There must be a 'default' identifier
            if self.ip6 and not any(identifier == 'default' for address, prefix, identifier in self.ip6):
                raise DeviceError(_('Missing IPv6 default identifier'), self.name)

    def limit_ip4_address(self) -> None:
        if len(self.ip4) > 1:
            # UCR can't support multiple IPv4 addresses on VLAN, Bridge and Bond interfaces; Bug #31767
            raise DeviceError(_('Multiple IPv4 addresses are not supported on this device.'), self.name)

    def check_unique_interface_usage(self) -> None:
        # make sure that used interfaces can not be used by other interfaces, too
        for device in self.interfaces.values():
            if device.name != self.name:
                for idevice in self.subdevices:
                    if idevice in device.subdevices:
                        raise DeviceError(_('Device %(device)r is already in use by %(name)r') % {'device': idevice.name, 'name': device.name}, self.name)

    def disable_ips(self) -> None:
        self.ip4 = []
        self.ip6 = []
        self.ip4dynamic = False
        self.ip6dynamic = False

    def get_options(self) -> list[str]:
        return self.options

    def parse_ucr(self) -> None:
        name = self.name
        self.clear()

        pattern = re.compile(r'^interfaces/%s(?:_[0-9]+)?/' % re.escape(name))
        vals = {key: ucr[key] for key in ucr if pattern.match(key)}

        self.start = ucr.is_true(value=vals.pop('interfaces/%s/start' % (name), None))

        self.type = vals.pop('interfaces/%s/type' % (name), None)

        order = vals.pop('interfaces/%s/order' % (name), "")
        if order.isdigit():
            self.order = int(order)

        self.network = vals.pop('interfaces/%s/network' % (name), '')
        self.broadcast = vals.pop('interfaces/%s/broadcast' % (name), '')

        address, netmask = vals.pop('interfaces/%s/address' % (name), ''), vals.pop('interfaces/%s/netmask' % (name), '24')
        if address:
            self.ip4.append((address, netmask))

        self.ip4dynamic = self.type in ('dhcp', 'dynamic')
        self.ip6dynamic = ucr.is_true(value=vals.pop('interfaces/%s/ipv6/acceptRA' % (name), None))

        for key in vals.copy():
            if re.match('^interfaces/%s/options/[0-9]+$' % re.escape(name), key):
                self.options.append(vals.pop(key))
                continue

            match = re.match('^interfaces/%s/ipv6/([^/]+)/address' % re.escape(name), key)
            if match:
                identifier = match.group(1)
                self.ip6.append((vals.pop(key), vals.pop('interfaces/%s/ipv6/%s/prefix' % (name, identifier), ''), identifier))
                continue

            match = re.match('^interfaces/(%s_[0-9]+)/address' % re.escape(name), key)
            if match:
                self.ip4.append((vals.pop(key), vals.pop('interfaces/%s/netmask' % match.group(1), '24')))
                continue

        self._leftover += vals.items()

        self.options.sort()
        self._leftover.sort()

    def to_ucr(self) -> dict[str, str | None]:
        """
        Returns a dict of UCR variables to set or unset.
        Values which are None should be unset.
        """
        name = self.name

        pattern = re.compile('^interfaces/%s(?:_[0-9]+)?/.*' % re.escape(name))
        vals: dict[str, str | None] = {key: None for key in ucr if pattern.match(key)}

        for key, val in self._leftover:
            vals[key] = val  # noqa: PERF403

        if self.start is not None:
            vals['interfaces/%s/start' % (name)] = str(bool(self.start)).lower()

        if self.type in ('static', 'manual', 'dhcp', 'dynamic', 'appliance-mode-temporary'):
            vals['interfaces/%s/type' % (name)] = self.type
        else:
            MODULE.warn('Unknown interfaces/%s/type: %r' % (self.name, self.type))

        if isinstance(self.order, int):
            vals['interfaces/%s/order' % (name)] = str(self.order)

        vals['interfaces/%s/network' % (name)] = None
        vals['interfaces/%s/broadcast' % (name)] = None

        if not self.ip4dynamic:
            if self.ip4:
                address, netmask = self.ip4[0]
                vals['interfaces/%s/address' % (name)] = address
                vals['interfaces/%s/netmask' % (name)] = netmask

                network = ipaddress.IPv4Network('%s/%s' % (address, netmask), False)
                vals['interfaces/%s/network' % (name)] = str(network.network_address)
                vals['interfaces/%s/broadcast' % (name)] = str(network.broadcast_address)

            for i, (address, netmask) in enumerate(self.ip4[1:]):
                vals['interfaces/%s_%s/address' % (name, i)] = address
                vals['interfaces/%s_%s/netmask' % (name, i)] = netmask

        if not self.ip6dynamic:
            for address, prefix, identifier in self.ip6:
                vals['interfaces/%s/ipv6/%s/address' % (name, identifier)] = address
                vals['interfaces/%s/ipv6/%s/prefix' % (name, identifier)] = prefix

        vals['interfaces/%s/ipv6/acceptRA' % (name)] = str(bool(self.ip6dynamic)).lower()

        options = sorted(self.get_options())
        for i, option in enumerate(options):
            vals['interfaces/%s/options/%d' % (name, i)] = option

        return vals

    def __repr__(self) -> str:
        return '<%s %r>' % (self.__class__.__name__, self.name)

    def __str__(self) -> str:
        return str(self.name)

    def __hash__(self) -> int:
        return hash(self.name)

    @property
    def dict(self):
        d = dict(self.__dict__)
        d["interfaceType"] = self.__class__.__name__
        for key in ('interfaces', '_leftover', 'network', 'broadcast', 'start', 'type', 'order'):
            d.pop(key, None)
        return d

    @staticmethod
    def from_dict(device, interfaces):
        DeviceType = {
            'Ethernet': Ethernet,
            'VLAN': VLAN,
            'Bridge': Bridge,
            'Bond': Bond,
        }.get(device['interfaceType'], Device)

        interface = DeviceType(device['name'], interfaces)
        interface.parse_ucr()

        # Bug 35601: frontend does not always pass a value for "ip4dynamic"/"ip6dynamic" to the backend
        if 'ip4dynamic' not in device:
            device['ip4dynamic'] = False
        if 'ip6dynamic' not in device:
            device['ip6dynamic'] = False

        interface.__dict__.update({k: device[k] for k in set(interface.dict.keys()) - {'start', 'type', 'order'} if k in device})
        if interface.ip4dynamic:
            interface.type = 'dhcp'

        return interface


class _RemovedDevice(Device):
    """Internal class representing that a device have to be removed from UCR"""

    def to_ucr(self) -> dict[str, str | None]:
        to_remove: dict[str, str | None] = {}
        for key in ucr:
            match = RE_INTERFACE.match(key)
            if match and self.name == match.group(1):
                to_remove[key] = None
        return to_remove

    def validate(self) -> None:
        return

    def validate_name(self) -> None:
        return


class Ethernet(Device):
    """A physical network interface"""


class VLAN(Device):
    """A virtual network interface (VLAN)"""

    @property
    def vlan_id(self) -> int:
        _, _, vlan = self.name.rpartition(".")
        return int(vlan)

    @vlan_id.setter
    def vlan_id(self, vlan_id: int) -> None:
        self.name = '%s.%d' % (self.parent_device, vlan_id)

    @property
    def parent_device(self) -> str:
        parent, _, _ = self.name.rpartition(".")
        return parent

    @parent_device.setter
    def parent_device(self, parent_device: str) -> None:
        self.name = '%s.%d' % (parent_device, self.vlan_id)

    @property
    def subdevice_names(self) -> set[str]:
        return {self.parent_device}

    def validate(self) -> None:
        super().validate()

        self.limit_ip4_address()

        # parent interface must exists
        if self.parent_device not in self.interfaces:
            raise DeviceError(_('Missing device: %r') % (self.parent_device), self.name)

        if isinstance(self.interfaces[self.parent_device], VLAN):
            # unsupported
            raise DeviceError('Nested VLAN-devices are currently unsupported.', self.name)

    def validate_name(self) -> None:
        super().validate_name()
        if '.' not in self.name:
            raise DeviceError(_('Invalid device name: %r') % (self.name,))
        if not (1 <= self.vlan_id <= 4095):
            raise DeviceError(_('Invalid VLAN ID. Must be between 1 and 4095.'), self.name)

    @property
    def dict(self) -> dict[str, str]:
        d = super().dict
        d["vlan_id"] = self.vlan_id
        d["parent_device"] = self.parent_device
        return d

    def parse_ucr(self) -> None:
        super().parse_ucr()
        options = []
        for option in self.options:
            try:
                name, value = option.split(None, 1)
            except ValueError:
                name, value = option, ''  # noqa: F841

            if name == 'vlan-raw-device':
                pass
            else:
                options.append(option)
        self.options = options

    def get_options(self) -> list[str]:
        options = super().get_options()
        options += [
            'vlan-raw-device %s' % (self.parent_device,),
        ]
        return options


class Bond(Device):
    """A network bonding interface"""

    MODES = {
        'balance-rr': 0,
        'active-backup': 1,
        'balance-xor': 2,
        'broadcast': 3,
        '802.3ad': 4,
        'balance-tlb': 5,
        'balance-alb': 6,
    }
    MODES_R = {v: k for k, v in MODES.items()}

    def clear(self) -> None:
        super().clear()
        self.bond_miimon: int | None = None
        self.bond_primary: list[str] = []
        self.bond_slaves: list[str] = []
        self.bond_mode = 0

        # TODO: arp_interval arp_ip_target downdelay lacp_rate max_bonds primary updelay use_carrier xmit_hash_policy

    def prepare_consistency(self) -> None:
        super().prepare_consistency()

        if self.bond_mode is None:
            self.bond_mode = 0

        for idevice in self.subdevices:
            # make sure that used interfaces does not have any IPv4 or IPv6 address
            idevice.disable_ips()

    def validate(self) -> None:
        super().validate()

        self.limit_ip4_address()

        self.validate_bond_mode()

        # at least one interface must exists in a bonding
        # FIXME: must bond_slaves contain at least 2 interfaces?
        if not self.bond_slaves:
            raise DeviceError(_('Missing device for bond-slaves'), self.name)

        for name in set(self.bond_slaves + self.bond_primary):
            # all interfaces must exists
            if name not in self.interfaces:
                raise DeviceError(_('Missing device: %r') % (name), self.name)

            # all interfaces must be physical
            if not isinstance(self.interfaces[name], Ethernet) or name not in PHYSICAL_INTERFACES:
                raise DeviceError(_('Devices used in a bonding must be physical: %s is not') % (name), self.name)

            # all used interfaces in a bonding must be unconfigured
            interface = self.interfaces[name]
            if interface.ip4 or interface.ip6:
                raise DeviceError(_('Cannot use device %s: Device must be unconfigured') % (name), self.name)

        # all bond-primaries must exists as bond-slaves
        if not set(self.bond_primary).issubset(set(self.bond_slaves)):
            raise DeviceError(_('Bond-primary must exist in bond-slaves'))

        self.check_unique_interface_usage()

    def validate_bond_mode(self) -> None:
        if self.bond_mode in self.MODES:
            return
        try:
            self.MODES_R[int(self.bond_mode)]
        except (ValueError, KeyError, TypeError):
            raise DeviceError(_('Invalid bond-mode: %r') % (self.bond_mode,), self.name)

    @property
    def subdevice_names(self) -> set[str]:
        return set(self.bond_slaves)

    def parse_ucr(self) -> None:
        super().parse_ucr()
        options = []
        for option in self.options:
            try:
                name, value = option.split(None, 1)
            except ValueError:
                name, value = option, ''

            if name == 'bond-primary':
                self.bond_primary = value.split()
            elif name == 'bond-slaves':
                self.bond_slaves = value.split()
            elif name == 'bond-mode':
                try:
                    self.bond_mode = int(value)
                except ValueError:
                    try:
                        self.bond_mode = self.MODES[value.strip()]
                    except KeyError:
                        pass  # invalid mode
            elif name in ('bond-miimon', 'miimon'):
                try:
                    self.bond_miimon = int(value)
                except ValueError:
                    pass
            else:
                options.append(option)
        self.options = options

    def get_options(self) -> list[str]:
        options = super().get_options()
        options += [
            'bond-slaves %s' % (' '.join(self.bond_slaves),),
            'bond-mode %s' % (self.bond_mode,),
        ]
        if int(self.bond_mode) == 1 and self.bond_primary:
            options.append('bond-primary %s' % (' '.join(self.bond_primary),))
        if self.bond_miimon is not None:
            options.append('bond-miimon %s' % (self.bond_miimon,))

        return options


class Bridge(Device):
    """A network bridge interface"""

    def clear(self) -> None:
        super().clear()
        self.bridge_ports: list[str] = []
        self.bridge_fd = 0

        # TODO: bridge_ageing bridge_bridgeprio bridge_gcint bridge_hello bridge_hw bridge_maxage bridge_maxwait bridge_pathcost bridge_portprio bridge_stp bridge_waitport

    @property
    def subdevice_names(self) -> set[str]:
        return set(self.bridge_ports)

    def prepare_consistency(self) -> None:
        super().prepare_consistency()

        for idevice in self.subdevices:
            # make sure that used interfaces does not have any IPv4 or IPv6 address
            idevice.disable_ips()

    def validate(self) -> None:
        super().validate()

        self.limit_ip4_address()

        for name in self.bridge_ports:
            # all interfaces must exists
            if name not in self.interfaces:
                raise DeviceError(_('Missing device: %r') % (name), self.name)

            # interface can't be a Bridge
            if isinstance(self.interfaces[name], Bridge):
                raise DeviceError(_('Cannot use bridge %r as bridge-port') % (name), self.name)

        self.check_unique_interface_usage()

    def parse_ucr(self) -> None:
        super().parse_ucr()
        options = []
        for option in self.options:
            try:
                name, value = option.split(None, 1)
            except ValueError:
                name, value = option, ''

            if name == 'bridge_ports':
                # TODO: support 'all' and 'bridge_ports all regex if.0 noregex ext0 regex vif.*'
                if value.strip().lower() == 'none':
                    self.bridge_ports = []
                else:
                    self.bridge_ports = value.split()
            elif name == 'bridge_fd':
                try:
                    self.bridge_fd = int(value)
                except ValueError:
                    pass
            else:
                options.append(option)
        self.options = options

    def get_options(self) -> list[str]:
        options = super().get_options()
        options += [
            'bridge_ports %s' % (' '.join(self.bridge_ports) or 'none',),
            'bridge_fd %d' % (self.bridge_fd,),
        ]

        return options


if __name__ == '__main__':
    import doctest
    print(doctest.testmod())
