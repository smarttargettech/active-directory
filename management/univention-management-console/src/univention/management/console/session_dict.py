#!/usr/bin/python3
#
# Univention Management Console
#  UMC server
#
# Copyright 2024-2025 Univention GmbH
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

from collections.abc import MutableMapping

from sqlalchemy import exc

from univention.management.console.session_db import DBDisabledException, DBSession, get_session
from univention.management.console.sse import logout_notifiers

from .log import CORE


class SessionDict(MutableMapping):
    sessions = {}

    def __delitem__(self, session_id) -> None:
        self.delete(session_id)

    def __setitem__(self, session_id, umc_session) -> None:
        try:
            with get_session() as db_session:
                session = DBSession.get(db_session, session_id)
                if session:
                    DBSession.update(db_session, session_id, umc_session)
                else:
                    DBSession.create(db_session, session_id, umc_session)
        except exc.DBAPIError as err:
            CORE.error('Adding the session into the database failed\n%s' % (err,))
        except DBDisabledException:
            pass

        self.sessions[session_id] = umc_session

    def __getitem__(self, session_id):
        local_session = self.sessions[session_id]
        try:
            with get_session() as db_session:
                session = DBSession.get(db_session, session_id)
                if not session:
                    del self.sessions[session_id]
                    raise KeyError(session_id)
        except exc.DBAPIError as err:
            CORE.error('Getting the session from the database failed\n%s' % (err,))
        except DBDisabledException:
            pass

        return local_session

    def __len__(self) -> int:
        return len(self.sessions)

    def __iter__(self):
        return self.sessions.__iter__()

    def get_oidc_sessions(self, logout_token_claims):
        try:
            with get_session() as db_session:
                sessions = DBSession.get_by_oidc(db_session, logout_token_claims)
                return sessions
        except exc.DBAPIError as err:
            CORE.error('Getting OIDC sessions from the database failed\n%s' % (err,))
        except DBDisabledException:
            pass

        return self.__get_oidc_sessions_fallback(logout_token_claims)

    def __get_oidc_sessions_fallback(self, logout_token_claims):
        sessions = [user for user in self.sessions.values() if user and user.oidc and user.oidc.id_token and logout_token_claims['iss'] == user.oidc.claims['iss']]
        for user in sessions:
            if user.oidc.claims['sid'] == logout_token_claims.get('sid'):
                yield user
                return
        for user in sessions:
            if user.oidc.claims['sub'] == logout_token_claims.get('sub'):
                yield user

    def delete(self, session_id, reload=True):
        CORE.debug('session deletion in session dict')
        logout_notifier = logout_notifiers.get(session_id)
        if logout_notifier is not None:
            CORE.debug('We have locally found a logout notifier')
            if reload:
                logout_notifier.set()
        try:
            with get_session() as db_session:
                if logout_notifier is None:
                    CORE.debug('we have not locally found a logout notifier.')
                DBSession.delete(db_session, session_id, logout_notifier is None)
        except exc.DBAPIError as err:
            CORE.debug('Deleting the session from the database failed\n%s' % (err,))
        except DBDisabledException:
            pass

        del self.sessions[session_id]
