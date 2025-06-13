/*
 * Univention Directory Listener
 *  notifier.c
 *
 * Like what you see? Join us!
 * https://www.univention.com/about-us/careers/vacancies/
 *
 * Copyright 2004-2025 Univention GmbH
 *
 * https://www.univention.de/
 *
 * All rights reserved.
 *
 * The source code of this program is made available
 * under the terms of the GNU Affero General Public License version 3
 * (GNU AGPL V3) as published by the Free Software Foundation.
 *
 * Binary versions of this program provided by Univention to you as
 * well as other copyrighted, protected or trademarked materials like
 * Logos, graphics, fonts, specific documentations and configurations,
 * cryptographic keys etc. are subject to a license agreement between
 * you and Univention and not subject to the GNU AGPL V3.
 *
 * In the case you use this program under the terms of the GNU AGPL V3,
 * the program is provided in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public
 * License with the Debian GNU/Linux or Univention distribution in file
 * /usr/share/common-licenses/AGPL-3; if not, see
 * <https://www.gnu.org/licenses/>.
 */

/*
 * The name notifier might be misleading. The main function
 * "notifier_listener" uses the listener network API (network.c)
 * to receive updates from a notifier and calls the "change"
 * functions.
 */

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <inttypes.h>
#include <sys/time.h>
#include <sys/statvfs.h>

#include <univention/debug.h>
#include <univention/config.h>
#include <univention/ldap.h>

#include "notifier.h"
#include "common.h"
#include "handlers.h"
#include "cache.h"
#include "change.h"
#include "network.h"
#include "transfile.h"
#include "utils.h"

#define DELAY_LDAP_CLOSE 15               /* 15 seconds */
#define DELAY_ALIVE 5 * 60                /* 5 minutes */
#define TIMEOUT_NOTIFIER_RECONNECT 5 * 60 /* 5 minutes */


static void check_free_space() {
	static int64_t min_mib = -2;
	const char *dirnames[] = {cache_dir, ldap_dir, NULL}, **dirname;

	if (min_mib == -2)
		min_mib = univention_config_get_int("listener/freespace");

	if (min_mib <= 0)
		return;

	for (dirname = dirnames; *dirname; dirname++) {
		struct statvfs buf;
		int64_t free_mib;

		if (statvfs(*dirname, &buf))
			continue;

		free_mib = ((int64_t)buf.f_bavail * (int64_t)buf.f_frsize) >> 20;
		if (free_mib >= min_mib)
			continue;

		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "File system '%s' full: %" PRId64 " < %" PRId64, *dirname, free_mib, min_mib);
		abort();
	}
}

/* Fetch transaction details from LDAP. */
int notifier_wait_id_result(struct transaction *trans) {
	LDAPMessage *res;
	char base[44];  // strlen("reqSession=%ld,cn=translog") + strlen(ULONG_MAX)
	int scope = LDAP_SCOPE_BASE;
	char *filter = NULL;
	char *attrs[] = {"reqType", "reqDN", NULL};
	int attrsonly0 = 0;
	LDAPControl **serverctrls = NULL;
	LDAPControl **clientctrls = NULL;
	struct timeval timeout = {
		.tv_sec = 5 * 60, .tv_usec = 0,
	};
	int sizelimit0 = 1;
	int rv;

	snprintf(base, sizeof(base), "reqSession=%ld,cn=translog", trans->cur.notify.id);
	if ((rv = LDAP_RETRY(trans->lp, ldap_search_ext_s(trans->lp->ld, base, scope, filter, attrs, attrsonly0, serverctrls, clientctrls, &timeout, sizelimit0, &res))) == LDAP_SUCCESS) {
		LDAPMessage *entry = ldap_first_entry(trans->lp->ld, res);
		struct berval **vals;

		vals = ldap_get_values_len(trans->lp->ld, entry, "reqDN");
		if (vals && vals[0]->bv_len > 0)
			trans->cur.notify.dn = strndup(vals[0]->bv_val, vals[0]->bv_len + 1);
		else
			rv = LDAP_NO_SUCH_ATTRIBUTE;
		ldap_value_free_len(vals);

		vals = ldap_get_values_len(trans->lp->ld, entry, "reqType");
		if (vals && vals[0]->bv_len == 1)
			trans->cur.notify.command = vals[0]->bv_val[0];
		else
			rv = LDAP_NO_SUCH_ATTRIBUTE;
		ldap_value_free_len(vals);
		LOG(INFO, "LDAP returned: id:%ld\tdn:%s\tcmd:%c", trans->cur.notify.id, trans->cur.notify.dn, trans->cur.notify.command);
	} else {
		LOG(ERROR, "LDAP failed %s (%d): id:%ld", ldap_err2string(rv), rv, trans->cur.notify.id);
	}
	ldap_msgfree(res);

	return rv;
}


/* listen for ldap updates */
int notifier_listen(univention_ldap_parameters_t *lp, bool write_transaction_file, univention_ldap_parameters_t *lp_local) {
	int rv = 0;
	NotifierID id = cache_master_entry.id;
	struct transaction trans = {
	    .lp = lp, .lp_local = lp_local,
	};

	for (;;) {
		int msgid;
		time_t timeout = DELAY_LDAP_CLOSE;

		check_free_space();

		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "Last Notifier ID: %lu", id);
		if ((msgid = notifier_get_dn(NULL, id + 1)) < 1)
			break;

		/* wait for data; on timeouts, do maintenance stuff
		   such as closing the LDAP connection or running postrun
		   handlers */
		while (notifier_get_msg(NULL, msgid) == NULL) {
			/* timeout */
			if ((rv = notifier_wait(NULL, timeout)) == 0) {
				if (timeout == DELAY_ALIVE) {
					if (NOTIFIER_RETRY(notifier_alive_s(NULL)) == 1) {
						univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "failed to get alive answer");
						return 1;
					}
					notifier_resend_get_dn(NULL, msgid, id + 1);
				} else {
					if (trans.lp->ld != NULL) {
						ldap_unbind_ext(trans.lp->ld, NULL, NULL);
						trans.lp->ld = NULL;
					}
					if (trans.lp_local->ld != NULL) {
						ldap_unbind_ext(trans.lp_local->ld, NULL, NULL);
						trans.lp_local->ld = NULL;
					}
					univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "running postrun handlers");
					handlers_postrun_all();
					timeout = DELAY_ALIVE;
				}
				continue;
			} else if (rv > 0 && notifier_recv_result(NULL, NOTIFIER_TIMEOUT) == 0) {
				univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "failed to recv result");
				return 1;
			} else if (rv < 0) {
				return 1;
			}
		}

		memset(&trans.cur, 0, sizeof(trans.cur));
		if (NOTIFIER_RETRY(notifier_get_dn_result(NULL, msgid, &trans.cur.notify)) != 0) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "failed to get dn result");
			return 1;
		}
		univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_INFO, "notifier returned = id:%ld\tdn:%s\tcmd:%c", trans.cur.notify.id, trans.cur.notify.dn ? trans.cur.notify.dn : "<LDAP>", trans.cur.notify.command ? trans.cur.notify.command : '*');

		if ((trans.cur.notify.id != id + 1 && trans.cur.notify.command != '\0') || trans.cur.notify.id <= id) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "notifier returned transaction id %ld (%ld expected)", trans.cur.notify.id, id + 1);
			rv = 1;
			goto out;
		}

		/* ensure that LDAP connection is open */
		if (trans.lp->ld == NULL) {
			if ((rv = LDAP_RETRY(trans.lp, univention_ldap_open(trans.lp))) != LDAP_SUCCESS)
				goto out;
		}

		/* Fetch data from LDAP since protocol version 3 */
		if (trans.cur.notify.command == '\0') {
			// FIXME: V3 returns the latest known ID, but for now we're only interested in the next one
			trans.cur.notify.id = id + 1;
			rv = notifier_wait_id_result(&trans);
			if (rv != LDAP_SUCCESS)
				goto out;
		}
		id = trans.cur.notify.id;

		if ((rv = change_update_dn(&trans)) != LDAP_SUCCESS) {
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_ERROR, "change_update_dn failed: %d", rv);
			goto out;
		}

		/* rv had better be LDAP_SUCCESS if we get here */
		assert(rv == LDAP_SUCCESS);

		if (notifier_has_failed_ldif())
			goto out;

		/* Delay current command is stashed for later, otherwise process pending command now */
		if (trans.prev.notify.command) {
			if (!trans.cur.notify.command)
				continue;
			if (write_transaction_file && (rv = notifier_write_transaction_file(trans.prev.notify)) != 0)
				goto out;
			change_free_transaction_op(&trans.prev);
		}

		if (write_transaction_file && (rv = notifier_write_transaction_file(trans.cur.notify)) != 0)
			goto out;

		cache_master_entry.id = id;
		cache_update_master_entry(&cache_master_entry);
		if (cache_set_int("notifier_id", id))
			univention_debug(UV_DEBUG_LISTENER, UV_DEBUG_WARN, "failed to write notifier ID");
		change_free_transaction_op(&trans.cur);
	}

out:
	change_free_transaction_op(&trans.cur);
	change_free_transaction_op(&trans.prev);
	return rv;
}
