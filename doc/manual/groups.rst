.. SPDX-FileCopyrightText: 2021-2025 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

.. _groups:

****************
Group management
****************

Permissions in UCS are predominantly differentiated between on the basis of
*groups*. Groups are stored in the LDAP and are thus identical on all systems.
Groups can contain not only user accounts, but can also optionally accept
computer accounts.

In addition, there are also local user groups on each system, which are
predominantly used for hardware access. These are not managed through the
|UCSUMS|, but saved in the :file:`/etc/group` file.

.. note::

   The group management is part of Univention Nubus in the *Directory Manager* component.
   For more information about Nubus, refer to :ref:`introduction-nubus`

.. _groups-assignement:

User group assignments
======================

The assignment of users to groups is performed in two ways:

* A selection of groups can be assigned to a user in the user management, see
  :ref:`users-management`.

* A selection of users can be assigned to a group in the group management, see
  :ref:`groups-management`.

.. _groups-recommendation-group-name:

Recommendation for group name definition
========================================

One very important and required attribute for groups is the group name. To
avoid conflicts with the different tools handling groups in UCS, adhere to the
following recommendations for the definition of group names:

* Only use upper and lower case letters (``A-Za-z``), digits (``0-9``) the
  hyphen (``-``) and space from the ASCII character set for group names.

* The group name starts with a letter from the ASCII character set. The space is
  not allowed as first or last character. The hyphen is not allowed as last
  character.

* In UCS the group name has at least a length of 4 characters and at most 20
  characters.

The recommendation results in the following regular expression::

   ^[A-Za-z][A-Za-z0-9 -]{2,18}[A-Za-z0-9]$

Consider the recommendation as a guideline and not a rule and keep potential
side-effects in mind when defining group names outside the recommendation.

.. _groups-management:

Managing groups via |UCSUMC| module
===================================

Groups are managed in the UMC module :guilabel:`Groups` (see
:ref:`central-user-interface`).

.. _create-group:

.. figure:: /images/create-group.*
   :alt: Creating a group via UMC module

   Creating a group via UMC module

.. _groups-management-table-general:

Group management module - General tab
-------------------------------------

.. _groups-management-table-general-tab:

.. list-table:: *General* tab
   :header-rows: 1
   :widths: 30 70

   * - Attribute
     - Description

   * - Name (*)
     - Defines the name of the group. For recommended characters for the group
       name, see :ref:`groups-recommendation-group-name`.

       By default it is not possible to create a group with the same name as an
       existing user. If the |UCSUCRV|
       :envvar:`directory/manager/user_group/uniqueness` is set to ``false``,
       this check is removed.

   * - Description
     - A description of the group can be entered here.

   * - Users
     - This input field can be used for adding users as members to the group.

   * - Groups
     - On this input field, other groups can be added as members of the current
       group (groups in groups).

.. _groups-management-table-advanced:

Group management module - Advanced settings tab
-----------------------------------------------

.. _groups-management-table-advanced-tab:

.. list-table:: *Advanced settings* tab
   :header-rows: 1
   :widths: 30 70

   * - Attribute
     - Description

   * - Mail
     - These options define a mail group and are documented in the
       :ref:`mail-management-mailgroups`.

   * - Host members
     - This field can be used for accepting computers as members of the group.

   * - Nested groups
     - The current group can be added as a member to other groups here (groups
       in groups).

   * - Group ID
     - If a group is to be assigned a certain group ID, the ID in question can
       be entered in this field. Otherwise the next available group ID will be
       automatically assigned when adding the group. The group ID cannot be
       subsequently changed. When editing the group, the group ID will be
       represented in gray.

       The group ID may consist of integers between 1000 and 59999 and between
       65536 and 100000.

   * - :menuselection:`Windows --> Relative ID`
     - The relative ID (RID) is the local part of the Security ID (SID) and is
       used in Windows and Samba domains. If a group is to be assigned a certain
       RID, the ID in question can be entered in this field. Otherwise a RID
       will be automatically assigned.

       The RID cannot be subsequently changed. When editing the group, the group
       ID will be represented in gray.

       The RIDs below 1000 are reserved for standard groups and other special
       objects.

       When Samba/AD is used, the RID is generated by Samba and cannot be
       specified.

   * - :menuselection:`Windows --> group type`
     - This group type is evaluated when the user logs in to a Samba/AD-based
       domain. Three types of Windows groups can be distinguished:

       Domain Groups
         are known across the domain. This is the default group type.

       Local groups
         are only relevant on Windows servers. If a local group is created on a
         Windows server, this group is known solely to the server; it is not
         available across the domain. UCS, in contrast, does not differentiate
         between local and global groups. After taking over an AD domain, local
         groups in UCS can be handled in the same way as global groups.

       Well-known group
         This group type covers groups preconfigured by Samba/Windows servers
         which generally have special privileges, e.g., ``Power Users``.

   * - :menuselection:`Windows --> AD group type`
     - This group type is only evaluated when the user logs in to a
       Samba/AD-based domain (which offers Active Directory domain services).
       These groups are described in :ref:`groups-adgroups`.

   * - :menuselection:`Windows --> Samba privileges`
     - This input mask can be used to assign Windows system rights to a group,
       e.g., the right to join a Windows client in the domain. This function is
       documented in :ref:`users-management`.

.. _groups-management-table-options:

Group management module - Options settings tab
-----------------------------------------------

.. _groups-management-table-options-tab:

This tab is only available when adding groups, not when editing groups. Certain
LDAP object classes for the group can be de-selected here. The entry fields for
the attributes of these classes can then no longer be filled in.

.. list-table:: *Options* tab
   :header-rows: 1
   :widths: 30 70

   * - Attribute
     - Description

   * - Samba group
     - This checkbox indicates whether the group contains the object class
       ``sambaGroupMapping``.

   * - POSIX group
     - This checkbox indicates whether the group contains the object class
       ``posixGroup``.

.. _groups-nested:

Group nesting with groups in groups
===================================

UCS supports group nesting (also known as "groups in groups"). This simplifies
the management of the groups. For example, if two locations are managed in one
domain, two groups can be formed ``IT staff location A`` and ``IT staff location
B``, to which the user accounts of the location's IT staff can be assigned
respectively.

To create a cross-location group, it is then sufficient to define the groups
``IT staff location A`` and ``IT staff location B`` as members.

Cyclic dependencies of nested groups are automatically detected and refused.
This check can be disabled with the |UCSUCRV|
:envvar:`directory/manager/web/modules/groups/group/checks/circular_dependency`.
Cyclic memberships must also be avoided in direct group changes without the
|UCSUMS|.

The resolution of nested group memberships is performed during the generation of
the group cache (see :ref:`groups-cache`) and is thus transparent for
applications.

.. _groups-cache:

Local group cache
=================

The user and computer information retrieved from the LDAP is cached by
the Name Server Cache Daemon (NSCD), see :ref:`computers-nscd`.

Since UCS 3.1, the groups are no longer cached via the NSCD for
performance and stability reasons; instead they are now cached by the
NSS module :program:`libnss-extrausers`. The group
information is automatically exported to the
:file:`/var/lib/extrausers/group` file by the
:file:`/usr/lib/univention-pam/ldap-group-to-file.py`
script and read from there by the NSS module.

In the basic setting, the export is performed once a day by a cron job
and is additionally started if the |UCSUDL| has been inactive for 15
seconds. The interval for the cron update is configured in Cron syntax
(see :ref:`cron-local`) by the |UCSUCRV|
:envvar:`nss/group/cachefile/invalidate_interval`. This listener
module can be activated/deactivated via the |UCSUCRV|
:envvar:`nss/group/cachefile/invalidate_on_changes`
(``true``/``false``).

When the group cache file is being generated, the script can verify
whether the group members are still present in the LDAP directory. If
not only UMC modules are used for user management, this additional check
can be can be enabled by setting the |UCSUCRV|
:envvar:`nss/group/cachefile/check_member` to
``true``.

.. _groups-adgroups:

Synchronization of Active Directory groups when using Samba/AD
==============================================================

If Samba/AD is used, the group memberships are synchronized between the
Samba/AD directory service and the OpenLDAP directory service by the
Univention S4 connector, i.e., each group on the UCS side is associated
with a group in Active Directory. General information on the Univention
S4 connector can be found in :ref:`windows-s4-connector`.

Some exceptions are formed by the *pseudo groups*,
sometimes also called system groups. These are only managed internally
by Active Directory/Samba, e.g., the ``Authenticated Users`` group includes a list
of all the users currently logged on to the system. Pseudo groups are
stored in the UCS directory service, but they are not synchronized by
the Univention S4 connector and should usually not be edited. This
applies to the following groups:

* ``Anonymous Logon``
* ``Authenticated Users``
* ``Batch``
* ``Creator Group``
* ``Creator Owner``
* ``Dialup``
* ``Digest Authentication``
* ``Enterprise Domain Controllers``
* ``Everyone``
* ``IUSR``
* ``Interactive``
* ``Local Service``
* ``NTLM Authentication``
* ``Network Service``
* ``Network``
* ``Nobody``
* ``Null Authority``
* ``Other Organization``
* ``Owner Rights``
* ``Proxy``
* ``Remote Interactive Logon``
* ``Restricted``
* ``SChannel Authentication``
* ``Self``
* ``Service``
* ``System``
* ``Terminal Server User``
* ``This Organization``
* ``World Authority``

In Active Directory/Samba, a distinction is made between the following
four AD group types. These group types can be applied to two types of
groups; *security groups* configure permissions
(corresponding to the UCS groups), whilst *distribution
groups* are used for mailing lists:

Local
   *Local* groups only exist locally on a host. A local group created in
   Samba/AD is synchronized by the Univention S4 Connector and thus also appears
   in the UMC module :guilabel:`Groups`. There is no need to create local groups
   in the UMC module.

Global
   *Global* groups are the standard type for newly created groups in the UMC
   module :guilabel:`Groups`. A global group applies for one domain, but it can
   also accept members from other domains. If there is a trust relationship with
   a domain, the groups there are displayed and permissions can be assigned.
   However, the current version of UCS does not support multiple domains/forests
   or outgoing trust relationships.

Domain local
   *Domain local* groups can also adopt members of other domains (insofar as
   there is a trust relationship in place or they form part of a forest). Local
   domain groups are only shown in their own domain though. However, the current
   version of UCS does not support multiple domains/forests or outgoing trust
   relationships.

Universal
   *Universal* groups can adopt members from all domains and these members are
   also shown in all the domains of a forest. These groups are stored in a
   separate segment of the directory service, the so-called *global catalog*.
   Domain forests are currently not supported by Samba/AD.

.. _groups-memberof:

Overlay module for displaying the group information on user objects
===================================================================

In the UCS directory service, group membership properties are only saved in the
group objects and not in the respective user objects. However, some applications
expect group membership properties at the user objects (in the attribute
``memberOf``). An overlay module in the LDAP server makes it possible
to present these attributes automatically based on the group information. The
additional attributes are not written to the LDAP, but displayed on the fly by
the overlay module if a user object is queried.
