#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2021-2025 Univention GmbH
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

import math
import os
import subprocess
import xml.etree.ElementTree as ET  # noqa: S405


STEPS = 48
THEME = 'light'


def main():
    tree = ET.parse(os.path.join(THEME, 'bootsplash-logo.svg'))  # noqa: S314
    root = tree.getroot()
    background_rect = root.find(
        './'
        '{http://www.w3.org/2000/svg}g[@{http://www.inkscape.org/namespaces/inkscape}label="Background"]/'
        '{http://www.w3.org/2000/svg}rect[@id="rect-background"]',
    )
    text = root.find(
        './'
        '{http://www.w3.org/2000/svg}g[@{http://www.inkscape.org/namespaces/inkscape}label="Text"]',
    )
    logo = root.find(
        './'
        '{http://www.w3.org/2000/svg}g[@{http://www.inkscape.org/namespaces/inkscape}label="Logo"]',
    )
    background_style = background_rect.get('style')
    text.set('style', 'display:none')
    logo.set('style', 'display:none')
    tree.write('logo-box.svg')
    subprocess.check_call(['inkscape', '--export-type=png', 'logo-box.svg'])
    os.remove('logo-box.svg')
    logo.attrib.pop('style')
    for i in range(STEPS):
        opacity = round((1 + math.cos(2 * math.pi * i / STEPS)) * 1 / 2, 2)
        background_rect.set('style', background_style.replace('stroke-opacity:1', f'stroke-opacity:{opacity}'))
        logo_fname = f'logo{i}.svg'
        tree.write(logo_fname)
        subprocess.check_call(['inkscape', '--export-type=png', logo_fname])
        os.remove(logo_fname)


if __name__ == '__main__':
    main()
