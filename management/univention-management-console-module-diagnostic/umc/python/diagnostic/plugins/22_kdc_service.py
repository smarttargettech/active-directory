#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2016-2025 Univention GmbH
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

import ipaddress
import random
import socket
import struct
from collections.abc import Callable, Iterator
from typing import TypeVar

import dns.exception
import dns.resolver
import pyasn1.codec.der.decoder
import pyasn1.codec.der.encoder
import pyasn1.error
from pyasn1.type import base, char, namedtype, tag, univ, useful

from univention.config_registry import handler_set as ucr_set, ucr_live as configRegistry
from univention.lib.i18n import Translation
# ruff: noqa: A004
from univention.management.console.modules.diagnostic import MODULE, Critical, Instance, ProblemFixed, Warning, util


_ = Translation('univention-management-console-module-diagnostic').translate

title = _('KDC service check')
description = ['The check for the KDC reachability was successful.']
run_descr = ["Performs a KDC reachability check"]

_T = TypeVar("_T", bound="base.Asn1ItemBase")

# This checks for the reachability of KDCs by sending a AS-REQ per TCP and UDP.
# The AS-REQ is send with the fake user `kdc-reachability-check`. The KDCs will
# respond in several ways: either with an KRB-ERROR (PREAUTH_REQUIRED,
# PRINCIPAL_UNKNOWN or RESPONSE_TO_BIG) or a AS-REP with an anonymous ticket.
#
# If we do not receive one of the above, the connection is not accepted, the
# socket is closed or an operation times out, we can assume, that the KDCs is
# not reachable.
#
# This check will test the KDCs as specified in UCR `kerberos/kdc` with TCP and
# UDP on port 88. If `kerberos/defaults/dns_lookup_kdc` is set, KDC discovery as
# specified in section `7.2.3. KDC Discovery on IP Networks` [1] will be used.
# In this case the ports as specified in the SRV records are used.
#
# This implements a minimal number of packages as defined in [1] and does not
# rely on python-kerberos or python-krb5, as those are too high level and
# outdated.
#
# Reachability checks of kpasswd servers are not implemented, as those are a
# separate protocol. See [2].
#
# [1]: https://tools.ietf.org/html/rfc4120
# [2]: https://tools.ietf.org/html/rfc3244


def add_lo_to_samba_interfaces(umc_instance: Instance) -> None:
    interfaces = configRegistry.get('samba/interfaces', '').split()
    interfaces.append('lo')
    MODULE.process('Setting samba/interfaces')
    ucr_set(['samba/interfaces={}'.format(' '.join(interfaces))])
    return run(umc_instance, retest=True)


def reset_kerberos_kdc(umc_instance: Instance) -> None:
    MODULE.process('Resetting kerberos/kdc=127.0.0.1')
    ucr_set(['kerberos/kdc=127.0.0.1'])
    return run(umc_instance, retest=True)


description = _('ph ')
actions = {
    'add_lo_to_samba_interfaces': add_lo_to_samba_interfaces,
    'reset_kerberos_kdc': reset_kerberos_kdc,
}


def _sequence_component(name: str, tag_value: int, type: base.Asn1ItemBase) -> namedtype.NamedType:
    return namedtype.NamedType(name, type.subtype(
        explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, tag_value)))


def _sequence_optional_component(name: str, tag_value: int, type: base.Asn1ItemBase) -> namedtype.OptionalNamedType:
    return namedtype.OptionalNamedType(name, type.subtype(
        explicitTag=tag.Tag(tag.tagClassContext, tag.tagFormatSimple, tag_value)))


class PrincipalName(univ.Sequence):
    componentType = namedtype.NamedTypes(
        _sequence_component('name-type', 0, univ.Integer()),
        _sequence_component('name-string', 1, univ.SequenceOf(componentType=char.GeneralString())),
    )


class KdcReqBody(univ.Sequence):
    componentType = namedtype.NamedTypes(
        _sequence_component('kdc-options', 0, univ.BitString()),
        _sequence_optional_component('cname', 1, PrincipalName()),
        _sequence_component('realm', 2, char.GeneralString()),
        _sequence_optional_component('sname', 3, PrincipalName()),
        _sequence_optional_component('from', 4, useful.GeneralizedTime()),
        _sequence_component('till', 5, useful.GeneralizedTime()),
        _sequence_component('nonce', 7, univ.Integer()),
        _sequence_component('etype', 8, univ.SequenceOf(componentType=univ.Integer())))


class PAData(univ.Sequence):
    tagSet = univ.Sequence.tagSet + tag.Tag(tag.tagClassContext, tag.tagFormatSimple, 4)
    componentType = namedtype.NamedTypes(
        _sequence_component('padata-type', 1, univ.Integer()),
        _sequence_component('padata-value', 2, univ.OctetString()))


class AsReq(univ.Sequence):
    tagSet = univ.Sequence.tagSet + tag.Tag(tag.tagClassApplication, tag.tagFormatSimple, 10)
    componentType = namedtype.NamedTypes(
        _sequence_component('pvno', 1, univ.Integer()),
        _sequence_component('msg-type', 2, univ.Integer()),
        _sequence_component('padata', 3, univ.SequenceOf(componentType=PAData())),
        _sequence_component('req-body', 4, KdcReqBody()))


class AsRep(univ.Sequence):
    tagSet = univ.Sequence.tagSet + tag.Tag(tag.tagClassApplication, tag.tagFormatSimple, 11)
    componentType = namedtype.NamedTypes(
        _sequence_component('pvno', 0, univ.Integer()),
        _sequence_component('msg-type', 1, univ.Integer()),
        # some more omitted
    )


class KrbError(univ.Sequence):
    tagSet = univ.Sequence.tagSet + tag.Tag(tag.tagClassApplication, tag.tagFormatSimple, 30)
    componentType = namedtype.NamedTypes(
        _sequence_component('pvno', 0, univ.Integer()),
        _sequence_component('msg-type', 1, univ.Integer()),
        # some more omitted
    )


class KerberosException(Exception):
    pass


class ServerUnreachable(KerberosException):
    pass


class InvalidResponse(KerberosException):
    pass


class EmptyResponse(KerberosException):
    pass


class Principal:

    def __init__(self, name: str, realm: str, princ_type: base.Asn1ItemBase) -> None:
        self.type = princ_type
        self.realm = realm
        self.components = [name, realm]

    def components_to_asn1(self, name: _T) -> _T:
        name.setComponentByName('name-type', int(self.type))
        strings = name.setComponentByName('name-string').getComponentByName('name-string')
        for i, c in enumerate(self.components):
            strings.setComponentByPosition(i, c)
        return name


def seq_set(seq: univ.Sequence, name: str, builder: Callable | None = None) -> base.Asn1ItemBase:
    component = seq.setComponentByName(name).getComponentByName(name)
    if builder is not None:
        seq.setComponentByName(name, builder(component))
    else:
        seq.setComponentByName(name)
    return seq.getComponentByName(name)


def build_kerberos_request(target_realm: str, user_name: str) -> bytes:

    as_req = AsReq()
    as_req['pvno'] = 5
    as_req['msg-type'] = 10  # AS-REQ
    as_req['padata'] = univ.noValue

    serverName = Principal('krbtgt', target_realm, 1)
    clientName = Principal(user_name, target_realm, 1)

    req_body = seq_set(as_req, 'req-body')
    req_body['kdc-options'] = [0 for i in range(32)]
    seq_set(req_body, 'sname', serverName.components_to_asn1)
    seq_set(req_body, 'cname', clientName.components_to_asn1)

    req_body['realm'] = target_realm
    req_body['till'] = '19700101000000Z'
    req_body['nonce'] = random.SystemRandom().getrandbits(31)

    return pyasn1.codec.der.encoder.encode(as_req)


def send_and_receive(kdc: str, port: int, protocol: str, as_req: bytes) -> bytes:
    socket_type = socket.SOCK_DGRAM if protocol == 'udp' else socket.SOCK_STREAM
    sock = socket.socket(socket.AF_INET, socket_type)
    sock.settimeout(1)

    packed = struct.pack('>I', len(as_req)) + as_req if protocol == 'tcp' else as_req

    try:
        sock.connect((kdc, port))
        sock.sendall(packed)
    except (TimeoutError, OSError):
        sock.close()
        raise ServerUnreachable()

    received = b''
    num_received = 0
    if protocol == 'udp':  # fake the length field
        received += b'\x00\x00\x00\x00'
        num_received += 4
    while num_received < 128:
        try:
            (buf, _addr) = sock.recvfrom(128)
        except (TimeoutError, OSError):
            buf = b''
        if not buf:
            break
        received += buf
        num_received += len(buf)

    if not received:
        raise EmptyResponse()

    return received


def probe_kdc(kdc: str, port: int, protocol: str, target_realm: str, user_name: str) -> bool:
    request = build_kerberos_request(target_realm, user_name)
    if protocol == 'udp':
        MODULE.process("Trying to contact KDC %s on udp port %d Similar to running: nmap %s -sU -p %d" % (kdc, port, kdc, port))
    else:
        MODULE.process("Trying to contact KDC %s on tcp port %d Similar to running: nmap %s -sT -p %d" % (kdc, port, kdc, port))
    try:
        received = send_and_receive(kdc, port, protocol, request)
    except KerberosException:
        return False

    return target_realm.encode('UTF-8') in received

    # this no longer works with >= 4.3, ??
    # I think the new pyasn1 version might need the full asn1Spec to work?:
    # http://snmplabs.com/pyasn1/changelog.html
    # Keyword: require strict two-zeros sentinel encoding
    try:
        (_error, _sub) = pyasn1.codec.der.decoder.decode(received, asn1Spec=KrbError())
    except pyasn1.error.PyAsn1Error:
        pass
    else:
        return True

    try:
        (_rep, _sub) = pyasn1.codec.der.decoder.decode(received, asn1Spec=AsRep())
    except pyasn1.error.PyAsn1Error:
        return False

    return True


def resolve_kdc_record(protocol: str, domainname: str) -> Iterator[tuple[str, int, str]]:
    kerberos_dns_fqdn = f'_kerberos._{protocol}.{domainname}'
    try:
        result = dns.resolver.query(kerberos_dns_fqdn, 'SRV')
    except dns.exception.DNSException:
        result = []

    for record in result:
        yield (record.target.to_text(True), record.port, protocol)


def run(_umc_instance: Instance, retest: bool = False) -> None:
    target_realm = configRegistry.get('kerberos/realm')
    user_name = 'kdc-reachability-check'

    kdc_fqds = configRegistry.get('kerberos/kdc', '').split()
    dns_lookup_kdc = configRegistry.is_true('kerberos/defaults/dns_lookup_kdc', True)
    if not kdc_fqds or dns_lookup_kdc:
        domainname = configRegistry.get('domainname')
        kdc_to_check = list(resolve_kdc_record('tcp', domainname))
        kdc_to_check.extend(resolve_kdc_record('udp', domainname))
    else:
        kdc_to_check = [(kdc, 88, 'tcp') for kdc in kdc_fqds]
        kdc_to_check.extend((kdc, 88, 'udp') for kdc in kdc_fqds)

    kdc_reachabe = [(probe_kdc(kdc, port, protocol, target_realm, user_name), (kdc, port, protocol)) for (kdc, port, protocol) in kdc_to_check]
    reachable_kdc = [
        (kdc, port, protocol) for (reachable, (kdc, port, protocol))
        in kdc_reachabe if reachable]
    unreachable_kdc = [
        (kdc, port, protocol) for (reachable, (kdc, port, protocol))
        in kdc_reachabe if not reachable]

    error_descriptions = []

    if unreachable_kdc:
        error = _('The following KDCs were unreachable: {}')
        unreach_string = (f'{protocol} {kdc}:{port}' for (kdc, port, protocol) in unreachable_kdc)
        error_descriptions.append(error.format(', '.join(unreach_string)))

    if not reachable_kdc:
        is_dc = configRegistry.get('server/role') == 'domaincontroller_master'
        is_s4_dc = is_dc and util.is_service_active('Samba 4')
        if is_s4_dc and configRegistry.is_true('samba/interfaces/bindonly', False):
            local_included = False
            for interface in configRegistry.get('samba/interfaces', '').split():
                try:
                    addr = ipaddress.ip_address('%s' % (interface,))
                except ValueError:
                    local_included |= interface == 'lo'
                else:
                    local_included |= addr.is_loopback or addr.is_unspecified
            if not local_included:
                error = _('samba/interfaces does not contain lo, 127.0.0.1 or 0.0.0.0.')
                error_descriptions.append(error)

            description = '\n'.join(error_descriptions)
            buttons = [{
                'action': 'add_lo_to_samba_interfaces',
                'label': _('Add lo to samba/interfaces'),
            }, {
                'action': 'reset_kerberos_kdc',
                'label': _('Reset kerberos/kdc to 127.0.0.1'),
            }]
            raise Critical(description=description, buttons=buttons)

        error_descriptions.append(_('No reachable KDCs were found.'))
        description = '\n'.join(error_descriptions)
        raise Critical(description=description)

    if error_descriptions:
        error = '\n'.join(error_descriptions)
        MODULE.error(error)
        raise Warning(description=error)

    if retest:
        raise ProblemFixed()


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
