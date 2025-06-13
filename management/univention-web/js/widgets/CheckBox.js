/*
 * Like what you see? Join us!
 * https://www.univention.com/about-us/careers/vacancies/
 *
 * Copyright 2011-2025 Univention GmbH
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
/*global define */

define([
	"dojo/_base/declare",
	"dojo/_base/lang",
	"dojo/dom-class",
	"dojo/dom-construct",
	"dijit/form/CheckBox",
	"umc/tools",
	"umc/widgets/_FormWidgetMixin",
	"./Icon"
], function(declare, lang, domClass, domConstruct, CheckBox, tools, _FormWidgetMixin, Icon) {
	return declare("umc.widgets.CheckBox", [ CheckBox, _FormWidgetMixin ], {
		// by default, the checkbox is turned off
		value: false,

		// a checkbox is always true
		valid: true,

		// display the label on the right
		labelPosition: 'right',

		// internal cache of the initial value
		_initialValue: null,

		postMixInProperties: function() {
			this._initialValue = this.checked = this.value;
			this.inherited(arguments);
		},

		buildRendering: function() {
			this.inherited(arguments);

			var iconCheck = new Icon({
				iconName: 'check'
			});
			var iconIndeterminate = new Icon({
				iconName: 'minus'
			});
			this.own(iconCheck);
			this.own(iconIndeterminate);
			domConstruct.place(iconCheck.domNode, this.domNode, 'first');
			domConstruct.place(iconIndeterminate.domNode, this.domNode, 'first');

			var node = domConstruct.create('div', {
				'class': 'dijitCheckBoxInputStretcher'
			}, this.focusNode, 'after');
			domConstruct.place(this.focusNode, node);
		},

		postCreate: function() {
			this.inherited(arguments);
			this.own(
				this.watch("checked", lang.hitch(this, function(attr, oldVal, newVal) {
					this.set('indeterminate', false);
					this.set("value", newVal);
				}))
			);
		},

		_setValueAttr: function(/*String|Boolean*/ newValue, /*Boolean*/ priorityChange){
			// based on the code from dijit.form.CheckBox
			newValue = tools.isTrue( newValue );

			// this is important, otherwise the initial state is displayed wrong
			if(this._created){
				this.set('checked', newValue, priorityChange);
			}
			this._set("value", newValue);
		},

		indeterminate: false,
		_setIndeterminateAttr: function(indeterminate) {
			this.focusNode.indeterminate = indeterminate;
			var ariaValue = indeterminate ? 'mixed' : this.get('checked').toString();
			this.focusNode.setAttribute('aria-checked', ariaValue);
			domClass.toggle(this.domNode, 'dijitCheckBoxIndeterminate', indeterminate);
			this._set('indeterminate', indeterminate);
		},

		_getValueAttr: function() {
			return this.get('checked');
		},

		setValid: function(isValid, message) {
			// a checkbox cannot be invalid
			// (for now, we should consider implementing it!)
			return false;
		}
	});
});


