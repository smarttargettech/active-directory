/*
 * Like what you see? Join us!
 * https://www.univention.com/about-us/careers/vacancies/
 *
 * Copyright 2017-2025 Univention GmbH
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
/*global define,dojo,getQuery,require*/


define([
	"login",
	"dojo/_base/lang",
	"dojo/_base/array",
	"dojo/on",
	"dojo/query",
	"dojo/dom",
	"dojo/dom-construct",
	"dojo/dom-attr",
	"dojo/has",
	"dojo/_base/event",
	"dojo/cookie",
	"dojo/json",
	"dojo/Deferred",
	"dijit/Tooltip",
	"dojox/html/entities",
	"umc/dialog",
	"umc/tools",
	"umc/widgets/CookieBanner",
	"umc/i18n/tools",
	"umc/i18n!login"
], function(login, lang, array, on, query, dom, domConstruct, domAttr, has, dojoEvent, cookie, json, Deferred, Tooltip, entities, dialog, tools, CookieBanner, i18nTools, _) {

	return {
		_loginDialogRenderedDeferred: new Deferred(),

		// add custom info link to login dialog
		addLink: function(link) {
			this._loginDialogRenderedDeferred.then(lang.hitch(this, '_renderLink', link));
		},

		addLinkFromUcr: function(name, defaults) {
			this._loginDialogRenderedDeferred.then(lang.hitch(this, '_addLinkFromUcr', name, defaults));
		},

		_addLinkFromUcr: function(name, defaults) {
			defaults = defaults || {};
			var loginLinks = tools.status('login_links') || {};
			var enabled = loginLinks[name + '/enabled'] !== undefined ? tools.isTrue(loginLinks[name + '/enabled']) : defaults.enabled;
			if (!enabled) {
				return;
			}

			var locale = i18nTools.defaultLang().substring(0, 2);
			var ucrLinkConf = {};
			['href', 'text', 'tooltip'].forEach(function(key) {
				var localizedKey = key + '/' + locale;
				ucrLinkConf[key] = loginLinks[name + '/' + key];
				ucrLinkConf[localizedKey] = loginLinks[name + '/' + localizedKey];
			});
			ucrLinkConf.target = loginLinks[name + '/target'];
			ucrLinkConf = tools.objFilter(ucrLinkConf, function(k, v) {
				return v !== undefined;
			});

			var linkConf = lang.mixin({
				href: 'javascript:void(0);',
				text: '',
				tooltip: '',
				target: '_self'
			}, defaults, ucrLinkConf);

			var href = linkConf['href/' + locale] !== undefined ? linkConf['href/' + locale] : linkConf.href;
			var text = linkConf['text/' + locale] !== undefined ? linkConf['text/' + locale] : linkConf.text;
			var tooltip = linkConf['tooltip/' + locale] !== undefined ? linkConf['tooltip/' + locale] : linkConf.tooltip;
			var target = linkConf.target;

			var link = lang.replace('<a href="{href}" title="{tooltip}" target="{target}">{text}</a>', {
				href: entities.encode(href),
				tooltip: entities.encode(tooltip),
				text: entities.encode(text),
				target: entities.encode(target)
			});
			this._renderLink(link);
		},

		renderLoginDialog: function() {
			(new CookieBanner()).show();
			this._addDefaultLinks();
			this._checkCookiesEnabled();
			this._watchUsernameField();
			this._loginDialogRenderedDeferred.resolve();
		},

		_addDefaultLinks: function() {
			array.forEach(this._getDefaultLinks(), lang.hitch(this, '_renderLink'));

			// add "How do I login" link
			var tooltip = _('Please login with a valid username and password.') + ' ';
			if (getQuery('username') === 'root') {
				tooltip += _('Use the %s user for the initial system configuration.', '<b><a href="javascript:void();" onclick="_fillUsernameField(\'root\')">root</a></b>');
			} else {
				tooltip += _('The default user to manage the domain is %s which has the same initial password as the <i>root</i> account.', this._administratorLink());
			}
			this._addLinkFromUcr('how_do_i_login', {
				text: _('How do I login?'),
				tooltip: tooltip
			});
		},

		_getDefaultLinks: function() {
			var links = [];
			links.push(this._warningBrowserOutdated());
			links.push(this._insecureConnection());
			return links;
		},

		_renderLink: function(link) {
			var parentNode = dom.byId('umcLoginLinks');
			if (link && parentNode) {
				var node = domConstruct.place(domConstruct.toDom(link), parentNode);
				if (node.title) {
					on(node, 'mouseover', lang.hitch(this, '_showTooltip', node, node.title));
					domAttr.remove(node, 'title');
				}
			}
		},

		_insecureConnection: function() {
			// Show warning if connection is unsecured
			if (window.location.protocol === 'https:' || window.location.host === 'localhost') {
				return;
			}
			return lang.replace('<p class="umcLoginLinkWarning"><a href="https://{url}" title="{tooltip}">{text}</a></p>', {
				url: entities.encode(window.location.href.slice(7)),
				tooltip: entities.encode(_('This network connection is not encrypted. All personal or sensitive data such as passwords will be transmitted in plain text. Please follow this link to use a secure SSL connection.')),
				text: _('This network connection is not encrypted.<br/>Click here for an HTTPS connection.')
			});
		},

		_warningBrowserOutdated: function() {
			if (tools.browserIsOutdated()) {
				return '<p class="umcLoginLinkWarning">' + entities.encode(tools.browserIsOutdatedMessage()) + '</p>';
			}
		},

		_watchUsernameField: function() {
			var node = dom.byId('umcLoginUsername');
			if (!node) {
				return;  // e.g. error page on SAML
			}
			on(node, 'keyup', lang.hitch(this, function() {
				if (node.value === 'root') {
					Tooltip.show(_('The default user to manage the domain is %s which has the same initial password as the <i>root</i> account.', this._administratorLink()) + ' ' + _('The <i>root</i> user neither has access to the domain administration nor to the App Center.'), node, ['above']);
				}
			}));
		},

		_administratorLink: function() {
			var username = 'Administrator';
			return '<b><a href="javascript:void();" onclick=\'_fillUsernameField(' + json.stringify(username) + ')\'>' + entities.encode(username) + '</a></b>';
		},

		_cookiesEnabled: function() {
			if (!cookie.isSupported()) {
				return false;
			}
			if (cookie('UMCUsername')) {
				return true;
			}
			var cookieTestString = 'cookiesEnabled';
			cookie('_umcCookieCheck', cookieTestString, {expires: 1});
			if (cookie('_umcCookieCheck') !== cookieTestString) {
				return false;
			}
			cookie('_umcCookieCheck', cookieTestString, {expires: -1});
			return true;
		},

		_checkCookiesEnabled: function() {
			if (this._cookiesEnabled()) {
				return;
			}
			login._loginDialog.disableForm(_('Please enable your browser cookies which are necessary for using Univention Services.'));
		},

		_showTooltip: function(node, text) {
			Tooltip.show(text, node);
			on.once(dojo.body(), 'click', function(evt) {
				Tooltip.hide(node);
			});
		}
	};
});

function _fillUsernameField(username) {
	require(['dojo/dom', 'dojo/has'], function(dom, has) {
	dom.byId('umcLoginUsername').value = username;
	dom.byId('umcLoginPassword').focus();

	//fire change event manually for internet explorer
	if (has('ie') < 10) {
		var event = document.createEvent("HTMLEvents");
		event.initEvent("change", true, false);
		dom.byId('umcLoginUsername').dispatchEvent(event);
	}
	});
}
