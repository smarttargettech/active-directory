#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2018-2025 Univention GmbH
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
# you and Univention.
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
A generic UDM module and object implementation.
Will work for all kinds of UDM modules.
"""


import copy
import functools
import inspect
import logging
import operator
import sys
from collections.abc import Iterable, Iterator  # noqa: F401

import ldap
from ldap.dn import dn2str, str2dn

import univention.admin.modules
import univention.admin.objects
import univention.admin.uexceptions
import univention.admin.uldap
import univention.config_registry

from ..base import BaseModule, BaseModuleMetadata, BaseObject, BaseObjectProperties, LdapMapping, ModuleMeta
from ..encoders import (  # noqa: F401
    BaseEncoder, DnPropertyEncoder, PoliciesEncoder, dn_list_property_encoder_for, dn_property_encoder_for,
)
from ..exceptions import (
    CreateError, DeletedError, DeleteError, ModifyError, MoveError, NoObject, NoSuperordinate, NotYetSavedError,
    SearchLimitReached, UdmError, UnknownModuleType, UnknownProperty, WrongObjectType,
)


ucr = univention.config_registry.ConfigRegistry()
ucr.load()
DEFAULT_CONTAINERS_DN = 'cn=default containers,cn=univention,{}'.format(ucr['ldap/base'])


class GenericObjectProperties(BaseObjectProperties):
    """
    Container for UDM properties.

    :py:attr:`_encoders` is a mapping from property names to subclasses of
    _encoders.BaseEncoder, which will be used to transparently map between the
    properties representation in original UDM and the new UDM APIs.
    """

    _encoders = {}  # type: Dict

    def __init__(self, udm_obj):
        # type: (BaseObject) -> None
        super().__init__(udm_obj)
        for encoder_class in self._encoders.values():
            assert hasattr(encoder_class, 'decode')
            assert hasattr(encoder_class, 'encode')

    def __setattr__(self, key, value):
        # type: (str, Any) -> None
        if not str(key).startswith('_') and key not in self._udm_obj._orig_udm_object:
            raise UnknownProperty(
                f'Unknown property {key!r} for UDM module {self._udm_obj._udm_module.name!r}.',
                dn=self._udm_obj.dn,
                module_name=self._udm_obj._udm_module.name,
            )
        super().__setattr__(key, value)


class GenericObject(BaseObject):
    r"""
    Generic object class that can be used with all UDM module types.

    Usage:

    *   Creation of instances :py:class:`GenericObject` is always done through
        :py:meth:`GenericModul.new`, :py:meth:`GenericModul.get` or :py:meth:`GenericModul.search`.

    *   Modify an object::

            user.props.firstname = 'Peter'
            user.props.lastname = 'Pan'
            user.save()

    *   Move an object::

           user.position = 'cn=users,ou=Company,dc=example,dc=com'
           user.save()

    *   Delete an object::

           obj.delete()

    After saving a :py:class:`GenericObject`, it is :py:meth:`reload`\ ed
    automatically because UDM hooks and listener modules often add, modify or
    remove properties when saving to LDAP. As this involves LDAP, it can be
    disabled if the object is not used afterwards and performance is an issue::

        user_mod.meta.auto_reload = False
    """

    udm_prop_class = GenericObjectProperties
    _policies_encoder = None

    def __init__(self):
        # type: () -> None
        """
        Don't instantiate a :py:class:`GenericObject` directly. Use
        :py:meth:`GenericModule.get()`, :py:meth:`GenericModule.new()` or
        :py:meth:`GenericModule.search()`.
        """
        super().__init__()
        self._udm_module = None  # type: Optional[GenericModule]
        self._lo = None  # type: Optional[univention.admin.uldap.access]
        self._orig_udm_object = None  # type: Optional[univention.admin.handlers.simpleLdap]
        self._old_position = ''
        self._fresh = True
        self._deleted = False

    def reload(self):
        # type: () -> GenericObject
        """
        Refresh object from LDAP.

        :return: self
        :raises univention.udm.exceptions.NotYetSavedError: if object does not yet exist (has no dn)
        """
        assert self._udm_module is not None
        if self._deleted:
            raise DeletedError(f'{self} has been deleted.', dn=self.dn, module_name=self._udm_module.name)
        if not self.dn or not self._orig_udm_object:
            raise NotYetSavedError(module_name=self._udm_module.name)
        self._orig_udm_object = self._udm_module._get_orig_udm_object(self.dn)
        self._copy_from_udm_obj()
        logging.getLogger('ADMIN').debug('%r object (dn: %r) reloaded', self._udm_module.name, self.dn)
        return self

    def save(self):
        # type: () -> GenericObject
        """
        Save object to LDAP.

        :return: self
        :raises univention.udm.exceptions.MoveError: when a move operation fails
        """
        assert self._udm_module is not None
        if self._deleted:
            raise DeletedError(f'{self} has been deleted.', dn=self.dn, module_name=self._udm_module.name)
        if not self._fresh:
            logging.getLogger('ADMIN').warning('Saving stale UDM object instance')
        self._copy_to_udm_obj()
        assert self._orig_udm_object is not None
        if self.dn:
            if self._old_position and self._old_position != self.position:
                new_dn_li = [str2dn(self._orig_udm_object.dn)[0]]
                new_dn_li.extend(str2dn(self.position))
                new_dn = dn2str(new_dn_li)
                logging.getLogger('ADMIN').info('Moving %r object %r to %r', self._udm_module.name, self.dn, new_dn)
                try:
                    self.dn = self._orig_udm_object.move(new_dn)
                except univention.admin.uexceptions.invalidOperation as exc:
                    raise MoveError(
                        f'Moving {self._udm_module.name!r} object is not supported ({exc}).',
                        dn=self.dn, module_name=self._udm_module.name,
                    ).with_traceback(sys.exc_info()[2])
                except (univention.admin.uexceptions.base, ldap.error) as exc:
                    raise MoveError(
                        f'Error moving {self._udm_module.name!r} object from {self.dn!r} to {self.position!r}: {exc}', dn=self.dn, module_name=self._udm_module.name,
                    ).with_traceback(sys.exc_info()[2])
                assert self.dn == self._orig_udm_object.dn
                self.position = self._lo.parentDn(self.dn)
                self._old_position = self.position
                self._orig_udm_object.position.setDn(self.position)
            try:
                self.dn = self._orig_udm_object.modify()
            except univention.admin.uexceptions.base as exc:
                raise ModifyError(
                    f'Error saving {self._udm_module.name!r} object at {self.dn!r}: {exc}', dn=self.dn, module_name=self._udm_module.name,
                ).with_traceback(sys.exc_info()[2])
            logging.getLogger('ADMIN').info('Modified %r object %r', self._udm_module.name, self.dn)
        else:
            try:
                self.dn = self._orig_udm_object.create()
            except ldap.INVALID_DN_SYNTAX as exc:
                raise CreateError(
                    f'Error creating {self._udm_module.name!r} object: {exc}', module_name=self._udm_module.name,
                ).with_traceback(sys.exc_info()[2])
            except univention.admin.uexceptions.base as exc:
                raise CreateError(
                    f'Error creating {self._udm_module.name!r} object: {exc}', module_name=self._udm_module.name,
                ).with_traceback(sys.exc_info()[2])
            logging.getLogger('ADMIN').info('Created %r object %r', self._udm_module.name, self.dn)

        assert self.dn == self._orig_udm_object.dn
        assert self.position == self._lo.parentDn(self.dn)
        self._fresh = False
        if self._udm_module.meta.auto_reload:
            self.reload()
        return self

    def delete(self, remove_childs=False):
        # type: (bool) -> None
        """
        Remove the object (and optionally its child nodes) from the LDAP database.

        :param bool remove_childs: if there are UDM objects below this objects DN, recursively remove
                them before removing this object
        :raises univention.udm.exceptions.NotYetSavedError: if object does not yet exist (has no dn)
        :raises univention.udm.exceptions.DeletedError: if the operation fails
        """
        assert self._udm_module is not None
        if self._deleted:
            logging.getLogger('ADMIN').warning('%s has already been deleted', self)
            return
        if not self.dn or not self._orig_udm_object:
            raise NotYetSavedError()
        try:
            self._orig_udm_object.remove(remove_childs=remove_childs)
        except univention.admin.uexceptions.base as exc:
            raise DeleteError(
                f'Error deleting {self._udm_module.name!r} object {self.dn!r}: {exc}', dn=self.dn, module_name=self._udm_module.name,
            )
        if univention.admin.objects.wantsCleanup(self._orig_udm_object):
            univention.admin.objects.performCleanup(self._orig_udm_object)
        self._orig_udm_object = None
        self._deleted = True
        logging.getLogger('ADMIN').info('Deleted %r object %r', self._udm_module.name, self.dn)

    def _copy_from_udm_obj(self):
        # type: () -> None
        """
        Copy UDM property values from low-level UDM object to `props`
        container as well as its `policies` and `options`.
        """
        assert self._udm_module is not None
        assert self._orig_udm_object is not None
        self.dn = self._orig_udm_object.dn
        self.entry_uuid = self._orig_udm_object.entry_uuid
        self.options = self._orig_udm_object.options
        if self._udm_module.meta.used_api_version >= 3:
            # policies is a mapping of policy-type to a list of referenced policy-dn
            if not self._policies_encoder:
                self.__class__._policies_encoder = self._init_encoder(
                    PoliciesEncoder, property_name='__policies', lo=self._lo, module_name=self._udm_module.name,
                )
            self.policies = self._policies_encoder.decode(self._orig_udm_object.policies)
        elif self._udm_module.meta.used_api_version > 0:
            # policies are a list of referenced policy DN's
            # encoders exist from API version 1 on
            if not self._policies_encoder:
                # 'auto', because list contains policies/*
                policies_encoder_class = dn_list_property_encoder_for('auto')
                self.__class__._policies_encoder = self._init_encoder(
                    policies_encoder_class, property_name='__policies', lo=self._lo,
                )
            self.policies = self._policies_encoder.decode(self._orig_udm_object.policies)
        else:
            self.policies = self._orig_udm_object.policies
        self.props = self.udm_prop_class(self)
        if not self.dn:
            self._init_new_object_props()
        for k in self._orig_udm_object.keys():
            # workaround Bug #47971: _orig_udm_object.items() changes object
            v = self._orig_udm_object.get(k)
            if not self.dn and v is None:
                continue
            if self._udm_module.meta.used_api_version > 0:
                # encoders exist from API version 1 on
                try:
                    encoder_class = self.props._encoders[k]
                except KeyError:
                    val = v
                else:
                    encoder = self._init_encoder(encoder_class, property_name=k)
                    val = encoder.decode(v)
            else:
                val = v
            if val is None and self._orig_udm_object.descriptions[k].multivalue:
                val = []
            setattr(self.props, k, val)
        if self._orig_udm_object.superordinate:
            if self._udm_module.meta.used_api_version > 0:
                # encoders exist from API version 1 on
                superordinate_encoder_class = dn_property_encoder_for('auto')  # 'auto', because superordinate can be anything
                superordinate_encoder = self._init_encoder(
                    superordinate_encoder_class, property_name='__superordinate', lo=self._lo,
                )
                self.superordinate = superordinate_encoder.decode(self._orig_udm_object.superordinate.dn)
            else:
                self.superordinate = self._orig_udm_object.superordinate.dn
        if self.dn:
            self.position = self._lo.parentDn(self.dn)
            self._old_position = self.position
        else:
            if self._orig_udm_object.superordinate:
                self.position = self._orig_udm_object.superordinate.dn
            else:
                self.position = self._udm_module._get_default_object_positions()[0]
            logging.getLogger('ADMIN').debug('Set position to %r', self.position)
        self._fresh = True

    def _copy_to_udm_obj(self):
        # type: () -> None
        """
        Copy UDM property values from `props` container to low-level UDM
        object.
        """
        assert self._udm_module is not None
        assert self._orig_udm_object is not None
        self._orig_udm_object.options = self.options
        if self._udm_module.meta.used_api_version >= 3:
            self._orig_udm_object.policies = functools.reduce(operator.add, self.policies.values(), [])
        else:
            self._orig_udm_object.policies = self.policies
        self._orig_udm_object.position.setDn(self.position)
        keys = list(self._orig_udm_object.keys())
        if 'ip' in keys and 'network' in keys:
            keys.remove('ip')  # restore broken behavior of Python 2.7 to make test 59_udm/59_udm_api_computers pass; Bug #25163
            keys = ['ip', *keys]
        for k in keys:
            # workaround Bug #47971: _orig_udm_object.items() changes object
            v = self._orig_udm_object.get(k)
            new_val = getattr(self.props, k, None)
            if self._udm_module.meta.used_api_version > 0:
                # encoders exist from API version 1 on
                try:
                    encoder_class = self.props._encoders[k]
                except KeyError:
                    new_val2 = new_val
                else:
                    encoder = self._init_encoder(encoder_class, property_name=k)
                    new_val2 = encoder.encode(new_val)
            else:
                new_val2 = new_val
            if v != new_val2:
                self._orig_udm_object[k] = new_val2
        if self.superordinate:
            # _orig_udm_object.superordinate is a orig UDM module
            if isinstance(self.superordinate, str):
                sup_obj = GenericModule(
                    self._udm_module._orig_udm_module.superordinate,
                    self._lo,
                    self._udm_module.meta.used_api_version,
                ).get(self.superordinate)
                self._orig_udm_object.superordinate = sup_obj._orig_udm_object
            elif isinstance(self.superordinate, GenericObject):
                self._orig_udm_object.superordinate = self.superordinate._orig_udm_object
            elif isinstance(self.superordinate, DnPropertyEncoder.DnStr):
                self._orig_udm_object.superordinate = self.superordinate.obj._orig_udm_object
            else:
                msg = f'Unkown type {type(self.superordinate)!r} in "superordinate" of {self!r}.'
                logging.getLogger('ADMIN').error('%s', msg)
                raise ValueError(msg)

    def _init_new_object_props(self):
        # type: () -> None
        """
        This is a modified copy of the code of
        :py:meth:`univention.admin.handlers.simpleLdap.__getitem__()` which
        creates the default values for a new object, without setting them on
        the underlying UDM object.
        """
        assert self._orig_udm_object is not None
        for key in self._orig_udm_object.keys():
            if key in self._orig_udm_object.info:
                if self._orig_udm_object.descriptions[key].multivalue and not isinstance(self._orig_udm_object.info[key], list):
                    # why isn't this correct in the first place?
                    setattr(self.props, key, [self._orig_udm_object.info[key]])
                    continue
                setattr(self.props, key, self._orig_udm_object.info[key])
            # Disabled if branch, because the defaults should be calculated
            # when saving and not when accessing (which is the reason this code
            # needs to be here):
            # elif key not in self._orig_udm_object._simpleLdap__no_default and self._orig_udm_object.descriptions[key].editable:
            #     ...
            elif self._orig_udm_object.descriptions[key].multivalue:
                setattr(self.props, key, [])
            else:
                setattr(self.props, key, None)

    def _init_encoder(self, encoder_class, **kwargs):
        # type: (Type[BaseEncoder], **Any) -> Union[Type[BaseEncoder], BaseEncoder]
        """
        Instantiate encoder object if required. Optionally assemble additional
        arguments.

        :param encoder_class: a subclass of BaseEncoder
        :param kwargs: named arguments to pass to __init__ when instantiating encoder object
        :return: either a class object or an instance, depending on the class variable :py:attr:`static`
        """
        if encoder_class.static:
            # don't create an object if not necessary
            return encoder_class
        else:
            assert self._udm_module is not None
            # initialize with required arguments
            for arg in inspect.getfullargspec(encoder_class.__init__).args:
                if arg == 'self':
                    continue
                elif arg in kwargs:
                    continue
                elif arg == 'connection':
                    kwargs['connection'] = self._udm_module.connection
                elif arg == 'api_version':
                    kwargs['api_version'] = self._udm_module.meta.used_api_version
                else:
                    raise TypeError(f'Unknown argument {arg!r} for {encoder_class.__class__.__name__}.__init__.')
            return encoder_class(**kwargs)


class GenericModuleMetadata(BaseModuleMetadata):
    def __init__(self, meta):
        # type: (GenericModule.Meta) -> None
        super().__init__(meta)
        self.default_positions_property = None
        if hasattr(meta, 'default_positions_property'):
            self.default_positions_property = meta.default_positions_property

    @property
    def identifying_property(self):
        # type: () -> str
        """
        UDM Property of which the mapped LDAP attribute is used as first
        component in a DN, e.g. `username` (LDAP attribute `uid`) or `name`
        (LDAP attribute `cn`).
        """
        assert self._udm_module is not None
        for key, udm_property in self._udm_module._orig_udm_module.property_descriptions.items():
            if udm_property.identifies:
                return key
        return ''

    def lookup_filter(self, filter_s=None):
        # type: (Optional[str]) -> str
        """
        Filter the UDM module uses to find its corresponding LDAP objects.

        This can be used in two ways:

        *   get the filter to find all objects::

                myfilter_s = obj.meta.lookup_filter()

        *   get the filter to find a subset of the corresponding LDAP objects (`filter_s` will be combined with `&` to the filter for all objects)::

                myfilter = obj.meta.lookup_filter('(|(givenName=A*)(givenName=B*))')

        :param str filter_s: optional LDAP filter expression
        :return: an LDAP filter string
        """
        assert self._udm_module is not None
        return str(self._udm_module._orig_udm_module.lookup_filter(filter_s, self._udm_module.connection))

    @property
    def mapping(self):
        # type: () -> LdapMapping
        """
        UDM properties to LDAP attributes mapping and vice versa.

        :return: a namedtuple containing two mappings: a) from UDM property to LDAP attribute and b) from LDAP attribute to UDM property
        """
        assert self._udm_module is not None
        return LdapMapping(
            udm2ldap={k: v[0] for k, v in self._udm_module._orig_udm_module.mapping._map.items()},
            ldap2udm={k: v[0] for k, v in self._udm_module._orig_udm_module.mapping._unmap.items()},
        )


class GenericModuleMeta(ModuleMeta):
    udm_meta_class = GenericModuleMetadata


class GenericModule(BaseModule, metaclass=GenericModuleMeta):
    """
    Simple API to use UDM modules. Basically a GenericObject factory.

    Usage:

    0.  Get module using::

            user_mod = UDM.admin/machine/credentials().version(2).get('users/user')

    1.  Create fresh, not yet saved GenericObject::

            new_user = user_mod.new()

    2.  Load an existing object::

            group = group_mod.get('cn=test,cn=groups,dc=example,dc=com')
            group = group_mod.get_by_id('Domain Users')

    3.  Search and load existing objects::

            dc_slaves = dc_slave_mod.search(filter_s='cn=s10*')
            campus_groups = group_mod.search(base='ou=campus,dc=example,dc=com')
    """

    _udm_object_class = GenericObject  # type: Type[GenericObject]
    _udm_module_meta_class = GenericModuleMetadata  # type: Type[GenericModuleMetadata]
    _udm_module_cache = {}  # type: Dict[Tuple[str, str, str, str], univention.admin.modules.UdmModule]
    _default_containers = {}  # type: Dict[str, Dict[str, Any]]

    class Meta:
        supported_api_versions = [0, 1, 2, 3]
        suitable_for = ['*/*']

    def __init__(self, name, connection, api_version):
        # type: (str, Any, int) -> None
        super().__init__(name, connection, api_version)
        self._orig_udm_module = self._get_orig_udm_module()

    def new(self, superordinate=None):
        # type: (Union[str, GenericObject, None]) -> GenericObject
        """
        Create a new, unsaved GenericObject object.

        :param superordinate: DN or UDM object this one references as its
                superordinate (required by some modules)
        :return: a new, unsaved GenericObject object
        """
        return self._load_obj('', superordinate)

    def get(self, dn):
        # type: (str) -> GenericObject
        """
        Load UDM object from LDAP.

        :param str dn: DN of the object to load
        :return: an existing GenericObject object
        :raises univention.udm.exceptions.NoObject: if no object is found at `dn`
        :raises univention.udm.exceptions.WrongObjectType: if the object found at `dn` is not of type :py:attr:`self.name`
        """
        return self._load_obj(dn)

    def search(self, filter_s='', base='', scope='sub', sizelimit=0):
        # type: (str, str, str, int) -> Iterator[GenericObject]
        """
        Get all UDM objects from LDAP that match the given filter.

        :param str filter_s: LDAP filter (only object selector like uid=foo
                required, objectClasses will be set by the UDM module)
        :param str base: subtree to search
        :param str scope: depth to search
        :param int sizelimit: LDAP size limit for searched results.
        :return: generator to iterate over GenericObject objects
        """
        try:
            try:
                udm_module_lookup_filter = str(self._orig_udm_module.lookup_filter(filter_s, self.connection))
                dns = self.connection.searchDn(
                    filter=udm_module_lookup_filter,
                    base=base,
                    scope=scope,
                    sizelimit=sizelimit,
                )
            except AttributeError:
                # not all modules have 'lookup_filter'
                dns = (obj.dn for obj in self._orig_udm_module.lookup(
                    None,
                    self.connection,
                    filter_s,
                    base=base,
                    scope=scope,
                    sizelimit=sizelimit,
                ))
        except univention.admin.uexceptions.ldapSizelimitExceeded:
            raise SearchLimitReached(module_name=self.name, search_filter=filter_s, sizelimit=sizelimit)
        for dn in dns:
            try:
                retrieved_obj = self.get(dn)
            except NoObject:
                logging.getLogger('ADMIN').warning('Skipping over search result with DN %r, that does not exist anymore', dn)
                continue
            yield retrieved_obj

    def _dn_exists(self, dn):
        # type: (str) -> bool
        """
        Checks if the DN exists in LDAP.

        :param str dn: the DN
        :return: whether `dn` exists
        """
        try:
            self.connection.searchDn(base=dn, scope='base')
        except univention.admin.uexceptions.noObject:
            return False
        else:
            return True

    def _get_default_containers(self):
        # type: () -> Dict[str, List[str]]
        """
        Get default containers for all modules.

        :return: a dictionary with lists of DNs
        """
        if not self._default_containers:
            # DEFAULT_CONTAINERS_DN must exist, or we'll run into an infinite recursion
            if self._dn_exists(DEFAULT_CONTAINERS_DN):
                mod = GenericModule('settings/directory', self.connection, 0)
                try:
                    default_directory_object = mod.get(DEFAULT_CONTAINERS_DN)
                except NoObject:
                    pass
                else:
                    self._default_containers.update(copy.deepcopy(default_directory_object.props))
        return self._default_containers

    def _get_default_object_positions(self):
        # type: () -> List[str]
        """
        Get default containers for this UDM module.

        :return: list of container DNs
        """
        module_contailers = [
            '{},{}'.format(dc, getattr(self._orig_udm_module.object, 'ldap_base', ucr['ldap/base']))
            for dc in getattr(self._orig_udm_module, 'default_containers', [])
        ]

        default_positions_property = self.meta.default_positions_property
        default_containers = self._get_default_containers()

        if default_containers and default_positions_property:
            dns = default_containers.get(default_positions_property, [])
            module_contailers.extend(dn for dn in dns if self._dn_exists(dn))
        module_contailers.append(getattr(self._orig_udm_module.object, 'ldap_base', self.connection.base))
        return module_contailers

    def _get_orig_udm_module(self):
        # type: () -> univention.admin.modules.UdmModule
        """
        Load a UDM module, initializing it if required.

        :return: a UDM module
        """
        # While univention.admin.modules already implements a modules cache we
        # cannot know if update() or init() are required. So we'll also cache.
        key = (self.connection.base, self.connection.binddn, self.connection.host, self.name)
        if key not in self._udm_module_cache:
            if self.name not in [k[3] for k in self._udm_module_cache.keys()]:
                univention.admin.modules.update()
            try:
                udm_module = univention.admin.modules._get(self.name)
            except LookupError:
                raise UnknownModuleType(
                    msg=f'UDM module {self.name!r} does not exist.',
                    module_name=self.name,
                )
            po = univention.admin.uldap.position(self.connection.base)
            univention.admin.modules.init(self.connection, po, udm_module)
            self._udm_module_cache[key] = udm_module
        return self._udm_module_cache[key]

    def _get_orig_udm_object(self, dn, superordinate=None):
        # type: (str, Union[str, GenericObject, None]) -> univention.admin.handlers.simpleLdap
        """
        Retrieve UDM object from LDAP.

        May raise from NoObject if no object is found at DN or WrongObjectType
        if the object found is not of type :py:attr:`self.name`.

        :param str dn: the DN of the object to load
        :param superordinate: DN or UDM object this one references as its
                superordinate (required by some modules)
        :param univention.admin.handlers.simpleLdap orig_udm_object: original
                UDM object instance, if unset one will be created from `dn`
        :return: UDM object
        :raises univention.udm.exceptions.NoObject: if no object is found at `dn`
        :raises univention.udm.exceptions.WrongObjectType: if the object found at `dn` is not of type :py:attr:`self.name`
        """
        udm_module = self._get_orig_udm_module()
        if superordinate:
            if isinstance(superordinate, str):
                superordinate_obj = univention.admin.objects.get_superordinate(udm_module, None, self.connection, superordinate)
            elif isinstance(superordinate, GenericObject):
                superordinate_obj = superordinate._orig_udm_object
            else:
                raise ValueError('Argument "superordinate" must be a DN (string) or a GenericObject instance.')
        else:
            superordinate_obj = None
        if not dn and not superordinate_obj:
            # check if objects of this module require a superordinate
            superordinate_modules = univention.admin.modules.superordinate_names(self.name)
            if superordinate_modules and superordinate_modules != ['settings/cn']:
                raise NoSuperordinate(dn=dn, module_name=self.name, superordinate_types=superordinate_modules)
        po = univention.admin.uldap.position(getattr(udm_module.object, 'ldap_base', self.connection.base))
        try:
            obj = univention.admin.objects.get(udm_module, None, self.connection, po, dn=dn, superordinate=superordinate_obj)
            assert obj is not None
        except univention.admin.uexceptions.noObject:
            raise NoObject(dn=dn, module_name=self.name).with_traceback(sys.exc_info()[2])
        except univention.admin.uexceptions.base as exc:
            raise UdmError(
                f'Error loading UDM object at DN {dn!r}: {exc}', dn=dn, module_name=self.name,
            ).with_traceback(sys.exc_info()[2])
        self._verify_univention_object_type(obj)
        if self.meta.auto_open:
            obj.open()
        return obj

    def _load_obj(self, dn, superordinate=None, orig_udm_object=None):
        # type: (str, Union[str, GenericObject, None], Optional[univention.admin.handlers.simpleLdap]) -> GenericObject
        """
        GenericObject factory.

        :param str dn: the DN of the UDM object to load, if '' a new one
        :param superordinate: DN or UDM object this one references as its
                superordinate (required by some modules)
        :param univention.admin.handlers.simpleLdap orig_udm_object: original
                UDM object instance, if unset one will be created from `dn`
        :return: a GenericObject
        :raises univention.udm.exceptions.NoObject: if no object is found at `dn`
        :raises univention.udm.exceptions.ValueError: if `orig_udm_object` is not a
                :py:class:`univention.admin.handlers.simpleLdap` instance
        :raises univention.udm.exceptions.WrongObjectType: if the object found at `dn` is not of type
                :py:attr:`self.name`
        """
        obj = self._udm_object_class()
        obj._lo = self.connection
        obj._udm_module = self
        if orig_udm_object:
            if not isinstance(orig_udm_object, univention.admin.handlers.simpleLdap):
                raise ValueError('Argument "orig_udm_object" must be an original UDM object instance.')
            obj._orig_udm_object = orig_udm_object
        else:
            obj._orig_udm_object = self._get_orig_udm_object(dn, superordinate)
        obj._copy_from_udm_obj()
        logging.getLogger('ADMIN').debug('%r object (dn: %r) loaded', self.name, obj.dn)
        return obj

    def _verify_univention_object_type(self, orig_udm_obj):
        # type: (univention.admin.handlers.simpleLdap) -> None
        """
        Check that the ``univentionObjectType`` of the LDAP objects matches the
        UDM module name.

        :param orig_udm_obj: original UDM object
        :raises univention.udm.exceptions.WrongObjectType: if ``univentionObjectType`` of the LDAP object
                does not match the UDM module name
        """
        uni_obj_type = getattr(orig_udm_obj, 'oldinfo', {}).get('univentionObjectType')
        if uni_obj_type and self.name.split('/', 1)[0] not in [uot.split('/', 1)[0] for uot in uni_obj_type]:
            raise WrongObjectType(dn=orig_udm_obj.dn, module_name=self.name, univention_object_type=', '.join(uni_obj_type))
