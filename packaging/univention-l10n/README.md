UCS Localization (l10n)
=======================

This package has two use cases:

1. Update, build and install translations during package development and build
2. Extract all translations from all UCS source packages into a separate translation package.

Package translation
-------------------

### New packages

1. Depends on package `univention-l10n-tools` for build in `debian/control`:

		Source: ...
		Build-Depends:
		 univention-l10n-dev (>= 7.0.1),

2. Invoke command in `debian/rules`:

		%:
			dh --with univention-l10n

3. Add JSON files `debian/$pkg.univention-l10n`:

		[
		  {
			"input_files": [
			   "modules/univention/admin/.*\\.py"
			],
			"po_subdir": "modules/univention/admin/",
			"target_type": "mo",
			"destination": "usr/share/locale/{lang}/LC_MESSAGES/$pkg.mo"
		  }
		]

	* `input_files`: List of Python regular expressions to match path names
	* `po_subdir`: Directory containing the `$lang.po` files
	* `po_path`: Path to a single `$lang.po` file (overwrites `po_subdir` if specified)
	* `target_type`: `mo` (GNU gettext binary message object), `json`
	* `destination`: Target directory for installation; `{lang}` is replaced by language abbreviation.

### Updating translations

For UCS we do not store the `.pot` files in the source tree, only the `de.po` files containing the translation for German.
If translation strings are updated, the `.pot` file must be re-generated first, as it is required for updating translations.

1. Update the `.po` files locally:
```sh
univention-l10n-build de
```

2. Update `.po` files manually:
```sh
$EDITOR .../de.po
```

3. Commit updated `.po` file:
```sh
dch -i 'Bug #00000: Update German translation'
git add -- .../de.po debian/changelog
git commit -m 'Bug #00000 $src: Update German translation'
```

### UMC
UMC used its own technique, which now indirectly invokes `univention-l10n`.
UMC also uses XML files, which need separate translation.

For UMC-only modules it is sufficient to use `dh-umc-module-build` and `dh-umc-module-install`.
If the package contains other Python or JavaScript files, `univention-l10n-build` and `univention-l10n-install` must be used in *addition*.

Translation package
-------------------
See [Chapter Translating UCS](https://docs.software-univention.de/developer-reference-5.2.html#chap:translation)
