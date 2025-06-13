#!/bin/bash
# shellcheck shell=bash
DEBUGLEVEL=4
eval "$(univention-config-registry shell)"
: "${DOMAIN:=$domainname}"

# shellcheck disable=SC2015
tty <&2 >/dev/null && _B=$(tput rev 2>/dev/null) _N=$(tput sgr0 2>/dev/null) || unset _B _N
error () { #DEBUGLEVEL 0
	echo -e "${_B:-}error${_N:-} $(date +"%Y-%m-%d %H:%M:%S\t") $*" >&2
}
warning () { #DEBUGLEVEL 1
	if [ "$DEBUGLEVEL" -ge 1 ]
	then
		echo -e "${_B:-}warning${_N:-} $(date +"%Y-%m-%d %H:%M:%S\t") $*" >&2
	fi
}
info () { #DEBUGLEVEL 2
	if [ "$DEBUGLEVEL" -ge 2 ]
	then
		echo -e "${_B:-}info${_N:-} $(date +"%Y-%m-%d %H:%M:%S\t") $*" >&2
	fi
}
debug () { #DEBUGLEVEL 3
	if [ "$DEBUGLEVEL" -ge 3 ]
	then
		echo -e "${_B:-}debug${_N:-} $(date +"%Y-%m-%d %H:%M:%S\t") $*" >&2
	fi
}
section () { # This is intended to make life easier for readers of test-logs with a lot of content. If your testcase performs multiple similar checks each producing a lot of output visually dividing these checks into sections will help a lot. You should use this function only on the top level, i.e. directly in the test-script and not in any library functions.
	local sectionname="$1"
	info "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
	info "$sectionname"
	info "+++++++++++++++++++++++++++++++++++++++++++++++++++++++++++"
}

check_perm () { # Check file permissions
	# shellcheck disable=SC2034
	local check="${1?type}" filename="${2?filename}" perm="${3?permission}" owner="${4?owner}" group="${5?group}"
	eval '[ -${check#-} "$filename" ]' || return 0
	if [ $((perm)) -ne $((0$(stat -c "%a" "$filename"))) ] ||
		[ "$owner" != "$(stat -c "%U" "$filename")" ] ||
		[ "$group" != "$(stat -c "%G" "$filename")" ]
	then
		error "Expected $*, found $(stat "$filename")"
		return 110
	fi
}

checkpkg () { # check if package $1 is installed
	[ "$(dpkg-query -W -f '${Status}' "${1}")" = 'install ok installed' ] && :
}
requiresoftware () { # check if reqquired package $1 is installed
	if checkpkg "$1"
	then
		info "required package $1 installed"
		return 0
	else
		error "package $1 is missing"
		return 1
	fi
}
conflictsoftware () { # check if conflicting package $1 is installed
	if checkpkg "$1"
	then
		error "conflict package $1 installed"
		return 0
	else
		info "conflict package $1 not installed"
		return 1
	fi
}

have () {  # Usage: have cmd
	command -v "${1:?cmd}" >/dev/null 2>/dev/null
}

verify_value () {
	local name="$1" actual_value="$2" expected_value="$3"

	if [ "$actual_value" = "$expected_value" ]
	then
		return 0
	else
		info "Value of \"$name\" is \"$actual_value\", expected \"$expected_value\""
		return 1
	fi
}
verify_value_ignore_case () {
	local name="$1" actual_value="$2" expected_value="$3"

	if [ "${actual_value^^}" = "${expected_value^^}" ]
	then
		return 0
	else
		info "Value of \"$name\" is \"$actual_value\", expected \"$expected_value\""
		return 1
	fi
}
verify_value_contains_line_ignore_case () {
	local name="$1" actual_value="$2" expected_value="$3"

	if echo -n "$actual_value" | grep -F -i -q --line-regexp -Fis "$expected_value"
	then
		return 0
	else
		info "Value of \"$name\" is \"$actual_value\", does not contain line \"$expected_value\""
		return 1
	fi
}
verify_value_contains_line () {
	local name="$1" actual_value="$2" expected_value="$3"

	if echo -n "$actual_value" | grep -F -q  --line-regexp "$expected_value"
	then
		return 0
	else
		info "Value of \"$name\" is \"$actual_value\", does not contain line \"$expected_value\""
		return 1
	fi
}

log_and_execute () {
	info "EXECUTING: $*"
	"$@"
}

RETVAL=100
ALREADY_FAILED=false
fail_test () { # This is intended to make life easier for readers of test-logs while searching the spot where a testcase failed first.  In order for this to work you should consequently call fail_test with the corresponding error-code in your test-case instead of directly using exit and when you really want to exit do so with "exit $RETVAL" The first occurrence of an error will then be marked specially in the log file.
	local errorcode=110
	case "$1" in
	[0-9]|[0-9][0-9]|[0-9][0-9][0-9]) errorcode="$1" ; shift ;;
	esac

	if ! $ALREADY_FAILED
	then
		ALREADY_FAILED=true
		RETVAL="$errorcode"
		error "**************** Test failed above this line ($errorcode) ****************"
	else
		error "*** Test already failed above, but failed again ($errorcode) ***"
	fi
	[ -z "$*" ] ||
		error "$@"
}
fail_fast () { # Like fail_test "$reason" "$message" but with exit
	fail_test "$@"
	exit "$RETVAL"
}
fail_bool () { # This is intended to be called directly after functions that are supposed to return 0 on successful validation, 1 on failure or anything else in case of an internal error.
	# Be sure not to use the !-Operator on such functions, as this prohibits to distinguish between check failure and internal test error.
	# The intended calling scheme would be along the lines of: some_boolean_check; fail_bool 0 111 "Check xxx failed" or some_boolean_check; fail_bool 1 121
	local rc=$?
	local expected_retval="${1:-0}"
	local errorcode="${2:-110}"
	local failure_message="${3:-}"

	if [ -z "$failure_message" ]
	then
		if [ 0 -eq "$expected_retval" ]
		then
			failure_message="Expected operation to succeed, but it failed"
		elif [ 1 -eq "$expected_retval" ]
		then
			failure_message="Expected operation to fail, but it succeeded"
		fi
	fi

	if [ $rc -eq 1 ] || [ $rc -eq 0 ]
	then
		if [ $rc -eq "$expected_retval" ]
		then
			:
		else
			fail_test "$errorcode" "$failure_message"
		fi
	else
		error "Internal error detected. Last function returned ${rc}."
		fail_test 140
	fi
	return $rc
}

assert () {
	E_ASSERT_FAILED=99
	if [ -z "$2" ]; then
		fail_fast $E_ASSERT_FAILED "not enough parameters passed to assert() - $*"
	fi
	if [ ! "$1" ]; then
		fail_fast $E_ASSERT_FAILED "Assertion \"$1\" failed, line $2"
	fi
}

get_current_ucs_version_string () {
	echo "${version_version:-}-${version_patchlevel:-}"
}
ucs_version_string_to_integer () {
	local IFS=.-
	# shellcheck disable=SC2086
	set -- $1  # IFS
	local major="${1:-0}" minor="${2:-0}" patchlevel="${3:-0}"
	printf "%d%03d%03d\n" "$major" "$minor" "$patchlevel"
}
current_ucs_version_in_range () {
	local version1 version2 ucsversion
	version1="$(ucs_version_string_to_integer "$1")"
	version2="$(ucs_version_string_to_integer "$2")"
	ucsversion="$(ucs_version_string_to_integer "$(get_current_ucs_version_string)")"
	[ "$version1" -le "$ucsversion" ] && [ "$ucsversion" -le "$version2" ] && :
}
current_ucs_version_greater_equal () {
	local versionstring ucsversion
	versionstring="$(ucs_version_string_to_integer "$1")"
	ucsversion="$(ucs_version_string_to_integer "$(get_current_ucs_version_string)")"
	[ "$ucsversion" -ge "$versionstring" ] && :
}
current_ucs_version_less_equal () {
	local versionstring ucsversion
	versionstring="$(ucs_version_string_to_integer "$1")"
	ucsversion="$(ucs_version_string_to_integer "$(get_current_ucs_version_string)")"
	[ "$ucsversion" -le "$versionstring" ] && :
}

wait_for_replication () { # wait for listener/notifier replication to complete (timeout 5m)
	local i
	debug "Waiting for replication..."
	for ((i=0;i<300;i++)); do
		if /usr/lib/nagios/plugins/check_univention_replication
		then
			info "replication complete."
			return 0
		fi
		sleep 1
	done
	error "replication incomplete."
	return 1
}
wait_for_replication_and_postrun () { # wait for listener/notifier replicaion and listener postrun delay
	local rc
	wait_for_replication
	rc=$?
	debug "Waiting for postrun..."
	sleep 33
	return $rc
}

check_domainadmin_credentials () { # check ldap credentials are available
	[ -n "${tests_domainadmin_pwd:-}" ] && [ -n "${tests_domainadmin_pwdfile:-}" ] && [ -n "${tests_domainadmin_account:-}" ]
}

get_domain_admins_dn () { # prints the Domain Admins dn
	eval "$(ucr shell groups/default/domainadmins ldap/base)"
	group_admins="${groups_default_domainadmins:-Domain Admins}"
	echo "cn=${group_admins:?},cn=groups,${ldap_base:?}"
}

retry () {  # <count> <args...> # retry_delay=1
	local retry_count="${1:?}"
	shift
	for ((retry_i=1; retry_i<=retry_count; retry_i++))
	do
		"$@" && return 0
		sleep "${retry_delay:-1}"
	done
	return 1
}

VAL () { # Usage: ... | VAL uid
	sed -rne "/^$1:/{s/^$1: //;s/^$1:: ([A-Za-z0-9+/]+=*)\$/echo \1|base64 -d/e;p}"
}
VAL1 () { # Usage: ... | VAL uid
	sed -rne "/^$1:/{s/^$1: //;s/^$1:: ([A-Za-z0-9+/]+=*)\$/echo \1|base64 -d/e;p;q}"
}
dn () {  # Usage: ldapsearch ... 1.1 | dn
	VAL dn
}
dn1 () {  # Usage: ldapsearch ... 1.1 | dn1
	VAL dn
}
DN () {  # Usage: udm "$mod" list ... | DN
	VAL DN
}
DN1 () {  # Usage: udm "$mod" list ... | DN1
	VAL1 DN
}
UDM1 () {  # Usage: udm "$mod" create ... | UDM1
	sed -ne 's/^Object created: //p;T;q'
}

# vim:set filetype=sh ts=4:
# Local Variables:
# mode: sh
# End:
