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
	"dojo/on",
	"umc/widgets/Uploader",
	"umc/widgets/Image",
	"umc/tools",
	"put-selector/put",
	"umc/i18n!"
], function(declare, lang, domClass, on, Uploader, Image, tools, put, _) {
	return declare("umc.widgets.ImageUploader", Uploader, {
		baseClass: 'umcImageUploader',

		// imageType: String
		//		Image type: '*', 'jpeg', 'png', 'svg+xml'
		imageType: '*',

		maxSize: 262400,

		size: 'Two',

		_image: null,

		constructor: function() {
			// this.buttonLabel = _('Upload new image');
			// this.clearButtonLabel = _('Clear image data');
		},

		buildRendering: function() {
			this.inherited(arguments);

			// create an image widget
			this._image = new Image({
				imageType: this.imageType,
				noImageMessage: _('Select file')
			});
			this.addChild(this._image, 0);
		},

		_hideStandby: null,
		_updateLabel: function() {
			this.inherited(arguments);
			this._hideStandby = tools.standby(this._image, {
				opacity: 1
			});
		},

		_resetLabel: function() {
			this.inherited(arguments);
			if (this._hideStandby) {
				this._hideStandby();
				this._hideStandby = null;
			}
		},

		updateView: function(value) {
			this._image.set('value', value);
		},

		getDataUri: function(base64String) {
			return this._image.getDataUri(base64String);
		}
	});
});


