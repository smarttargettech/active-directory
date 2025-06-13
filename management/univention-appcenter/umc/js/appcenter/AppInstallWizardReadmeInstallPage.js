/*
 * Like what you see? Join us!
 * https://www.univention.com/about-us/careers/vacancies/
 *
 * Copyright 2020-2025 Univention GmbH
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
/*global define*/

define([
	"dojo/_base/declare",
	"dompurify/purify",
	"umc/widgets/Text",
	"./AppText",
	"umc/i18n!umc/modules/appcenter"
], function(declare, purify, Text, AppText, _) {
	return {
		getPageConf: function(app, readme) {
			if (!app[readme]) {
				return null;
			}

			return {
				name: `readme_${app.id}`,
				headerText: '',
				helpText: _('Information'),
				widgets: [{
					type: AppText,
					app: AppText.appFromApp(app),
					name: 'appText'
				}, {
					type: Text,
					'class': 'appInstallDialog__readme',
					name: `readmeInstall_readme_${app.id}`,
					content: purify.sanitize(app[readme])
				}]
			};
		}
	};
});
