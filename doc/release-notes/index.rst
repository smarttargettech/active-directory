.. SPDX-FileCopyrightText: 2021-2025 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

############################################################################################
Release notes for the installation and update of Univention Corporate Server (UCS) |release|
############################################################################################

Publication date of UCS |release|: 2025-06-12

.. _relnotes-highlights:

******************
Release highlights
******************

With |UCSUCS| 5.2-2, the second patch level release for |UCSUCS| 5.2 is available.
It provides several feature improvements and extensions, properties, as well as, bug fixes.
Here is an overview of the most important changes:

* |UCSUCS| 5.2-2 introduces the ``univentionObjectIdentifier``: a globally unique identifier
  for all objects managed via |UCSUDM|.
  It simplifies object mapping to external systems and ensures consistent tracking across logs.
  The identifier is auto-generated for new objects; existing objects receive it during upgrade.

* :program:`Keycloak` *26* is now available in the App Center with enhanced security and new features.
  It comes with a new ``Ad Hoc Provisioning`` plugin which automatically creates Nubus user accounts.
  This enables seamless Single Sign-On access across connected applications
  for identities logging in via trusted external *IdPs* (e.g., :program:`Active Directory`).

* |UCSUCS| 5.2-2 delivers major performance gains in |UCSUDM|, notably for deleting computer objects and
  editing groups in large environments.
  A new diagnostic tool identifies LDAP database fragmentation — a key bottleneck in older,
  large deployments — and provides remediation guidance.

* Various components of the |UCSUMC| and App Center were hardened against cross-site scripting (XSS) attacks
  through stricter content sanitization and improved HTML encoding.

* |UCSUCS| 5.2-2 includes numerous security updates for packages such as ``curl``, ``glibc``, ``intel-microcode``,
  ``openssl``, ``firefox-esr``, ``Linux kernel``, and many others
  to ensure protection against the latest vulnerabilities.

.. _relnotes-update:

**********************
Notes about the update
**********************

Run the update in a maintenance window, because some services in the domain may
not be available temporarily. It's recommended that you test the update in a separate
test environment before the actual update. The test environment must be
identical to the production environment.

Depending on the system performance, network connection, and installed software,
the update can take anywhere from 30 minutes to several hours. For large
environments, consult :cite:t:`ucs-performance-guide`.

.. _relnotes-sequence:

Recommended update sequence for environments with more than one UCS system
==========================================================================

In environments with more than one UCS system, take the update sequence of the UCS
systems into account.

The authoritative version of the LDAP directory service operates on the |UCSPRIMARYDN|
and replicates to all the remaining LDAP servers of the UCS domain. As changes to the
LDAP schema can occur during release updates, the |UCSPRIMARYDN| must always be the
first system in the update order during a release update.

.. _relnotes-univention-object-identifier:

Initialization and indexing of the ``univentionObjectIdentifier``
=================================================================

During update an LDAP equality index is created for the ``univentionObjectIdentifier``
and for each object of class ``univentionObject``  the value of ``entryUUID`` is used
to initialize the attribute in case it is not yet present. Depending on the amount of
objects in the LDAP directory and limiting I/O factors this may take some time.

Please note that in Nubus environments with mixed UCS versions prior to |UCSUCS| 5.2-2, the
UDM on the old systems will not know how to properly manage the attribute for all
kinds of ``univentionObject``. |UCSUCS| 5.2-2 contains a plugin for UMC System Diagnostic
to check if all objects have the attribute and to fix those that don't.

.. _relnotes-bootloader:

********************************************************
Simultaneous operation of UCS and Debian on UEFI systems
********************************************************

Please note that simultaneous operation of UCS and Debian GNU/Linux on a UEFI
system starting with UCS 5.0 isn't supported.

The reason for this is the GRUB boot loader of |UCSUCS|, which partly uses the
same configuration files as Debian. An already installed Debian leads to the
fact that UCS can't boot (anymore) after the installation of or an update to UCS
5.0. A subsequent installation of Debian results in UCS 5.0 not being able to
boot. For more information, refer to :uv:kb:`17768`.

.. _relnotes-prepare:

*********************
Preparation of update
*********************

This section provides more information you need to consider before you update.

.. _relnotes-sufficient-disc-space:

Sufficient disk space
=====================

Also verify that you have sufficient disk space available for the update. A
standard installation requires a minimum of 6-10 GB of disk space. The update
requires approximately 1-2 GB additional disk space to download and install the
packages, depending on the size of the existing installation.

.. _relnotes-console-for-update:

Console usage for update
========================

For the update, sign in on the system's local console as user ``root``, and
initiate the update there. Alternatively, you can conduct the update using
|UCSUMC|.

If you want or have to run the update over a network connection, ensure that the
update continues in case of network disconnection. Network connection interrupts
may cancel the update procedure that you initiated over a remote connection. An
interrupted update procedure affects the system severely. To keep the update
running even in case of an interrupted network connection, use tools such as
:command:`tmux`, :command:`screen`, and :command:`at`. All UCS system roles have
these tools installed by default.

.. _relnotes-pre-update-checks:

Script to check for known update issues
=======================================

Univention provides a script that checks for problems which would prevent the
successful update of the system. You can download the script before the update
and run it on the UCS system.

.. code-block:: console

   # download
   $ curl -OOf https://updates.software-univention.de/download/univention-update-checks/pre-update-checks-5.2-2{.gpg,}

   # verify and run script
   $ apt-key verify pre-update-checks-5.2-2{.gpg,} && bash pre-update-checks-5.2-2

   ...

   Starting pre-update checks ...

   Checking app_appliance ...                        OK
   Checking block_update_of_NT_DC ...                OK
   Checking cyrus_integration ...                    OK
   Checking disk_space ...                           OK
   Checking hold_packages ...                        OK
   Checking ldap_connection ...                      OK
   Checking ldap_schema ...                          OK
   ...


.. _relnotes-post:

*****************************
Post processing of the update
*****************************

Following the update, you need to run new or updated join scripts. You can
either use the UMC module *Domain join* or run the command
:command:`univention-run-join-scripts` as user ``root``.

Subsequently, you need to restart the UCS system.

Please verify the PostgreSQL version on all UCS systems that updated to UCS 5.2.
As UCS 5.2 ships Version 15 of PostgreSQL, updated systems may need
migration from PostgreSQL 11.
For the recommended migration steps,
see :uv:kb:`22162`.

.. _relnotes-packages:

**************************
Notes on selected packages
**************************

The following sections inform about some selected packages regarding the update.

.. _relnotes-usage:

Collection of usage statistics
==============================

When using the *UCS Core Edition*, UCS collects anonymous statistics on the use
of |UCSUMC|. The modules opened get logged to an instance of the web traffic
analysis tool *Matomo*. Usage statistics enable Univention to better tailor the
development of |UCSUMC| to customer needs and carry out usability improvements.

You can verify the license status through the menu entry :menuselection:`License
--> License information` of the user menu in the upper right corner of |UCSUMC|.
Your UCS system is a *UCS Core Edition* system, if the *License information*
lists ``UCS Core Edition`` under *License type*.

UCS doesn't collect usage statistics, when you use an `Enterprise Subscription
<https://www.univention.com/products/prices-and-subscriptions/>`_ license such
as *UCS Base Subscription* or *UCS Standard Subscription*.

Independent of the license used, you can deactivate the usage statistics
collection by setting the |UCSUCRV| :envvar:`umc/web/piwik` to ``false``.

.. _relnotes-browsers:

Recommended browsers for the access to |UCSUMC|
===============================================

|UCSUMC| uses numerous JavaScript and CSS functions to display the web
interface. Your web browser needs to permit cookies. |UCSUMC| requires one of
the following browsers:

* Chrome as of version 131

* Firefox as of version 128

* Safari and Safari Mobile as of version 18

* Microsoft Edge as of version 128

Users running older browsers may experience display or performance issues.

.. _relnotes-changelog:

*********
Changelog
*********

You find the changes since UCS 5.2-0 in
:external+uv-changelog-5.2-2:doc:`index`.

.. _biblio:

************
Bibliography
************

.. bibliography::
