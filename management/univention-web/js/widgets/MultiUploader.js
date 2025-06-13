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
	"dojo/_base/array",
	"dojo/when",
	"dojo/on",
	"dojo/dom-style",
	"dojox/html/entities",
	"umc/tools",
	"umc/widgets/ContainerWidget",
	"umc/widgets/_FormWidgetMixin",
	"umc/widgets/Button",
	"umc/widgets/Uploader",
	"umc/widgets/MultiSelect",
	"umc/widgets/Text",
	"umc/i18n!"
], function(declare, lang, array, when, on, domStyle, entities, tools, ContainerWidget, _FormWidgetMixin, Button, Uploader, MultiSelect, Text, _) {
	return declare("umc.widgets.MultiUploader", [ ContainerWidget, _FormWidgetMixin ], {
		baseClass: 'umcMultiUploader',

		// command: String
		//		The UMC command to which the data shall be uploaded.
		//		If not given, the data is sent to univention/upload which will return the
		//		file content encoded as base64.
		command: '',

		// dynamicOptions: Object?|Function?
		//		see umc/widgets/Uploader
		dynamicOptions: null,

		// buttonLabel: String
		//		The label that is displayed on the upload button.
		buttonLabel: _('Upload'),

		// removeButtonLabel: String
		removeButtonLabel: _('Remove'),

		// value: String[]
		//		'value' contains an array of the uploaded file names.
		value: null,

		// maxSize: Number
		//		A size limit for the uploaded file.
		maxSize: 524288,

		// this form element should always be valid
		valid: true,

		/*=====
		// state: String
		//		Specifies in which state the widget is:
		//		'Complete' -> default,
		//		'Incomplete' -> uploads are not completed yet
		state: 'Complete',
		=====*/

		// internal reference to the MultiSelect widget containing all filenames
		_files: null,

		// internal reference to the current Uploader widget
		_uploader: null,

		_progress: null,

		// allow selecting of Multiple Files
		multiFile: false,

		// internal reference to the progress bar
		_progressText: null,

		// button for removing entries
		_removeButton: null,

		// container for the upload and remove buttons
		_container: null,

		// internal reference to the currently uploading files
		_uploadingFiles: [],

		constructor: function() {
			this._uploadingFiles = [];
			this.value = [];

			// default to value given by UCR variable
			var maxSize = parseInt(tools.status('umc/server/upload/max'), 10);
			if (!isNaN(maxSize)) {
				this.maxSize = maxSize * 1024;
			}
		},

		buildRendering: function() {
			this.inherited(arguments);

			// MultiSelect widget for displaying the file list
			this._files = new MultiSelect({
				showHeader: true
			});
			this.addChild(this._files);

			this._createProgressBar();

			// prepare remove button and container for upload/remove buttons
			this._container = new ContainerWidget({
				'class': 'umcMultiUploader__buttons'
			});
			this.addChild(this._container);
			// add the uploader button
			this._addUploader();
			this._container.addChild(new Button({
				label: this.removeButtonLabel,
				onClick: lang.hitch(this, '_removeFiles'),
				'class': 'ucsTextButton',
				iconClass: 'trash'
			}));

			this._uploader.setDragAndDrop(this._files.domNode);
		},

		destroy: function() {
			this.inherited(arguments);

			if (this._progressText) {
				// destroy the old progress bar
				this._progressText.destroyRecursive();
			}
		},

		_getStateAttr: function() {
			return this._uploadingFiles.length ? 'Incomplete' : 'Complete';
		},

		_setValueAttr: function(newVal) {
			this._files.selection.clear();
			this._files.set('staticValues', newVal);
			this._set('value', newVal);
		},

		_getValueAttr: function() {
			return this._files.get('staticValues');
		},

		_setButtonLabelAttr: function(newVal) {
			this._uploader.set('buttonLabel', newVal);
			this._set('buttonLabel', newVal);
		},

		_setDisabledAttr: function(newVal) {
			this._files.set('disabled', newVal);
			this._uploader.set('disabled', newVal);
			this._set('disabled', newVal);
		},

		_getDisabledAttr: function() {
			return this._files.get('disabled');
		},

		_removeFiles: function() {
			var selectedFiles = this._files.get('value');
			if (!selectedFiles.length) {
				return;
			}

			// make sure we may remove the selected items
			when(this.canRemove(selectedFiles), lang.hitch(this, function(doUpload) {
				if (!doUpload) {
					// removal canceled
					return;
				}

				// remove items
				var files = this.get('value');
				files = array.filter(files, function(ifile) {
					return array.indexOf(selectedFiles, ifile) < 0;
				});
				this.set('value', files);
			}));
		},

		_createProgressBar: function() {
			if (this._progressText) {
				// destroy the old progress bar
				this._progressText.destroyRecursive();
			}

			// create progress bar for displaying the upload information
			this._progressText = new Text({
				'class': 'umcMultiUploader__progressText'
			});
		},

		_updateProgress: function() {
			if (!this._progressText) {
				return;
			}

			var currentVal = 0;
			var nDone = 0;
			var currentMaxSize = 0;
			array.forEach(this._uploadingFiles, lang.hitch (this, function(ifile) {
				if (this._uploadingFiles && this._progress) {
					currentMaxSize += ifile.size;
					if (this._progress.bytesLoaded >= currentMaxSize){
						nDone = ifile.index;
						ifile.done = true;
					}
				}
			}));
			currentVal = (nDone / this._uploadingFiles.length) * 100;
			if (this._uploadingFiles.length && nDone == this._uploadingFiles.length - 1) {
				this._progressText.set('content',
					entities.encode(_('Uploading... %(current)d of %(total)d files remaining.',
						{
							current: this._uploadingFiles.length - nDone,
							total: this._uploadingFiles.length
						}
					))
				);
			}
		},

		_addUploader: function() {
			// create a new Uploader widget
			this._uploader = new Uploader({
				showClearButton: false,
				buttonLabel: this.buttonLabel,
				command: this.command,
				dynamicOptions: this.dynamicOptions,
				maxSize: this.maxSize,
				multiFile: this.multiFile,
				canUpload: this.canUpload,
				buttonClass: 'ucsTextButton'
			});
			this._container.addChild(this._uploader, 0);

			// register events
			var uploader = this._uploader;



			on.once(uploader, 'uploadStarted', lang.hitch(this, function(file) {
				//console.log('### onUploadStarted:', json.stringify(file));

				// add current file to the list of uploading items
				if (!this._uploadingFiles.length) {
					// first file being uploaded -> show the standby animation
					this._files.standby(true, this._progressText);
				}
				// convert to array if single file
				if (!(file instanceof Array)){
					file = [ file ];
				}
				array.forEach(file, lang.hitch(this, function(ifile) {
					ifile.done = false;
					this._uploadingFiles.push(ifile);
				}));
				this._updateProgress();

				var progressSignal = on(uploader, 'progress', lang.hitch(this, function(info) {
					// update progress information
					//console.log('### onProgress:', json.stringify(info));
					lang.mixin(file, info);
					this._progress=info;
					this._updateProgress();
				}));

				var uploadSignal;
				var errorSignal;

				var _done = function(success) {
					// disconnect events
					//console.log('### onUploaded');
					progressSignal.remove();
					uploadSignal.remove();
					errorSignal.remove();

					// update progress information
					file.done = true;
					file.success = success;
					this._updateProgress();

					// remove Uploader widget from container
					this.removeChild(uploader);
					uploader.destroyRecursive();

					// when all files are uploaded, update the internal list of files
					var allDone = true;
					array.forEach(this._uploadingFiles, function(ifile) {
						allDone = allDone && ifile.done;
					});
					if (allDone) {
						// add files to internal list of files
						this._files.standby(false);
						var vals = this.get('value');

						array.forEach(this._uploadingFiles, function(ifile){
							if (file.success) {
								vals.unshift(ifile.name);
							}
						});

						//remove duplicates from list
						var newVals = [];
						array.forEach(vals, function(value) {
							if (array.indexOf(newVals, value) == -1) {
								newVals.push(value);
							}
						});

						this.set('value', newVals);

						// clear the list of uploading files
						this._uploadingFiles = [];
					}
				};
				uploadSignal = on(uploader, 'uploaded', lang.hitch(this, _done, true));
				errorSignal = on(uploader, 'error', lang.hitch(this, _done, false));

				// hide uploader widget and add a new one
				uploader.set('visible', false);
				this._addUploader();
				//since we create a new uploader we need to setup drag and drop again
				this._uploader.setDragAndDrop(this._files.domNode);
			}));
		},


		canUpload: function(fileInfo) {
			// summary:
			//		Before uploading a file, this function is called to make sure
			//		that the given filename is valid. Return boolean or dojo/Deferred.
			// fileInfo: Object
			//		Info object for the requested file, contains properties 'name',
			//		'size', 'type'.
			return true;
		},

		canRemove: function(filenames) {
			// summary:
			//		Before removing a files from the current list, this function
			//		is called to make sure that the given file may be removed.
			//		Return boolean or dojo/Deferred.
			// filenames: String[]
			//		List of filenames.
			return true;
		},

		onUploaded: function(data) {
			// event stub
		},

		onChange: function(data) {
			// event stub
		}
	});
});


