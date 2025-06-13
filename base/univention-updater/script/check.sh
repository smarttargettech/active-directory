#!/bin/bash
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright (C) 2018-2025 Univention GmbH
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

# shellcheck disable=SC2154,SC2317
#
UPDATER_LOG="/var/log/univention/updater.log"
###CHECKS_ONLY###
if [ -z "${UPDATE_NEXT_VERSION:-}" ]
then
	# stdout to screen and log
	exec > >(exec tee -ia "$UPDATER_LOG")
fi
###CHECKS_COMMON###

VERSION="52"  # we don't put 51 here because the upgrade should look like upgrading to UCS 5.2
VERSION_NAME="5.2"
MIN_VERSION="5.0-7"
MIN_VERSION_SYSTEM="5.2-1-39"

# shellcheck disable=SC2034
updateLogDir="/var/univention-backup/update-to-${UPDATE_NEXT_VERSION:-$VERSION_NAME}"

echo
echo "Starting $0 ($(date)):"

eval "$(univention-config-registry shell)"
# shellcheck source=/dev/null
. /usr/share/univention-lib/ucr.sh || exit $?

conffile_is_unmodified () {
	# conffile_is_unmodified <conffile>
	# returns exitcode 0 if given conffile is unmodified
	local chksum fnregex testchksum
	chksum="$(md5sum "${1:?}" | awk '{print $1}')"
	fnregex="$(python3 -c 'import re, sys; print(re.escape(sys.argv[1]))' "$1")"
	for testchksum in $(dpkg-query -W -f '${Conffiles}\n' | sed -nre "s,^ $fnregex ([0-9a-f]+)( .*)?$,\\1,p") ; do
		[ "$testchksum" = "$chksum" ] &&
			return 0
	done
	return 1
}

ignore_check () {
	local var="$1"
	is_ucr_true "$var" ||
		return 1
	echo -n "Ignoring test as requested by $var " 1>&2
	return 0
}

have () {
	command -v "$1" >/dev/null 2>&1
}

die () {
	echo "${0##*/}: $*"
	exit 1
}

# check for hold packages
update_check_hold_packages () {
	local var="update$VERSION/ignore_hold"
	ignore_check "$var" && return 100
	hold_packages=$(LC_ALL=C dpkg -l | awk '/^h/{print $2}')
	[ -n "$hold_packages" ] || return 0

	echo "	WARNING: Some packages are marked as hold -- this may interrupt the update and result in an inconsistent system!"
	echo "	Please check the following packages and unmark them or set the UCR variable $var to yes"
	for hp in $hold_packages; do
		echo "	- $hp"
	done
	echo
	echo "	This check can be disabled by setting the UCR variable '$var' to 'yes'."
	return 1
}

# Bug #44650 begin - check slapd on Managed Node
update_check_slapd_on_member () {
	local var="update$VERSION/ignore_slapd_on_member"
	ignore_check "$var" && return 100
	have slapd ||
		return 0
	[ "$server_role" = "memberserver" ] ||
		return 0

	echo "	The ldap server is installed on your Managed Node. This is not supported"
	echo "	and may lead to problems during the update. Please deinstall the package"
	echo "	*slapd* from this system with either the command line tool univention-remove "
	echo "	  -> univention-remove slapd"
	echo "	or via the package management in the Univention Management Console."
	echo "	Make sure that only the package slapd gets removed!"
	echo
	echo "	This check can be disabled by setting the UCR variable '$var' to 'yes'."
	return 1
}

update_check_ldap_schema () {
	[ -x /usr/sbin/slapschema ] ||
		return 0
	/usr/sbin/slapschema -f /etc/ldap/slapd.conf -c 1>&2 &&
		return 0

	echo "	There is a problem with the LDAP schema on this system."
	echo "	Please check $UPDATER_LOG or run 'slapschema' manually."
	return 1
}

update_check_valid_machine_credentials () {
	[ -f /var/univention-join/joined ] ||
		return 0
	[ -f /etc/machine.secret ] &&
		return 0

	echo "	The credentials for the machine account could not be found!"
	echo "	Please re-join this system."
	return 1
}

update_check_ldap_connection () {
	case "$server_role" in
	'') return 0 ;;
	esac
	[ -n "$ldap_base" ] || return 0
	[ -n "$ldap_hostdn" ] || return 0

	ldapsearch -x -D "$ldap_hostdn" -y /etc/machine.secret -b "$ldap_base" -s base &>/dev/null
	[ $? -eq 49 ] ||
		return 0

	echo "	A LDAP connection to the configured LDAP servers with the machine"
	echo "	account has failed (invalid credentials)!"
	echo "	This MUST be fixed before the update can continue."
	echo "	This problem can be corrected by setting the content of the file"
	echo "	/etc/machine.secret to the password of the computer object using"
	echo "	Univention Management Console."
	return 1
}


# Bug #58045 Loading the database from the LDIF dump failed - could not parse entry (line=xxx)
# Note: This check should be enabled only for major and minor updates
_disabled_verify_translog_schema () {
  local var="update$VERSION/verify_translog_schema"
  ignore_check "$var" && return 100
  if [ "$server_role" != "domaincontroller_master" ] && [ "$server_role" != "domaincontroller_backup" ];
  then
    return 0
  fi
  if slapcat -f /etc/ldap/slapd.conf  -n 3 | slapadd -f /etc/ldap/slapd.conf -n 3 -u; then
    return 0
  fi
  echo "	There is a problem with the translog schema on this system."
  echo "	Please check $UPDATER_LOG or run 'slapcat -f /etc/ldap/slapd.conf  -n 3 | slapadd -f /etc/ldap/slapd.conf -n 3 -u' manually."
  echo "	Please see <https://help.univention.com/t/23981> for more information."
  return 1
}


_migrate_openldap_bdb_failed () {
	local msg="$1"
	local revert="${2:-false}"
	echo "$(date) The migration failed with: $msg"
	if $revert; then
		if [ -e /var/lib/univention-ldap/ldap.BACKUP/uid.bdb ]; then
			echo "$(date) Reverting to BDB database"
			service slapd stop
			mv /var/lib/univention-ldap/ldap.BACKUP/* /var/lib/univention-ldap/ldap/
			ucr set ldap/database/type=bdb
			service slapd start
		fi
	fi
	echo "$(date) Consult the Univention Support or <https://help.univention.com/t/22322> for help!"
	exit 1
}

migrate_openldap_bdb () {
	local database_size available_size mdb_max_size
	update_check_openldap_bdb >/dev/null && echo "$(date) already migrated to mdb, nothing to do" && return 0
	echo "$(date) starting BDB to MDB migration"
	database_size="$(du -s /var/lib/univention-ldap/ldap | awk '{print $1}')"
	available_size="$(LC_ALL=C df --output="avail" /var/lib/univention-ldap | tail -n 1)"
	mdb_max_size="${ldap_database_mdb_maxsize:-4295000000}"
	# only if available disk space is 10 times the size of the database
	test "$available_size" -ge "$((database_size*10))" || \
		_migrate_openldap_bdb_failed "not enough disk space for migration"
	# only if mdb maxsize is 3 times bigger then current size of the database
	test "$mdb_max_size" -ge "$((database_size*3))" || \
		_migrate_openldap_bdb_failed "max size for mdb database does not fit, raise max size by setting UCRV ldap/database/mdb/maxsize"
	univention-ldapsearch -LLL "uid=$(hostname)\$" >/dev/null || \
		_migrate_openldap_bdb_failed "slapd is not running"
	service slapd stop || \
		_migrate_openldap_bdb_failed "error stopping slapd"
	slapcat -l /var/lib/univention-ldap/database.ldif || \
		_migrate_openldap_bdb_failed "error during slapcat"
	mkdir -p /var/lib/univention-ldap/ldap.BACKUP || \
		_migrate_openldap_bdb_failed "error creating backup dir"
	mv /var/lib/univention-ldap/ldap/* /var/lib/univention-ldap/ldap.BACKUP/ || \
		_migrate_openldap_bdb_failed "error moving old database to backup dir"
	ucr set ldap/database/type=mdb
	slapadd -l /var/lib/univention-ldap/database.ldif || \
		_migrate_openldap_bdb_failed "error importing database" true
	service slapd start || \
		_migrate_openldap_bdb_failed "error starting slapd" true
	univention-ldapsearch -LLL "uid=$(hostname)\$" >/dev/null || \
		_migrate_openldap_bdb_failed "error during LDAP lookup" true
	echo "$(date) migration to MDB done"
}

update_check_role_package_removed () {
	local role_package
	case "$server_role" in
	domaincontroller_master) role_package="univention-server-master" ;;
	domaincontroller_backup) role_package="univention-server-backup" ;;
	domaincontroller_slave) role_package="univention-server-slave" ;;
	memberserver) role_package="univention-server-member" ;;
	*) return 0 ;;
	esac

	LC_ALL=C ${update_commands_distupgrade_simulate:-false} 2>&1 | grep -q "^Remv $role_package" ||
		return 0

	echo "	The pre-check of the update calculated that the"
	echo "	essential software package $role_package will be removed"
	echo "	during the upgrade. This could result into a broken system."
	echo
	# If you really know what you are doing, you can skip this check by
	# setting the UCR variable update/commands/distupgrade/simulate to /bin/true.
	# But you have been warned!
	# In this case, you have to set the UCR variable after the update back
	# to the old value which can be get from /var/log/univention/config-registry.replog
	echo "	Please contact Univention Support in case you have an Enterprise"
	echo "	Subscription. Otherwise please try Univention Help"
	echo "	<https://help.univention.com/>"
	return 1
}

# Bug #56134 Bug #56651 Bug #56367 Bug #52048 Bug #56765
# Admin must agree to remove these:
# Issue univention/dev/ucs#1885
#  we removed univentionSAMLServiceProvider, univentionSAMLIdpConfig and
#  univentionOIDCService, we remove these objects in check_keycloak_migration
#  but as we support mixed environments (5.0/5.2) we have to support these
#  objects in 5.2 too (not create in 5.2)
#  we can remove them completely with the next version (6.0)
declare -a legacy_ocs_structural=(
	'(structuralObjectClass=univentionNagiosTimeperiodClass)'
)
declare -a legacy_ocs_auxiliary=(
	'(objectClass=univentionVirtualMachineGroupOC)'  # EA
	'(objectClass=univentionVirtualMachineHostOC)'  # EA
)
# These are auto-removed:
declare -a obsolete_objectclasses=(
	'(structuralObjectClass=univentionPortalEntry)'
	'(structuralObjectClass=univentionPortalCategory)'
	'(structuralObjectClass=univentionPortal)'
	'(structuralObjectClass=univentionVirtualMachineCloudType)'
	'(structuralObjectClass=univentionVirtualMachineCloudConnection)'
	'(structuralObjectClass=univentionVirtualMachineProfile)'
	'(structuralObjectClass=univentionVirtualMachine)'
	'(&(objectClass=univentionUDMProperty)(cn=UVMMGroup))'  # EA
	'(&(objectClass=univentionUDMProperty)(cn=ManageableBy))'  # EA
	'(&(objectClass=univentionUDMModule)(cn=uvmm/profile))'  # UDM module
	'(&(objectClass=univentionUDMModule)(cn=uvmm/info))'  # UDM module
	'(&(objectClass=univentionUDMModule)(cn=uvmm/cloudtype))'  # UDM module
	'(&(objectClass=univentionUDMModule)(cn=uvmm/cloudconnection))'  # UDM module
	'(&(objectClass=univentionUDMSyntax)(cn=univention-virtual-machine-manager-schema))'  # UDM syntax
	'(&(objectClass=univentionLDAPExtensionACL)(cn=66univention-ldap-server_acl-master-uvmm))'  # LDAP ACL's
	'(&(objectClass=univentionLDAPExtensionSchema)(cn=univention-virtual-machine-manager))'  # LDAP schema
)

delete_legacy_objects () {
	local filter ldif oc
	[ -r /etc/ldap.secret ] || die "Cannot get LDAP credentials from '/etc/ldap.secret'"

	echo "> Removing structural objects"
	for filter in "${legacy_ocs_structural[@]}"
	do
		echo ">> $filter"
		univention-ldapsearch -LLL "$filter" 1.1 |
			sed -ne 's/^dn: //p' |
			ldapdelete -x -D "cn=admin,${ldap_base:?}" -y /etc/ldap.secret -c
	done

	echo "> Removing auxiliary data"
	ldif="$(mktemp)"
	for filter in "${legacy_ocs_auxiliary[@]}"
	do
		echo ">> $filter"
		oc="${filter#(objectClass=}"  # the closing parenthesis is stripped below!
		univention-ldapsearch -LLL -b 'cn=Subschema' -s base objectClasses -E mv="${filter/objectClass=/objectClasses=}" >"$ldif"
		sed -rne 's/objectClasses: //;T;s/.* (MUST|MAY)//;s/ (MUST|MAY|[($)])//g;s/^ +| +$//g;s/ +/\n/g;s/\S+/replace: &\n-/g;a delete: objectClass\nobjectClass: '"${oc%)}" -e p -i "$ldif"
		[ -s "$ldif" ] || continue
		univention-ldapsearch -LLL "$filter" 1.1 |
			sed -e "/^dn: /r $ldif" |
			ldapmodify -x -D "cn=admin,${ldap_base:?}" -y /etc/ldap.secret -c
	done
	rm -f "$ldif"
}

# Some objects get deleted automatically in preup.sh
# Objects are found by queries based on obsolete_objectclasses
# references to these deleted objects are also deleted if the
# reference is in an attribute named univentionPolicyReference or
# univentionPolicyObject
delete_obsolete_objects () {
	[ "$server_role" != "domaincontroller_master" ] && return 0
	[ -r /etc/ldap.secret ] || die "ERROR: Cannot get LDAP credentials from '/etc/ldap.secret'"
	[ -d "${updateLogDir:?}" ] ||
		install -m0700 -o root -d "$updateLogDir" ||
		die "ERROR: Could not create $updateLogDir"
	local filter ldif oc backupfile
	backupfile="${updateLogDir}/removed_with_ucs5_$(date +%Y-%m-%d-%S).ldif"

	echo "> Several LDAP objects are no longer supported with UCS 5.2 and are removed automatically."
	echo "> An LDIF file of removed objects is available: ${backupfile}"
	install -b -m 400 /dev/null "${backupfile}"
	echo "> Removing objects with obsolete objectClasses"
	for filter in "${obsolete_objectclasses[@]}"
	do
		echo ">> $filter"
		# check if object is referenced anywhere in a policy
		local object_dns
		object_dns="$(univention-ldapsearch -LLL "$filter" | sed -ne 's/^dn: //p')"
		[ -z "$object_dns" ] && continue
		echo "Deleting object(s) with dn: $object_dns"
		# Iterate over all found objects matching the ldap filter to find references
		while IFS= read -r object_dn; do
			# References to objects can come in two attributes
			for policy_reference_type in univentionPolicyReference univentionPolicyObject; do
				local policy_references dn="$object_dn"
				dn="${dn//\\/\\5c}"
				dn="${dn//\*/\\2a}"
				dn="${dn//\(/\\28}"
				dn="${dn//\)/\\29}"
				policy_references="$(univention-ldapsearch -LLL "($policy_reference_type=$dn)" 1.1 | sed -ne 's/^dn: //p')"
				[ -z "$policy_references" ] && continue
				while read -r referencing_dn; do
					echo "# Deleting reference to $object_dn from $referencing_dn" | tee -a "${backupfile}"
					ldapmodify -x -D "cn=admin,${ldap_base:?}" -y /etc/ldap.secret <<__EOF__
dn: $referencing_dn
changetype: modify
delete: $policy_reference_type
$policy_reference_type: $object_dn
__EOF__
				done <<< "$policy_references"
			done # for policy_reference_type
		done <<< "$object_dns" # while read object_dn
		univention-ldapsearch -LLL "$filter" "*" + |
			tee -a "${backupfile}" |
			sed -ne 's/^dn: //p' |
			ldapdelete -x -D "cn=admin,${ldap_base:?}" -y /etc/ldap.secret -c || die 'ERROR: could not remove obsolete objects'
	done
}

# check that no apache configuration files are manually adjusted; Bug #43520
update_check_overwritten_umc_templates () {
	local var="update$VERSION/ignore_apache_template_checks"
	ignore_check "$var" && return 100
	univention-check-templates 2>/dev/null |
		grep /etc/univention/templates/files/etc/apache2/sites-available/ 1>&2 ||
		return 0

	echo "	WARNING: There are modified Apache configuration files in /etc/univention/templates/files/etc/apache2/sites-available/."
	echo "	Please restore the original configuration files before upgrading and apply the manual changes again after the upgrade succeeded."
	echo
	echo "	This check can be disabled by setting the UCR variable '$var' to 'yes'."
	return 1
}

update_check_package_status () {
	dpkg -l | LC_ALL=C grep "^[a-zA-Z][A-Z] " 1>&2 || return 0

	echo "	The package state on this system is inconsistent."
	echo "	Please run 'dpkg --configure -a' manually"
	return 1
}

# check for Primary Directory Node UCS version
update_check_master_version () {
	local master_version ATTR=univentionOperatingSystemVersion var="update$VERSION/ignore_version"
	ignore_check "$var" && return 100
	[ -f /var/univention-join/joined ] || return 0

	case "$server_role" in
	domaincontroller_master) return 0 ;;
	esac

	master_version="$(univention-ldapsearch -LLL '(univentionServerRole=master)' "$ATTR" | sed -ne "s/$ATTR: //p;T;q")"
	dpkg --compare-versions "$master_version" le "${version_version}-${version_patchlevel}" || return 0

	echo "	Your Primary Directory Node is still on version $master_version."
	echo "	It is strongly recommended that the Primary Directory Node is"
	echo "	always the first system to be updated during a release update."
	echo
	echo "	This check can be disabled by setting the UCR variable '$var' to 'yes'."
	return 1
}

update_check_disk_space () {
	local var="update$VERSION/ignore_free_space" ret=0
	ignore_check "$var" && return 100
	while read -r partition size usersize
	do
		if [ "$(($(stat -f -c '%a*%S' "$partition")/1024))" -le "$size" ]
		then
			echo "	Not enough space in $partition, need at least $usersize."
			echo "	This may interrupt the update and result in an inconsistent system!"
			if [ "$partition" = "/boot" ] && [ "$update52_pruneoldkernel" != "yes" ]
			then
				echo
				echo "	Old kernel versions on /boot/ can be pruned by manully by running"
				echo "	'univention-prune-kernels' or automatically during"
				echo "	next update attempt by setting config registry variable"
				echo "	update${VERSION}/pruneoldkernel to \"yes\"."
			fi
			ret=1
		fi
	done <<__PART__
/var/cache/apt/archives	4000000	4000 MB
/boot	200000	200 MB
/	4000000	4000 MB
__PART__
	echo
	echo "	This check can be disabled by setting the UCR variable '$var' to 'yes'."
	echo "	But be aware that this is not recommended!"
	return "$ret"
}

# block if failed.ldif exists
update_check_failed_ldif() {
	[ -e /var/lib/univention-directory-replication/failed.ldif ] || return 0

	echo "	A failed.ldif exists."
	echo "	Please check <https://help.univention.com/t/6432> for further information."
	echo "	The update can be started after the failed.ldif has been removed."
	return 1
}

# block update if system date is too old
update_check_system_date_too_old() {
	local system_year
	system_year="$(date +%Y)"
	local var="update$VERSION/ignore_system_date"
	ignore_check "$var" && return 100
	[ "$system_year" -lt 2025 ] || return 0

	echo "	The system date ($(date +%Y-%m-%d)) does not seem to be correct."
	echo "	Please set a current system time before the update, otherwise the"
	echo "	update will fail if Spamassassin is installed."
	echo
	echo "	This check can be disabled by setting the UCR variable '$var' to 'yes'."
	return 1
}

update_check_minimum_ucs_version_of_all_systems_in_domain () {  # Bug #51621
	[ "$server_role" != "domaincontroller_master" ] && return 0

	MIN_VERSION="$MIN_VERSION" /usr/bin/python3 -c '
# -*- coding: utf-8 -*-
from packaging.version import Version
from os import environ
from univention.uldap import getMachineConnection

lo = getMachineConnection()

REQUIRED_VERSION = environ["MIN_VERSION"]
V5 = Version("5.0-0")

ATTR = "univentionOperatingSystemVersion"
blocking_computers = [
    "%s: %s" % (dn, attrs[ATTR][0].decode("UTF-8", "replace"))
    for dn, attrs in lo.search("(&(%s=*)(univentionOperatingSystem=Univention Corporate Server)(!(univentionObjectFlag=docker)))" % ATTR, attr=[ATTR])
    if Version(attrs[ATTR][0].decode("UTF-8", "replace")) < Version(REQUIRED_VERSION)
]

blocking_objects = []
ATTRS = ["univentionUCSVersionStart", "univentionUCSVersionEnd"]
for dn, attrs in lo.search("(&(objectClass=univentionObjectMetadata)(!(objectClass=univentionLDAPExtensionSchema)))", attr=ATTRS):
    start, end = (attrs.get(attr, [b""])[0].decode("UTF-8", "replace") for attr in ATTRS)
    if start and Version(start) >= V5:
        continue
    if end and Version(end) < V5:
        continue
    if start and Version(start) < V5 and end:
        continue
    blocking_objects.append("%s: [%s..%s)" % (dn, start or "unspecified", end or "unspecified"))

if blocking_computers:
    print("The following hosts must be upgraded to UCS %s first:\n\t%s" % (REQUIRED_VERSION, "\n\t".join(blocking_computers)))
if blocking_objects:
    print("The following extensions are incompatible with UCS 5.0:\n\t%s" % "\n\t".join(blocking_objects))

if blocking_computers or blocking_objects:
    exit(1)'
}

update_check_ucsschool () {
  local ucs_school_umc_exam_master_version="$(dpkg-query -W -f='${db:Status-Status} ${Version}' ucs-school-umc-exam-master 2>/dev/null | grep 'installed' | awk '{print $2}')"
  if [ -n "$ucs_school_umc_exam_master_version" ] && dpkg --compare-versions "$ucs_school_umc_exam_master_version" le "12.0.4"; then
    echo "	You have the package ucs-school-umc-exam-master version $ucs_school_umc_exam_master_version installed."
    echo "	This package is provided by the app 'UCS@school' version 5.2 v2 or older and currently is incompatible with UCS 5.2-2."
    echo "	Please wait for the next version of UCS@school to be released."
    return 1
  fi
}

# Bug 58164: Upgrade to UCS 5.2: LDAP Database is empty - Loading the domain database from the LDIF dump failed - attribute type undefined
_disabled_cool_solutions () {
  ! is_ucr_true repository/online/component/cool-solutions && return 0
  if [ "$repository_online_component_cool_solutions_version" = "current" ]; then
    return 0
  fi
  echo "	Cool Solutions component is not correctly setup"
  echo "	Setting repository/online/component/cool-solutions/version to current."
  ucr set repository/online/component/cool-solutions/version=current 2>>"$UPDATER_LOG" 3>>"$UPDATER_LOG" 1>>"$UPDATER_LOG"
  ucr unset " repository/online/component/cool-solutions/version" 2>>"$UPDATER_LOG" 3>>"$UPDATER_LOG" 1>>"$UPDATER_LOG"
  echo "	Setting repository/online/component/cool-solutions/unmaintained to yes."
  ucr set repository/online/component/cool-solutions/unmaintained=yes 2>>"$UPDATER_LOG" 3>>"$UPDATER_LOG" 1>>"$UPDATER_LOG"
  ucr unset " repository/online/component/cool-solutions/unmaintained" 2>>"$UPDATER_LOG" 3>>"$UPDATER_LOG" 1>>"$UPDATER_LOG"
  return 1
}

checks () {
	# stderr to log
	exec 2>>"$UPDATER_LOG"

	local f name stat stdout ret key success=true
	declare -A messages
	for f in $(declare -F)
	do
		if [[ "$f" =~ update_check_.* ]]
		then
			name=${f#update_check_}
			stat="OK"
			printf "%-50s" "Checking $name ... "
			stdout=$($f)
			ret=$?
			if [ $ret -ne 0 ]
			then
				if [ $ret -eq 100 ]
				then
					stat="IGNORED"
				else
					stat="FAIL"
					success=false
					messages["$name"]="$stdout"
				fi
			fi
			echo "$stat"
		fi
	done

	# summary
	ret=0
	if ! $success
	then
		echo
		echo "The system can not be updated to UCS $VERSION_NAME due to the following reasons:"
		for key in "${!messages[@]}"
		do
			echo
			echo "$key:"
			echo "${messages[$key]}" # | fmt --uniform-spacing --width="${COLUMNS:-80}"
		done
		echo
		ret=1
	fi
	[ "$ret" -gt 0 ] &&
		exit "$ret"
}

###CHECKS_ONLY###
if [ -z "${UPDATE_NEXT_VERSION:-}" ]
then
	main () {
		[ $# -ge 1 ] || set checks
		while [ $# -ge 1 ]
		do
			"$1"
			shift
		done
	}

	main "$@"
fi
###CHECKS_COMMON###
