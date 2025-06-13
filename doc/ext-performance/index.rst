.. SPDX-FileCopyrightText: 2021-2025 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

.. _intro:

###############################################
Univention Corporate Server - Performance guide
###############################################

By default UCS is suitable for environments with up to 5,000 users. This
document describes configuration modifications which can increase performance in
larger environments.

.. _slapd:

*************************************************
OpenLDAP and listener/notifier domain replication
*************************************************

As a core element in the operation and administration of a UCS domain,
the performance of the LDAP server plays a central role in the overall
performance.

.. _slapd-index:

Indexes
=======

Comparable with other database systems, OpenLDAP uses indexes about
commonly requested attributes. For indexed attributes a search isn't
performed through the full database contents, but over an optimized
subsection.

With recent UCS versions, the indexes are occasionally expanded and
automatically activated. You can deactivate the automatic activation with the
UCR variable :envvar:`ldap/index/autorebuild`. In this case, you must set the
indexes manually to ensure that there is no loss of performance as a result.

Optimizing an LDAP index requires some thoughts before hand. It isn't
recommended to add all wanted attributes to the LDAP index. The index requires
maintenance and updating an index costs performance on write and sometimes also
on read operations. Evaluate your frequent searches and add the frequent used
search attributes to the LDAP index.

.. seealso::

   `Can more indexes improve performance? <https://www.openldap.org/faq/data/cache/42.html>`_ in the *OpenLDAP Faq-O-Matic*
      for more information about indexes influence the performance in OpenLDAP

To add LDAP attributes to an index, use the following steps:

#. Stop the OpenLDAP server.

#. Add or remove the LDAP attributes in the indexes by changing the respective
   UCR variable.

#. Run the command :command:`slapindex` to re-index the entries in the LDAP database.

#. Start the OpenLDAP server.

The UCR variables :envvar:`ldap/index/eq`, :envvar:`ldap/index/pres`,
:envvar:`ldap/index/sub`, and :envvar:`ldap/index/approx` control the LDAP index
configuration for the OpenLDAP server. After changing one of those variables,
UCR rewrites the OpenLDAP server configuration file.

Consider the following hints for your index:

* Negations don't use an index and therefore negation searches suffer
  performance.

* Range comparisons like ``>=`` and ``<=`` only work for non-string syntaxes
  like *integer* and *generalizedTime*. They use the :envvar:`eq
  <ldap/index/eq>` index for equality tests.

The following UCR variables control the LDAP index:

.. envvar:: ldap/index/approx

   This index tests for approximate matches. For example adding the ``uid``
   attribute to the index, it corresponds to the LDAP filter
   :samp:`uid~={value}` and finds all approximate objects.

   .. seealso::

      `Ldapwiki: ApproxMatch <https://ldapwiki.com/wiki/ApproxMatch>`_
         Overview about approximate match in OpenLDAP search filters defined in
         :rfc:`4511`.

.. envvar:: ldap/index/eq

   This index tests for equality. For example adding the ``uid`` attribute to
   the index, it corresponds to the LDAP filter :samp:`uid={value}` and finds
   all objects with exact that :samp:`{value}`. LDAP uses this index as fallback
   for a missing presence index in :envvar:`ldap/index/pres`.

.. envvar:: ldap/index/pres

   This index tests for the presence. For example adding the ``uid`` attribute
   to the index, it corresponds to the LDAP filter ``uid=*`` and finds all
   objects that have something within the ``uid`` attribute.

.. envvar:: ldap/index/sub

   This index runs a sub string search. For example adding the ``uid`` attribute
   to the index, it corresponds to the LDAP filter :samp:`uid={value}*` and
   finds all objects that match with the filter including the wildcard.

To determine whether OpenLDAP uses not-indexed variables, you can activate
OpenLDAP debug level ``-1`` and search for the string ``not indexed`` in the log
file :file:`/var/log/syslog`. For example:

.. code-block:: console

   $ ucr set ldap/debug/level=-1
   $ systemctl restart slapd
   $ grep 'not indexed' /var/log/syslog

.. _slapd-mdb:

Configuration of the database backend
=====================================

The memory mapped database (MDB) has been used for new installations
since UCS 4.0. The following flags have impact on the performance of
the MDB database and can be set with the |UCSUCRV|
:envvar:`ldap/database/mdb/envflags` (multiple values are separated
by spaces):

``nosync``
   Specify that on-disk database contents should not be immediately
   synchronized with in memory changes. Enabling this option may improve
   performance at the expense of data security. In particular, if the operating
   system crashes before changes are flushed, some number of transactions may be
   lost. By default, a full data flush/sync is performed when each transaction
   is committed.

``nometasync``
   Flush the data on a commit, but skip the sync of the meta
   page. This mode is slightly faster than doing a full sync, but can
   potentially lose the last committed transaction if the operating system
   crashes. If both ``nometasync`` and ``nosync`` are set, the ``nosync`` flag
   takes precedence.

``writemap``
   Use a writable memory map instead of just read-only. This speeds
   up write operations but makes the database vulnerable to corruption in case
   any bugs in ``slapd`` cause stray writes into the memory mapped region.

``mapasync``
   When using a writable memory map and performing flushes on each
   commit, use an asynchronous flush instead of a synchronous flush (the
   default). This option has no effect if ``writemap`` has not been set. It also
   has no effect if ``nosync`` is set.

``nordahead``
   Turn off file read-ahead. Usually the OS performs read-ahead on
   every read request. This usually boosts read performance but can be harmful
   to random access read performance if the system's memory is full and the DB
   is larger than RAM.

.. _slapd-acl:

OpenLDAP ACLs
=============

Access to the information contained in the LDAP directory is controlled by
access control lists (ACLs) on the server side. General information on the
configuration of ACLs in UCS can be found in :ref:`uv-manual:domain-ldap-acls`
in :cite:t:`ucs-manual`.

Nested groups are also supported. The |UCSUCRV| :envvar:`ldap/acl/nestedgroups`
can be used to deactivate the nested groups function for LDAP ACLs, which will
result in a speed increase for directory requests.

.. _listener:

|UCSUDL|
========

The |UCSUDL| can perform safety checks to prevent a user name being added into a
group twice. These checks add some overhead to replication and can be
deactivated by setting the |UCSUCR| variables :envvar:`listener/memberuid/skip`
and :envvar:`listener/uniquemember/skip` to ``no``. Starting with UCS 3.1 the
variables are not set and the checks are not activated any longer by default.

.. _initial-user-provisioning:

***********************************************************
Performance during initial provisioning of users and groups
***********************************************************

There are several ways in which you can provision users and groups into UCS.
Each method has its own performance implications and use cases.
Especially for large environments it's important that you choose an efficient method.

The following recommendations can improve performance when creating large
numbers of users and adding them to groups:

#. Use the *UDM Python library* in case you can do the provisioning locally on the UCS system.

   Use the :external+uv-dev-ref:ref:`udm-rest-api` to provision users and groups to a remote UCS system.

   It isn't recommended to use the UDM command line interface,
   because it's significantly slower than the previously mentioned options.

#. Create the users first and then the groups.
   This prevents unnecessary LDAP operations,
   because after the creation of the users, LDAP only needs to update the groups one time.

#. For the duration of the provisioning,
   deactivate the automatic update of the primary group, typically ``Domain Users``,
   when you create or remove a user.
   Set the |UCSUCR| variable :envvar:`directory/manager/user/primarygroup/update` to ``false``.

You can use the following example as a guide for using the *UDM Python library*:

.. code-block:: python

    #!/usr/bin/python3

    from univention.admin import modules, uldap
    from univention.config_registry import ucr


    lo, position = uldap.getAdminConnection()
    base = ucr['ldap/base']

    modules.update()

    users = modules.get('users/user')
    modules.init(lo, position, users)

    groups = modules.get('groups/group')
    modules.init(lo, position, groups)

    def create_user(name):
        position.setDn('cn=users,%s' % (base,))
        res = users.lookup(None, lo, "uid=%s" % name)
        if res:
            user = res[0]
        else:
            user = users.object(None, lo, position)
            user.open()
            user["lastname"] = name
            user["firstname"] = name
            user["password"] = "univention"
            user["username"] = name
            user.create()
        return user.dn

    def create_or_modify_group(name, members=None):
        """
        Parameters:
            name (str): name of the group
            members (list[str]): list of user DNs
        """
        position.setDn('cn=groups,%s' % (base,))
        res = groups.lookup(None, lo, "cn=%s" % name)
        if res and members:
            group = res[0]
            group.open()
            group["users"].extend(members)
            group.modify()
        else:
            group = groups.object(None, lo, position)
            group.open()
            group["name"] = name
            if members:
                group["users"] = members
            group.create()

    username_list = ["exampleuser1", "exampleuser2"]
    userdn_list = []
    for name in username_list:
        userdn = create_user(name)
        if userdn:
            userdn_list.append(userdn)

    if userdn_list:
        create_or_modify_group("examplegroup1", userdn_list)

.. _join:

******************************************
Performance issues during the join process
******************************************

The size of the UCS domain can have an impact on the duration of the
join process. Here is some information how to deal with such problems.

.. _join-samba:

Samba
=====

One of the join scripts for samba requires that the samba connector has
synchronized all domain objects into samba. This script has a timeout of ``3h``
(from UCS 4.4-7 on). This is sufficient for normal sized environments. But in
large environments this script may hit the timeout and abort the join process.
To increase the timeout the |UCSUCRV| :envvar:`create/spn/account/timeout` can
be set prior to the join process.

The join scripts ``97univention-s4-connector`` and ``98univention-samba4-dns``
wait for the replication of the DNS record of the joining system to verify
that the local Samba backed DNS server can answer requests for Active Directory
related requests.
By default the scripts wait for 600 seconds, but in case there are a lot of
objects that need to be replicated (e.g. DNS zones) then this default may be
too short.  In that case the timeout can be adjusted by setting the |UCSUCRV|
:envvar:`join/samba/dns/replication/timeout` to a bigger value before joining.

Samba traditionally uses TDB as backend database storage, that has an internal
32 bit address space limitation. UCS supports provisioning Samba using LMDB
instead, which doesn't have this strict limitation.
For more information, see :cite:t:`lmdb-doc`. :uv:kb:`18014` describes
how to migrate a productive UCS domain.

To use LMDB instead of TDB, set the corresponding |UCSUCRV|
:envvar:`samba/database/backend/store` to ``mdb`` before you install the app
:program:`Active Directory-compatible Domain Controller` in your UCS domain.

.. versionadded:: 5.2-0

   LMDB is the default for provisioning the Samba backend database.

The |UCSUCRV| :envvar:`samba/database/backend/store/size` defines the current
maximal size of the individual backend database store files and has the default
value of ``8GB``. Since there is one backend storage file per Active Directory
naming context, this amounts to a total of ``40GiB``. Take care that the storage
can accommodate this amount of space.

If required, you can increase the value monotonically. After changing the
|UCSUCRV|, you need to restart Samba, so that the value can take effect. You can
check the number of used storage pages, ``4KiB`` each, by running the command
:command:`mdb_stat -nef` on the individual files and calculating ``Number of
pages used`` minus ``Free pages``. The value at ``Max pages`` shows the current
effective limit. The backend storage files locate in :file:`/var/lib/samba/private/sam.ldb.d/`
and have the file extension :file:`.ldb`.

LMDB uses ``fdatasync`` to persist transactions.
As an optimization,
the operating system should only write modified memory pages to the disk.
On Amazon EC2,
writing modified memory pages can result in a higher number of IOPS as compared to TDB,
which can significantly slow down provisioning
and operations such as bulk group membership changes.
As a temporary speed-up option, Samba offers the ``ldb:nosync`` parameter.
Enabling ``ldb:nosync`` provides performance benefits during a provisioning phase.
However, don't enable ``ldb:nosync`` permanently during day-to-day operations,
as this compromises durability of changes committed to the SAM database.
Instead, consider other means of improving I/O performance.
To set this parameter,
use the following commands:

.. code-block:: console

   $ echo -e "\n[global}\n\tldb:nosync = true" >> /etc/samba/local.conf
   $ ucr commit /etc/samba/smb.conf
   $ /etc/init.d/samba restart

.. _group-cache:

*****************
Local group cache
*****************

By default the group cache is regenerated every time changes are made to a
group. This avoids cache effects whereby group memberships only become visible
for a service after the next scheduled group cache rewrite (by default once a
day and after 15 seconds of inactivity in the |UCSUDL|). In larger environments
with a lot of group changes, this function should be deactivated by setting the
|UCSUCRV| :envvar:`nss/group/cachefile/invalidate_on_changes` to ``false``. This
setting takes effect immediately and does not require a restart of the |UCSUDL|.

When the group cache file is being generated, the script verifies whether the
group members are still present in the LDAP directory. If only the |UCSUMC| is
used for the management of the LDAP directory, this additional check is not
necessary and can be disabled by setting the |UCSUCRV|
:envvar:`nss/group/cachefile/check_member` to ``false``.

.. _umc:

*********************
UCS management system
*********************

.. _umc-search-auto:

Disabling automatic search
==========================

By default all objects are automatically searched for in the domain management
modules of the |UCSUMC|. This behavior can be disabled by setting the |UCSUCRV|
:envvar:`directory/manager/web/modules/autosearch` to ``0``.

.. _umc-search-limit:

Imposing a size limit for searches
==================================

The |UCSUCRV| :envvar:`directory/manager/web/sizelimit` is used to impose an
upper limit for search results. If, e.g., this variable is set to ``2000`` (as is
the default), searching for more than 2000 users would not be performed and
instead the user is asked to refine the search.

.. _umc-open-file-limit:

Adjusting the limit on open file descriptors
============================================

The |UCSUCRV| :envvar:`umc/http/max-open-file-descriptors` is used to impose an
upper limit on open file descriptors of the
:program:`univention-management-console-web-server`. The default is ``65535``.

.. _umc-performance-multiprocessing:

Vertical performance scaling
============================

A single |UCSUMC| instance does not use multiple CPU cores by design, therefore
it can be beneficial to start multiple instances. Set the following |UCSUCRV|
:envvar:`umc/http/processes` and restart the
|UCSUMC|:

.. code-block:: console

   $ systemctl restart apache2 \
     univention-management-console-server

The number of instances to configure depends on the workload and the server
system. As a general rule of thumb these should not be higher than the machines
CPU cores. Good throughput values had resulted in tests with the following
combinations:

* Automatically detect available CPU cores: :envvar:`umc/http/processes`\ ``=0``

* 6 CPU cores: :envvar:`umc/http/processes`\ ``=3``

* 16 CPU cores: :envvar:`umc/http/processes`\ ``=15``

* 32 CPU cores: :envvar:`umc/http/processes`\ ``=25``

Note that the number of Apache processes may also need to be increased for the
customization to take effect.

.. _services:

*******************************
Further services and components
*******************************

Apache
======

In environments with many simultaneous accesses to the web server or Univention
Portal and Univention Management Console, it may be advisable to increase the
number of possible Apache processes or reserve processes. This can be achieved
via the UCR variables :envvar:`apache2/server-limit`,
:envvar:`apache2/start-servers`, :envvar:`apache2/min-spare-servers` and
:envvar:`apache2/max-spare-servers`. After setting, the Apache process must be
restarted via the command :command:`systemctl restart apache2`.

Detailed information about useful values for the UCR variables can be found at
`ServerLimit Directive
<https://httpd.apache.org/docs/2.4/en/mod/mpm_common.html#serverlimit>`_ and
`StartServers Directive
<https://httpd.apache.org/docs/2.4/en/mod/mpm_common.html#startservers>`_ in
:cite:t:`apache-httpd-2.4-docs`.

SAML
====

By default, SAML assertions are valid for ``300`` seconds, after which clients
must renew them to continue using them. In scenarios where refreshing SAML
assertions at such short intervals is too expensive for clients or servers, you
can increase the lifetime of SAML assertions. For instructions about how to
configure the SAML assertion lifetime, refer to
:external+ucs-keycloak-doc:ref:`app-saml-assertion-lifetime` in
:cite:t:`ucs-keycloak-doc`.

Carefully consider the increase of the SAML assertion lifetime, because it has
implications on the security.

Squid
=====

If the Squid proxy service is used with NTLM authentication, up to five running
NTLM requests can be processed in parallel. If many proxy requests are received
in parallel, the Squid user may occasionally receive an authentication error.
The number of parallel NTLM authentication processes can be configured with the
|UCSUCRV| :envvar:`squid/ntlmauth/children`.

BIND
====

BIND can use two different backend for its configuration: OpenLDAP or the
internal LDB database of Samba/AD. The backend is configured via the |UCSUCRV|
:envvar:`dns/backend`. On UCS Directory Nodes running Samba/AD, the backend **must
not** be changed to OpenLDAP.

When using the Samba backend, a search is performed in the LDAP for every DNS
request. With the OpenLDAP backend, a search is only performed in the directory
service if the DNS data has changed. For this reason, using the OpenLDAP backend
can reduce the load on a Samba/AD domain controller.

Kernel
======

In medium and larger environments the maximum number of open files allowed by
the Linux kernel may be set too low by default. As each instance requires some
unswappable memory in the Linux kernel, too many objects may lead to a resource
depletion and denial-of-service problems in multi-user environments. Because of
that the number of allowed file objects is limited by default.

The maximum number of open files can be configured on a per-user or per-group
basis. The default for all users can be set through the following |UCSUCRVs|:


:samp:`security/limits/user/{default}/hard/nofile`
   The hard limit defines the upper limit a user can assign to a
   process. The default is ``32768``.

:samp:`security/limits/user/{default}/soft/nofile`
   The soft limit defines the default settings for the processes of the
   user. The default is ``32768``.

A similar problem exists with the Inotify sub-system of the kernel, which can be
used by all users and applications to monitor changes in file systems.

:envvar:`kernel/fs/inotify/max_user_instances`
   The upper limit of inotify services per user ID. The default is ``511``.

:envvar:`kernel/fs/inotify/max_user_watches`
   The upper limit of files per user which can be watched by the inotify
   service. The default is ``32767``.

:envvar:`kernel/fs/inotify/max_queued_events`
   The upper limit of queued events per inotify instance. The default is
   ``16384``.

When the UCS system is part of a network of a very large number of devices,
it is possible that the ARP garbage collector thresholds are insufficient.
For those scenarios, raise the following thresholds:

:envvar:`kernel/net/ipv4/neigh/default/gc_thresh1`
   The threshold of ARP cache entries below which the garbage collector will not run. The default is 1024.

:envvar:`kernel/net/ipv4/neigh/default/gc_thresh2/`
   The threshold when garbage collector purges ARP cache entries that are older than 5 seconds. The default is 2048.

:envvar:`kernel/net/ipv4/neigh/default/gc_thresh3/`
   The maximum number of ARP cache entries that are non-permanent. The default is 4096.

Samba
=====

Samba uses its own mechanism to specify the maximum number of open files. This
can be configured through the |UCSUCRV| :envvar:`samba/max_open_files`. The
default is ``32808``.

If the log file :file:`/var/log/samba/log.smbd` contains errors like ``Failed to
init inotify - Too many open files``, the kernel and Samba limits should be
increased and the services should be restarted.

.. _systemstats:

System statistics
=================

The log file :file:`/var/log/univention/system-stats.log` can be checked for
further performance analyses. The system status is logged every *30 minutes*.
If more regular logging is required, it can be controlled via the UCR variable
:envvar:`system/stats/cron`.

.. _dovecot-high-performance:

Dovecot high-performance mode
=============================

|UCSUCS| configures Dovecot to run in *High-security mode* by default. Each
connection is served by a separate login process. This security has a price: for
each connection at least two processes must run.

Thus installations with 10.000s of users hit operating system boundaries. For
this case Dovecot offers the *High-performance mode*. To activate it, login
processes are allowed to serve more than one connection. To configure this run

.. code-block:: console

   $ ucr mail/dovecot/limits/imap-login/service_count=0

If ``client_limit=1000`` and ``process_limit=100`` are set, only 100 login
processes are started, but each serves up to 1000 connections — a total of
100.000 connections.

The cost of this is that if a login process is compromised, an attacker might
read the login credentials and emails of all users this login process is
serving.

To distribute the load of the login processes evenly between CPU cores,
:envvar:`mail/dovecot/limits/imap-login/process_min_avail` should be set to the
number of CPU cores in the system.

.. _udm-rest-api:

|UCSREST| performance scaling
=============================

A single |UCSREST| instance does not use multiple CPU cores by design,
therefore it can be beneficial to start multiple instances. By setting the
|UCSUCRV| :envvar:`directory/manager/rest/processes` the number of processes can
be increased. Afterwards the |UCSREST| needs to be restarted:

.. code-block:: console

   $ systemctl restart univention-directory-manager-rest

The number of instances to configure depends on the workload and the server
system. As a general rule of thumb these should not be higher than the machines
CPU cores. With :envvar:`directory/manager/rest/processes`\ ``=0`` all available CPU cores
are used.

.. _biblio:

************
Bibliography
************

.. bibliography::
