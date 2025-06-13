.. SPDX-FileCopyrightText: 2021-2025 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

.. _central-management-umc-introduction:

Introduction
============

.. _central-access:

Access
------

The |UCSWEB| can be opened on any UCS system via the URL
:samp:`https://{servername}/`. Alternatively, access is also possible via the server's
IP address. Under certain circumstances it may be necessary to access the
services over an insecure connection (e.g., if no SSL certificates have been
created for the system yet). In this case, ``http`` must be used instead of
``https`` in the URL. In this case, passwords are sent over the network in plain
text!

.. _central-browser-compatibility:

Browser compatibility
---------------------

The |UCSWEB| uses numerous JavaScript and CSS functions.
Your browser must allow the use of cookies.
|UCSWEB| supports the following browsers:

* :program:`Google Chrome` as of version 131

* :program:`Mozilla Firefox` as of version 128

* :program:`Microsoft Edge` as of version 128

* :program:`Apple Safari` and :program:`Apple Safari Mobile` as of version 18

Users with older browsers may experience display problems
or |UCSWEB| doesn't work at all.

The |UCSWEB| is available in German and English.
If you chose French as language during installation from the ISO image,
you can also use French.

You can select a different language through :guilabel:`Change language` in the user menu.

.. _central-theming:

Switching between dark and light theme for |UCSWEB|\ s
------------------------------------------------------

All |UCSWEB|\ s have a dark and a light theme that can be switched between with
the |UCSUCRV| :envvar:`ucs/web/theme`. The value of :envvar:`ucs/web/theme`
corresponds to a CSS file under :file:`/usr/share/univention-web/themes/` with
the same name (without file extension). For example, setting
:envvar:`ucs/web/theme` to ``light`` will use
:file:`/usr/share/univention-web/themes/light.css` as theme for all |UCSWEB|\ s.

.. _central-theming-custom:

Creating a custom theme/Adjusting the design of |UCSWEB|\ s
-----------------------------------------------------------

To customize a theme for |UCSWEB|\ s don't edit the files
:file:`/usr/share/univention-web/themes/dark.css` and
:file:`/usr/share/univention-web/themes/light.css`,
because UCS upgrades can overwrite your changes.
Instead, copy one of these files to, for example,
:file:`/usr/share/univention-web/themes/mytheme.css`
and set the |UCSUCRV| :envvar:`ucs/web/theme` to ``mytheme``.

The files
:file:`/usr/share/univention-web/themes/dark.css`
and
:file:`/usr/share/univention-web/themes/light.css`
contain the same list of `CSS variables <mozilla-css-custom-properties_>`_.
Other CSS files use these CSS variables.
These CSS variables are the supported layer of configurability for |UCSWEB|\ s.
The names and use cases for these variables don't change between UCS upgrades,
but Univention may add additional names and use cases.

Some |UCSWEB|\ s import their own local :file:`custom.css` file
which you can use to adjust the design of the following pages:

* For :ref:`central-user-interface`: :file:`/usr/share/univention-management-console-login/css/custom.css`

* For :ref:`central-portal`: :file:`/usr/share/univention-portal/css/custom.css`

The files are empty during the installation of UCS.
UCS updates don't change these files.

.. important::

   Be aware, however, that a given `CSS selector <mozilla-css-selectors_>`_
   may break when installing a UCS update.

.. _central-management-umc-feedback:

Feedback on UCS
---------------

By choosing the :menuselection:`Help --> Feedback` option in the upper right
menu, you can provide feedback on UCS via a web form.

.. _central-management-umc-matomo:

Collection of usage statistics
------------------------------

Anonymous usage statistics on the use of the |UCSWEB| are collected when using
the *core edition* version of UCS (which is generally used for evaluating UCS).
Further information can be found in :uv:kb:`Data collection in Univention
Corporate Server <6701>`.
