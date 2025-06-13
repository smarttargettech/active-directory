#
# Univention Password Self Service frontend base class
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2015-2025 Univention GmbH
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

from univention.config_registry import ConfigRegistry
from univention.lib.i18n import Translation


_ = Translation('univention-self-service-passwordreset-umc').translate


class UniventionSelfServiceTokenEmitter:
    """base class"""

    def __init__(self, log):
        self.ucr = ConfigRegistry()
        self.ucr.load()
        self.data = {}
        self.log = log

    @staticmethod
    def send_method():
        return "????"

    @staticmethod
    def send_method_label():
        return _("????")

    @staticmethod
    def message_application():
        return 'password_reset'

    @staticmethod
    def is_enabled():
        ucr = ConfigRegistry()
        ucr.load()
        return ucr.is_true("umc/self-service/passwordreset/????/enabled")

    @property
    def udm_property(self):
        return "self-service-????"

    def password_reset_verified_recovery_email(self):
        return self.message_application() == "password_reset" and self.udm_property == "PasswordRecoveryEmail"

    @property
    def token_length(self):
        return 1024

    def set_data(self, data):
        self.data.update(data)

    def send(self):
        raise NotImplementedError("Implement me")
