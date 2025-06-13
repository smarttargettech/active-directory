#!/bin/bash

set -e -x

test_single_server () {
	# shellcheck source=utils.sh
	. product-tests/samba/utils.sh
	eval "$(ucr shell ldap/base windows/domain)"

	# get windows client info/name
	ucs-winrm run-ps --cmd ipconfig
	ucs-winrm winrm-config
	ucs-winrm run-ps --cmd "(gwmi win32_operatingsystem).caption"
	# shellcheck disable=SC2016
	winclient_name="$(ucs-winrm run-ps  --cmd '$env:computername' --loglevel error | head -1 | tr -d '\r')"
	test -n "$winclient_name"

	# Join des Clients
	ucs-winrm domain-join --dnsserver "$UCS"  --domainuser "Administrator" --domainpassword "$ADMIN_PASSWORD"

	assert_no_core_files

	# SID des Windows-Clients in OpenLDAP prüfen Bug #39804
	check_windows_client_sid "$winclient_name"

	# In der UMC anlegen: Benutzer, Drucker, Dateifreigabe
	udm users/user create --position "cn=users,$ldap_base" --set username="newuser01" \
		--set lastname="newuser01" --set password="Univention.99"
	#udm groups/group modify --dn "cn=Domain Admins,cn=groups,$ldap_base" --append users="uid=newuser01,cn=users,dc=sambatest,dc=test"
	udm shares/share create --position "cn=shares,$ldap_base" --set name="testshare" \
		--set host="$(hostname -f)" --set path="/home/testshare"
	udm shares/printer create --position "cn=printers,$ldap_base" --set name="printer1" \
		--set spoolHost="$(hostname -f)" --set uri="cups-pdf:/" --set model="cups-pdf/CUPS-PDF.ppd"
	sleep 15

	# Login als Domänen-Administrator am Windows-Client
	ucs-winrm domain-user-validate-password --domainuser "Administrator" --domainpassword "$ADMIN_PASSWORD"
	ucs-winrm domain-user-validate-password --domainuser "newuser01" --domainpassword "Univention.99"

	# TODO server password change

	# Benutzer-Login am Windows7 Client
	# * Zugriff auf Homeshare, Datei anlegen
	# * Dateirechte aus Homeshare prüfen:
	#  ** Windows: Rechte Maustaste, Eigenschaften..
	#  ** Server: getfacl
	ucs-winrm create-share-file --server "$UCS" --filename test-admin.txt --username 'Administrator' --userpwd "$ADMIN_PASSWORD" --share Administrator
	stat /home/Administrator/test-admin.txt
	getfacl /home/Administrator/test-admin.txt | grep "Domain.*Admin"
	ucs-winrm create-share-file --server "$UCS" --filename test-newuser01.txt --username 'newuser01' --userpwd "Univention.99" --share newuser01
	stat /home/newuser01/test-newuser01.txt
	getfacl /home/newuser01/test-newuser01.txt | grep "Domain.*Users"
	ucs-winrm create-share-file --server "$UCS" --filename test-admin.txt --username 'Administrator' --userpwd "$ADMIN_PASSWORD" --share testshare
	stat /home/testshare/test-admin.txt

	# this should fail
	ucs-winrm create-share-file --server "$UCS" --filename test-newuser01.txt \
		--username 'newuser01' --userpwd "Univention.99" --share testshare --debug 2>&1 | grep 'denied.'
	ucs-winrm create-share-file --server "$UCS" --filename test-newuser01.txt \
		--username 'newuser01' --userpwd "Univention.99" --share Administrator --debug 2>&1 | grep 'denied.'

	# check windows acl's
	ucs-winrm get-acl-for-share-file --server "$UCS" --filename test-newuser01.txt \
		--username 'newuser01' --userpwd "Univention.99" --share newuser01 --debug | grep "Group.*Domain Users"
	ucs-winrm get-acl-for-share-file --server "$UCS" --filename test-admin.txt \
		--username 'Administrator' --userpwd "$ADMIN_PASSWORD" --share Administrator --debug | grep "Group.*Domain Admins"
	su newuser01 -c "touch /home/newuser01/newfile.txt"
	ucs-winrm get-acl-for-share-file --server "$UCS" --filename newfile.txt \
		--username 'newuser01' --userpwd "Univention.99" --share newuser01 --debug | grep "Group.*Domain Users"

	# create files on samba and check share
	su Administrator -c "touch /home/Administrator/newfile.txt"
	ucs-winrm get-acl-for-share-file --server "$UCS" --filename newfile.txt \
		--username 'Administrator' --userpwd "$ADMIN_PASSWORD" --share Administrator --debug | grep "Group.*Domain Admins"

	# * GPO's
	# user gpo
	create_gpo NewGPO "$ldap_base" User 'HKCU\Environment'
	# machine gpo
	create_gpo NewMachineGPO "$ldap_base" Computer 'HKLM\Environment'
	# check gpo's
	ucs-winrm check-applied-gpos --username 'Administrator' --userpwd "$ADMIN_PASSWORD" \
		--usergpo 'Default Domain Policy' \
		--usergpo 'NewGPO' \
		--computergpo 'Default Domain Policy' \
		--computergpo 'NewMachineGPO'
	ucs-winrm check-applied-gpos --username 'newuser01' --userpwd "Univention.99" \
		--usergpo 'Default Domain Policy' \
		--usergpo 'NewGPO' \
		--computergpo 'Default Domain Policy' \
		--computergpo 'NewMachineGPO'

	## * Drucker einrichten
	#ucs-winrm setup-printer --printername printer1  --server "$UCS"
	#sleep 15
	#rpcclient  -UAdministrator%"$ADMIN_PASSWORD" localhost -c enumprinters
	## * Zugriff auf Drucker
	#ucs-winrm print-on-printer --printername printer1 --server "$UCS" --impersonate \
	#	--run-as-user Administrator
	#stat /var/spool/cups-pdf/administrator/job_1-document.pdf
	#ucs-winrm print-on-printer --printername printer1 --server "$UCS" --impersonate \
	#	--run-as-user newuser01 --run-as-password "Univention.99"
	#stat /var/spool/cups-pdf/newuser01/job_2-document.pdf
	## TODO printer via gpo

	# host $windows_client muss die IPv4-Adresse liefern.
	nslookup "$winclient_name" | grep "$WINRM_CLIENT"

	# userpassword change
	password=univention
	users="test1 test2 test3"
	clients="$WINRM_CLIENT $UCS"
	for user in $users; do
		udm users/user create --ignore_exists \
			--set password="$password" --set lastname="$user" --set username="$user"
		udm users/user modify \
			--dn "$(univention-ldapsearch -LLL uid="$user" dn |  sed -n 's/^dn: //p')" \
			--set password=$password --set overridePWHistory=1
	done
	sleep 10
	for client in $clients; do
		for user in $users; do
			smbclient "//${client}/IPC\$" -U "${user}%${password}" -c exit
		done
	done
	# password change via windows
	password=Univention.98
	for user in $users; do
		ucs-winrm change-user-password --userpassword="$password" --domainuser "$user"
	done
	sleep 10
	# check password
	for user in $users; do
		for client in $clients; do
			smbclient "//${client}/IPC\$" -U "${user}%${password}" -c exit
		done
		echo $password > /tmp/.usertest
		kinit --password-file=/tmp/.usertest "$user"
	done
	# check sid uid wbinfo
	# shellcheck disable=SC2153
	for user in $USERS; do
		uidNumber="$(univention-ldapsearch -LLL uid="$user" uidNumber |  sed -n 's/^uidNumber: //p')"
		sid="$(univention-ldapsearch -LLL uid="$user" sambaSID |  sed -n 's/^sambaSID: //p')"
		test "$uidNumber" = "$(wbinfo -S "$sid")"
		test "$sid" = "$(wbinfo -U "$uidNumber")"
		# shellcheck disable=SC2154
		wbinfo -i "${windows_domain}+${user}"
	done

	# IP-Adresse am Windows-Client ändern (statisch) DNS-Record auf dem Server überprüfen, DNS-Auflösung per host testen
	# TODO, geht nicht so einfach in ec2

	assert_no_core_files

	echo "Success"
}
