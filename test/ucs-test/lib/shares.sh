#!/bin/bash
# shellcheck shell=bash

# shellcheck source=base.sh
. "$TESTLIBPATH/base.sh" || exit 137

SHARE_HOST="${hostname:?}.${domainname:?}"
SHARE_POSITION="cn=$hostname.${domainname:?},cn=shares,${ldap_base:?}"
SHARE_UNIX_OWNER=0 # must be number
SHARE_UNIX_GROUP=0 # must be number
SHARE_UNIX_DIRECTORYMODE=0755
SHARE_NFS_WRITEABLE=1
SHARE_SAMBA_WRITEABLE=1

share_create () {
	local sharename="${1?:share name}" sharepath="${2?:share path}" rc=0
	shift 2
	if udm_out="$(udm-test shares/share create \
		--position "$SHARE_POSITION" \
		--set name="$sharename" \
		--set path="$sharepath" \
		--set host="$SHARE_HOST" \
		--set owner="$SHARE_UNIX_OWNER" \
		--set group="$SHARE_UNIX_GROUP" \
		--set directorymode="$SHARE_UNIX_DIRECTORYMODE" \
		--set writeable="$SHARE_NFS_WRITEABLE" \
		--set sambaWriteable="$SHARE_SAMBA_WRITEABLE" \
		"$@" 2>&1)"
	then
		UDM1 <<<"$udm_out"
	else
		rc=$?
		echo "$udm_out" >&2
	fi
	return "$rc"
}

share_exists () {
	local name="${1:?share name}"
	udm-test shares/share list --filter "cn=$name" |
		grep -q "^DN: cn=$1,$SHARE_POSITION"
}

share_remove () {
	local name="${1:?share name}"
	udm-test shares/share remove --dn "cn=$name,$SHARE_POSITION"
}

share_mountlocal_nfs () {
	local name="${1:?share name}" path="${2:?mount point}"
	mount localhost:"$name" "$path"
}

share_mountlocal_samba () {
	local name="${1:?share name}" path="${2:?mount point}" USERNAME="${3:-$NAME}" PASSWORD="${4:-univention}"
	log_and_execute mount //localhost/"$1" "$2" -o username="$USERNAME",password="$PASSWORD"
}

# vim:set filetype=sh ts=4:
