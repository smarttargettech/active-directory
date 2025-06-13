#!/bin/bash
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright (C) 2010-2025 Univention GmbH
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

# shellcheck disable=SC2317

export DEBIAN_FRONTEND=noninteractive

UPDATE_NEXT_VERSION="$1"
UPDATER_LOG="/var/log/univention/updater.log"
exec 3>>"$UPDATER_LOG"

###CHECKS###

readcontinue () {
	local var
	while true
	do
		echo -n "Do you want to continue [Y/n]? "
		read -r var
		case "$var" in
		''|y|Y) return 0 ;;
		n|N) return 1 ;;
		*) echo "" ;;
		esac
	done
}

echo
echo "HINT:"
echo "Please check the release notes carefully BEFORE updating to UCS ${UPDATE_NEXT_VERSION}:"
echo " English version: https://docs.software-univention.de/release-notes/${UPDATE_NEXT_VERSION}/en/"
echo " German version:  https://docs.software-univention.de/release-notes/${UPDATE_NEXT_VERSION}/de/"
echo
echo "Please also consider documents of following release updates and"
echo "3rd party components."
echo
if ! is_ucr_false update/warning/releasenotes && [ "${update_warning_releasenotes_internal:-}" != "no" ]
then
	if [ "$UCS_FRONTEND" = "noninteractive" ]; then
		echo "Update will wait here for 60 seconds..."
		echo "Press CTRL-c to abort or press ENTER to continue"
		# BUG: 'read -t' is the only bash'ism in this file, therefore she-bang has to be /bin/bash not /bin/sh!
		# shellcheck disable=SC2034
		read -r -t 60 somevar
	else
		readcontinue || exit 1
	fi
fi

echo ""

update_check_ssh () {
	[ -n "$SSH_CLIENT" ] || return 0
	[ "${update51_ignoressh:-}" = "yes" ] && return 0
	[ "${update52_ignoressh:-}" = "yes" ] && return 0
	echo "WARNING: You are logged in using SSH -- this may interrupt the update and result in an inconsistent system!"
	echo "Please log in under the console or re-run with \"--ignoressh\" to ignore it."
	return 1
}

update_check_term () {
	[ "$TERM" = "xterm" ] || return 0
	[ "${update51_ignoreterm:-}" = "yes" ] && return 0
	[ "${update52_ignoreterm:-}" = "yes" ] && return 0
	echo "WARNING: You are logged in under X11 -- this may interrupt the update and result in an inconsistent system!"
	echo "Please log in under the console or re-run with \"--ignoreterm\" to ignore it."
	return 1
}

# call custom preup script if configured
if [ -n "${update_custom_preup:-}" ]; then
	if [ -f "$update_custom_preup" ]; then
		if [ -x "$update_custom_preup" ]; then
			echo "Running custom preupdate script $update_custom_preup"
			"$update_custom_preup" "$UPDATE_NEXT_VERSION" >&3 2>&3
			echo "Custom preupdate script $update_custom_preup exited with exitcode: $?" >&3
		else
			echo "Custom preupdate script $update_custom_preup is not executable" >&3
		fi
	else
		echo "Custom preupdate script $update_custom_preup not found" >&3
	fi
fi

update_check_kernel () {
	is_ucr_true "update${VERSION}/pruneoldkernel" || return 0
	univention-prune-kernels
}

checks

# save ucr settings
[ -d "${updateLogDir:?}" ] ||
	install -m0700 -o root -d "$updateLogDir"
cp /etc/univention/base*.conf "$updateLogDir/"
ucr dump > "$updateLogDir/ucr.dump"

# move old initrd files in /boot
initrd_backup='/var/backups/univention-initrd.bak'
[ -d "$initrd_backup" ] ||
	install -m 0755 -o root -g root -d "$initrd_backup"
mv /boot/*.bak "$initrd_backup" >/dev/null 2>&1


# Bug #52923 #57296: disable fetchmail during update to prevent aborting update
if dpkg -l univention-fetchmail 2>&3 | grep ^ii  >&3 ; then
	if [ -z "$(ucr search "^fetchmail/autostart/update522$")" ] ; then
		ucr set fetchmail/autostart/update522="$(ucr get fetchmail/autostart)" >&3
	fi
	ucr set fetchmail/autostart=no >&3 2>&3
	systemctl stop fetchmail >&3 2>&3 || :
fi

# set KillMode of atd service to process to save the children from getting killed
# up to this point the updater process is a child of atd as well
install -m 0755 -o root -g root -d /etc/systemd/system/atd.service.d
echo -en "[Service]\nKillMode=process" > /etc/systemd/system/atd.service.d/update520.conf
systemctl daemon-reload

# ensure that en_US is included in list of available locales (Bug #44150)
case "${locale:-}" in
	*en_US*) ;;
	*) /usr/sbin/univention-config-registry set locale="${locale:+$locale }en_US.UTF-8:UTF-8" ;;
esac

# autoremove before the update
is_ucr_true update52/skip/autoremove ||
	DEBIAN_FRONTEND=noninteractive apt-get -y --allow-unauthenticated --allow-downgrades --allow-remove-essential --allow-change-held-packages autoremove >&3 2>&3

deactivate_old_package_sources () {
	# disable UCS 5.1 package sources to avoid mixing package versions during update
	local sources_lists
	sources_lists=("/etc/apt/sources.list.d/15_ucs-online-version.list" "/etc/apt/sources.list.d/20_ucs-online-component.list")
	for sources_list in "${sources_lists[@]}"; do
		mv "$sources_list" "${sources_list}.upgrade522.bak"
	done
}
deactivate_old_package_sources

# Pre-upgrade
preups=""
${update_commands_update:-false} >&3 2>&3
for pkg in $preups; do
	if dpkg -l "$pkg" 2>&3 | grep ^ii  >&3 ; then
		echo -n "Starting pre-upgrade of $pkg: "
		if ! ${update_commands_install:-false} "$pkg" >&3 2>&3
		then
			echo "failed."
			echo "ERROR: Failed to upgrade $pkg."
			exit 1
		fi
		echo "done."
	fi
done

echo "** Starting: apt-get -s -o Debug::pkgProblemResolver=yes dist-upgrade" >&3 2>&3
apt-get -s -o Debug::pkgProblemResolver=yes dist-upgrade >&3 2>&3

echo ""
echo "Starting update process, this may take a while."
echo "Check /var/log/univention/updater.log for more information."
date >&3
trap - EXIT

exit 0
