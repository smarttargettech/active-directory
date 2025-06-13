#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2023-2024 Univention GmbH
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

import subprocess
from shutil import which

from univention.lib.i18n import Translation
from univention.management.console.modules.diagnostic import MODULE, Instance, Warning  # noqa: A004


_ = Translation('univention-management-console-module-diagnostic').translate


DEFRAGMENTATION_ARTICLE_URL = "https://help.univention.com/t/24105"
title = _('Check fragmentation of LMDB databases')
description = _('''
LMDB (https://www.symas.com/mdb) is a key value store with B+-tree structure and MVCC.
During normal oparation, the on disk file may get fragmented and it can be beneficial
for performance to defragment the file by running "mdb_copy -c".
This step has to be performed manually as described in''')

links = [
    {
        "name": "lmdb-defragmentation",
        "href": DEFRAGMENTATION_ARTICLE_URL,
        "label": _("Defragmentation of LMDB databases"),
    },
]
# run_descr = [_('The migration status can be checked by executing: pg_lsclusters -h.')]


def warning(msg: str) -> Warning:
    text = f'{msg}\n{description}'
    MODULE.error(text)
    return Warning(text, links=links)


def run(_umc_instance: Instance) -> None:
    if not which("univention-lmdb-fragmentation"):
        msg = "univention-lmdb-fragmentation not found"
        MODULE.error(msg)
        raise Warning(msg, links=[])

    error_descriptions = []
    try:
        subprocess.check_output(["univention-lmdb-fragmentation"])
    except subprocess.CalledProcessError as exc:
        error_descriptions.extend(exc.output.decode("utf-8").splitlines())

    if error_descriptions:
        raise warning(_("LMDB fragmentation above threshold.") + "\n" + "\n".join(error_descriptions))


if __name__ == '__main__':
    from univention.management.console.modules.diagnostic import main
    main()
