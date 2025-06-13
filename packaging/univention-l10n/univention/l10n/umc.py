#!/usr/bin/python3
#
# Univention Management Console
"""
Each module definition contains the following entries:

* Module: The internal name of the module
* Python: A directory containing the Python module. There must be a subdirectory named like the internal name of the module.
* Definition: The |XML| definition of the module
* Javascript: The directory of the javascript code. In this directory must be a a file called :file:`<Module>.js`
* Category: The |XML| definition of additional categories
* Icons: A directory containing the icons used by the module. The directory structure must follow the following pattern :file:`<weight>x<height>/<icon>.(png|svg)`.

The entries Module and Definition are required.

Example::

    Module: ucr
    Python: umc/module
    Definition: umc/ucr.xml
    Javascript: umc/js
    Category: umc/categories/ucr.xml
    Icons: umc/icons
"""
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2011-2025 Univention GmbH
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


import copy
import json
import os
import re
import subprocess
import sys
import warnings
import xml.etree.ElementTree as ET  # noqa: S405
from collections.abc import Iterable, Iterator
from email.utils import formatdate

import polib
from debian.deb822 import Deb822, Packages

from .helper import Error, call, make_parent_dir
from .message_catalogs import merge_po


MODULE = 'Module'
PYTHON = 'Python'
DEFINITION = 'Definition'
JAVASCRIPT = 'Javascript'
CATEGORY = 'Category'
ICONS = 'Icons'

LANGUAGES = ('de', )

PO_METADATA = {
    'Project-Id-Version': '',
    'Report-Msgid-Bugs-To': 'packages@univention.de',
    'POT-Creation-Date': '',
    'PO-Revision-Date': '',
    'Last-Translator': 'Univention GmbH <packages@univention.de>',
    'Language-Team': 'Univention GmbH <packages@univention.de>',
    'Language': '',
    'MIME-Version': '1.0',
    'Content-Type': 'text/plain; charset=UTF-8',
    'Content-Transfer-Encoding': '8bit',
}


class UMC_Module(dict):

    def __init__(self, *args):
        dict.__init__(self, *args)
        for key in (MODULE, PYTHON, JAVASCRIPT, DEFINITION, CATEGORY, ICONS):
            if self.get(key):
                self[key] = self[key][0]

    @property
    def package(self) -> str:
        """Return the name of the Debian binary package."""
        return self['package']

    @property
    def python_path(self) -> str | None:
        """Return path to Python UMC directory."""
        try:
            return '%(Python)s/%(Module)s/' % self
        except KeyError:
            return None

    @property
    def js_path(self) -> str | None:
        """Return path to JavaScript UMC directory."""
        try:
            return '%(Javascript)s/' % self
        except KeyError:
            return None

    @property
    def js_module_file(self) -> str | None:
        """Return path to main JavaScript file."""
        try:
            return '%(Javascript)s/%(Module)s.js' % self
        except KeyError:
            return None

    def _iter_files(self, base: str | None, suffix: str) -> Iterator[str]:
        """Iterate over all files below base ending with suffix."""
        if base is None:
            return
        for dirname, dirs, files in os.walk(base):
            # ignore .svn directories
            if '.svn' in dirs:
                dirs.remove('.svn')
            # we are only interested in .js files
            for ifile in files:
                if ifile.endswith(suffix):
                    yield os.path.join(dirname, ifile)

    @property
    def js_files(self) -> Iterator[str]:
        """Iterate over all JavaScript UMC files."""
        return self._iter_files(self.js_path, '.js')

    @property
    def html_files(self) -> Iterator[str]:
        """Iterate over all JavaScript HTML files."""
        return self._iter_files(self.js_path, '.html')

    @property
    def css_files(self) -> Iterator[str]:
        """Iterate over all Javascript CSS files."""
        return self._iter_files(self.js_path, '.css')

    @property
    def module_name(self) -> str | None:
        """Return the name of the UMC module."""
        return self.__getitem__(MODULE)

    @property
    def xml_definition(self) -> str | None:
        """Return the path to the XML UMC definition."""
        return self.get(DEFINITION)

    @property
    def xml_categories(self) -> str | None:
        """Return the path to the XML file defining categories."""
        return self.get(CATEGORY)

    @property
    def python_files(self) -> Iterator[str]:
        """Iterate over all Python UMC files."""
        return self._iter_files(self.python_path, '.py')

    @property
    def python_po_files(self) -> Iterator[str]:
        """Iterate over all Python UMC message catalogs."""
        try:
            path = '%(Python)s/%(Module)s/' % self
        except KeyError:
            return
        for lang in LANGUAGES:
            yield os.path.join(path, '%s.po' % lang)

    @property
    def js_po_files(self) -> Iterator[str]:
        """Iterate over all JavaScript UMC message catalogs."""
        path = self.get(JAVASCRIPT)
        if not path:  # might be an empty string
            return
        for lang in LANGUAGES:
            yield os.path.join(path, '%s.po' % lang)

    @property
    def xml_po_files(self) -> Iterator[tuple[str, str]]:
        """Iterate over all XML UMC message catalogs."""
        if self.xml_definition is None:
            return
        dirpath = os.path.dirname(self.xml_definition)
        for lang in LANGUAGES:
            path = os.path.join(dirpath, '%s.po' % lang)
            yield (lang, path)

    @property
    def icons(self) -> str | None:
        """Return path to UMC icon directory."""
        return self.get(ICONS)


def read_modules(package: str, core: bool = False) -> list[UMC_Module]:
    """
    Read |UMC| module definition from :file:`debian/<package>.umc-modules`.

    :param package: Name of the package.
    :param core: Import as core-module, e.g. the ones shipped with |UDM| itself.
    :returns: List of |UMC| module definitions.
    """
    modules: list[UMC_Module] = []

    file_umc_module = os.path.join('debian/', package + '.umc-modules')
    file_control = os.path.join('debian/control')

    if not os.path.isfile(file_umc_module):
        return modules

    provides = []
    with open(file_control, encoding='utf-8') as fd_control:
        with warnings.catch_warnings():  # debian/deb822.py:982: UserWarning: cannot parse package relationship "${python3:Depends}", returning it raw
            for pkg in Packages.iter_paragraphs(fd_control):
                if pkg.get('Package') == package:
                    provides = [p[0]['name'] for p in pkg.relations['provides']]
                    break

    with open(file_umc_module, 'rb') as fd_umc:
        for item in Deb822.iter_paragraphs(fd_umc):
            item = {k: [v] for k, v in item.items()}  # simulate dh_ucs.parseRfc822 behaviour
            # required fields
            if not core:
                for required in (MODULE, PYTHON, DEFINITION, JAVASCRIPT):
                    if not item.get(required):
                        raise Error('UMC module definition incomplete. key %s missing' % (required,))

            # single values
            item['package'] = package
            item['provides'] = provides
            module = UMC_Module(item)
            if core and (module.module_name != 'umc-core' or not module.xml_categories):
                raise Error('Module definition does not match core module')
            modules.append(module)

    return modules


def module_xml2po(module: UMC_Module, po_file: str, language: str, template: bool = False) -> None:
    """
    Create a PO file the |XML| definition of an |UMC| module.

    :param module: |UMC| module.
    :param po_file: File name of the textual message catalog.
    :param language: 2-letter language code.
    :param template: Keep PO template file.
    """
    pot_file = '%s/messages.pot' % (os.path.dirname(po_file) or '.')

    po = polib.POFile(check_for_duplicates=True)
    po.metadata = copy.copy(PO_METADATA)
    po.metadata['Project-Id-Version'] = module.package
    po.metadata['POT-Creation-Date'] = formatdate(localtime=True)
    po.metadata['Language'] = language

    def _append_po_entry(xml_entry):
        """
        Helper function to access text property of XML elements and to find the
        corresponding po-entry.
        """
        if xml_entry is not None and xml_entry.text is not None:  # important to use "xml_entry is not None"!
            entry = polib.POEntry(msgid=xml_entry.text, msgstr='')
            try:
                po.append(entry)
            except ValueError as exc:  # Entry "..." already exists
                print('Warning: Appending %r to po file failed: %s' % (xml_entry.text, exc), file=sys.stderr)

    if module.xml_definition and os.path.isfile(module.xml_definition):
        tree = ET.ElementTree(file=module.xml_definition)
        _append_po_entry(tree.find('module/name'))
        _append_po_entry(tree.find('module/description'))
        _append_po_entry(tree.find('module/keywords'))
        for flavor in tree.findall('module/flavor'):
            _append_po_entry(flavor.find('name'))
            _append_po_entry(flavor.find('description'))
            _append_po_entry(flavor.find('keywords'))
        _append_po_entry(tree.find('link/name'))
        _append_po_entry(tree.find('link/description'))
        _append_po_entry(tree.find('link/url'))

    if module.xml_categories and os.path.isfile(module.xml_categories):
        tree = ET.ElementTree(file=module.xml_categories)
        for cat in tree.findall('categories/category'):
            _append_po_entry(cat.find('name'))

    po.save(pot_file)
    merge_po_file(po_file, pot_file)
    if not template:
        os.unlink(pot_file)


def create_po_file(po_file: str, package: str, files: str | Iterable[str], language: str = 'python', template: bool = False) -> None:
    """
    Create a PO file for a defined set of files.

    :param po_file: File name of the textual message catalog.
    :param package: Name of the package.
    :param files: A single file name or a list of file names.
    :param language: Programming language name.
    :param template: Keep PO template file.
    """
    pot_file = '%s/messages.pot' % (os.path.dirname(po_file) or '.')

    if os.path.isfile(pot_file):
        os.unlink(pot_file)
    if isinstance(files, str):
        files = [files]
    call(
        'xgettext',
        '--force-po',
        '--add-comments=i18n',
        '--from-code=UTF-8',
        '--sort-output',
        '--package-name=%s' % package,
        '--msgid-bugs-address=packages@univention.de',
        '--copyright-holder=Univention GmbH',
        '--language', language,
        '--output', pot_file,
        *files,
        errmsg='xgettext failed for the files: %r' % (list(files),)  # noqa: COM812
    )

    po = polib.pofile(pot_file)
    po.metadata['Content-Type'] = 'text/plain; charset=UTF-8'
    if po.metadata_is_fuzzy:  # xgettext always creates fuzzy metadata
        try:
            po.metadata_is_fuzzy.remove('fuzzy')
        except ValueError:
            pass

    po.save()
    merge_po_file(po_file, pot_file)
    if not template:
        os.unlink(pot_file)


def merge_po_file(po_file: str, pot_file: str) -> None:
    """
    Merge :file:`.po` file with new :file:`.pot` file.

    :param po_file: PO file containing translation.
    :param pot_file: PO template file.
    """
    if os.path.isfile(po_file):
        merge_po(pot_file, po_file)
    else:
        call('cp', pot_file, po_file)


def create_mo_file(po_file: str, mo_file: str = '') -> None:
    """
    Compile textual message catalog (`.po`) to binary message catalog (`.mo`).

    :param po_file: File name of the textual message catalog.
    :param mo_file: File name of compiled message catalog.
    """
    if not mo_file:
        head, tail = os.path.splitext(po_file)
        assert tail == '.po'
        mo_file = head + '.mo'

    cmd = ('msgattrib', '--only-fuzzy', '--no-wrap', po_file)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    out, _err = proc.communicate()
    if out:
        raise Error("Error: '{}' contains 'fuzzy' translations:\n{}".format(po_file, out.decode('utf-8', 'replace')))

    make_parent_dir(mo_file)

    call(
        'msgfmt', '--check', '--output-file', mo_file, po_file,
        errmsg='Failed to compile translation file from %s.' % (po_file,),
    )


def create_json_file(po_file: str) -> None:
    """
    Compile textual message catalog (`.po`) to |JSON| message catalog.

    :param po_file: File name of the textual message catalog.
    """
    json_file = po_file.replace('.po', '.json')
    pofile = polib.pofile(po_file)
    data = {}

    has_plurals = False
    for meta_entry in pofile.ordered_metadata():
        if meta_entry[0] == "Plural-Forms":
            has_plurals = True
            plural_rules = meta_entry[1]
            break

    # The rules get parsed from the pofile and put into the json file as
    # entries, if there are any. Parsing happens with regular expressions.
    if has_plurals:
        nplurals_start = re.search(r"nplurals\s*=\s*", plural_rules)
        nplurals_end = re.search(r"nplurals\s*=\s*[\d]+", plural_rules)

        # The $plural$ string contains everything from "plural=" to the last
        # ';'. This is a useful, since it would include illegal code, which
        # can then be found later and generate an error.
        plural_start = re.search(r"plural\s*=\s*", plural_rules)
        plural_end = re.search(r'plural\s*=.*;', plural_rules)

        if nplurals_start is None or nplurals_end is None or plural_start is None or plural_end is None:
            raise Error('The plural rules in %s\'s header entry "Plural-Forms" seem to be incorrect.' % (po_file))

        data["$nplurals$"] = plural_rules[nplurals_start.end():nplurals_end.end()]
        data["$plural$"] = plural_rules[plural_start.end():plural_end.end() - 1]

        # The expression in data["$plural$"] will be evaluated via eval() in
        # javascript. To avoid malicious code injection a simple check is
        # performed here.
        if not re.match(r"^[\s\dn=?!&|%:()<>]+$", data["$plural$"]):
            raise Error('There are illegal characters in the "plural" expression in %s\'s header entry "Plural-Forms".' % (po_file))

    for entry in pofile:
        if entry.msgstr:
            data[entry.msgid] = entry.msgstr
        elif entry.msgstr_plural and not has_plurals:
            raise Error("There are plural forms in %s, but no rules in the file's header." % (po_file))
        elif entry.msgstr_plural:
            entries = entry.msgstr_plural.items()
            entries = sorted(entries, key=lambda x: int(x[0]))
            data[entry.msgid] = [x[1] for x in entries]
            if len(data[entry.msgid]) != int(data["$nplurals$"]):
                raise Error('The amount of plural forms for a translation in %s doesn\'t match "nplurals" from the file\'s header entry "Plural-Forms".' % (po_file))

    with open(json_file, 'w') as fd:
        json.dump(data, fd)


def po_to_json(po_path: str, json_output_path: str) -> None:
    """
    Convert translation file to `JSON` file.

    :param po_path: Translation file name.
    :param json_output_path: Output file name.
    """
    create_json_file(po_path)
    make_parent_dir(json_output_path)
    os.rename(po_path.replace('.po', '.json'), json_output_path)
