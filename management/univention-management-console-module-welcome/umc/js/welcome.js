/*
 * Like what you see? Join us!
 * https://www.univention.com/about-us/careers/vacancies/
 *
 * Copyright 2021-2025 Univention GmbH
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
	"umc/tools",
	"umc/widgets/Module",
	"umc/widgets/Page",
	"dojo/topic",
	"management/widgets/ActivationDialog",
	"umc/modules/udm/LicenseDialog",
	"umc/modules/udm/LicenseImportDialog",
	"./welcome/Bubble",
	"./welcome/BubbleButton",
	"umc/i18n!umc/modules/welcome",
	"xstyle/css!umc/modules/welcome.css"
], function(declare, tools, Module, Page, topic, ActivationDialog, LicenseDialog, LicenseImportDialog, Bubble, BubbleButton, _) {
	return declare("umc.modules.welcome", [ Module ], {

		buildRendering: function() {
			this.inherited(arguments);

			tools.ucr(['uuid/license']).then((ucr) => {
				this._page = new Page({
					helpText: _("Great to see you! Now that your system is ready, these simple steps will guide you through the next phase. Let’s ensure everything is set up perfectly for a smooth experience!"),
					fullWidth: true
				});
				this.addChild(this._page);

				var license = new Bubble({
					header: _('UCS License'),
					icon: 'modules/udm/license.svg',
					description: _('Manage your license for your Univention Corporate Server domain'),
					subClass: 'license',
				});
				if (!ucr['uuid/license']) {
					license.addChild(new BubbleButton({
						header: _('Request a new license'),
						description: _('We send you a license with a Key ID to your email address'),
						onClick: () => { new ActivationDialog({}); }
					}));
				}
				license.addChild(new BubbleButton({
					header: _('License info'),
					description: _('Show your current license'),
					onClick: () => { new LicenseDialog({}); }
				}));
				license.addChild(new BubbleButton({
					header: _('Import a license'),
					description: _('Upload a new license we sent you earlier'),
					onClick: () => {
						var dlg = new LicenseImportDialog({});
						dlg.show();
					}
				}));
				this._page.addChild(license);

				var keycloak = new Bubble({
					header: _('Single Sign-on'),
					icon: '/univention/js/dijit/themes/umc/images/login_logo.svg',
					description: _('The Keycloak app enables single sign-on (SSO) for your UCS system, providing a unified and secure login experience.'),
					subClass: 'keycloak',
				});
				keycloak.addChild(new BubbleButton({
					header: _('Keycloak app'),
					description: _('Open in Univention App Center'),
					onClick: () => {
						topic.publish('/umc/modules/open', 'appcenter', 'appcenter', {props: {app: 'keycloak'}});
					}
				}));
				keycloak.addChild(new BubbleButton({
					header: _('Documentation'),
					description: _('Explore everything you need to know about the Keycloak app here'),
					onClick: () => {
						window.open('https://docs.software-univention.de/keycloak-app/latest/index.html');
					}
				}));
				this._page.addChild(keycloak);
			});
		}
	});
});
