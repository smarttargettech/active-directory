#!/usr/bin/python3
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# Copyright 2009-2025 Univention GmbH
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
"""Univention Updater helper functions for managing a local repository."""

import gzip
import os
import shutil
import subprocess
import sys
from typing import IO

from univention.config_registry import ucr
from univention.lib.ucs import UCS_Version


# constants
ARCHITECTURES = {'amd64', 'all'}


class TeeFile:
    """
    Writes the given string to several files at once. Could by used
    with the print statement
    """

    def __init__(self, fds: list[IO[str]] = []) -> None:
        """
        Register multiple file descriptors, to which the data is written.

        :param fds: A list of opened files.
        :type fds: list(File)
        """
        self._fds = fds or [sys.stdout]

    def write(self, data: str) -> None:
        """
        Write string to all registered files.

        :param str data: The string to write.
        """
        for fd in self._fds:
            fd.write(data)
            fd.flush()


def gzip_file(filename: str) -> int:
    """
    Compress file.

    :param str filename: The file name of the file to compress.
    :returns: the process exit code.
    :rtype: int
    """
    return subprocess.call(('gzip', '--keep', '--force', '--no-name', '-9', filename))


def copy_package_files(source_dir: str, dest_dir: str) -> None:
    """
    Copy all Debian binary package files and signed updater scripts from `source_dir` to `dest_dir`.

    :param str source_dir: Source directory.
    :param str dest_dir: Destination directory.
    """
    for filename in os.listdir(source_dir):
        src = os.path.join(source_dir, filename)
        if not os.path.isfile(src):
            continue
        if filename.endswith(('.deb', '.udeb')):
            try:
                arch = filename.rsplit('_', 1)[-1].split('.', 1)[0]  # partman-btrfs_10.3.201403242318_all.udeb
            except (TypeError, ValueError):
                print("Warning: Could not determine architecture of package '%s'" % filename, file=sys.stderr)
                continue
            src_size = os.stat(src)[6]
            dest = os.path.join(dest_dir, arch, filename)
            # package already exists with correct size
            if os.path.isfile(dest) and os.stat(dest)[6] == src_size:
                continue
        elif filename in ('preup.sh', 'preup.sh.gpg', 'postup.sh', 'postup.sh.gpg'):
            dest = os.path.join(dest_dir, 'all', filename)
        else:
            continue
        try:
            shutil.copy2(src, dest)
        except shutil.Error as ex:
            print("Copying '%s' failed: %s" % (src, ex), file=sys.stderr)


def gen_indexes(base: str, version: UCS_Version) -> None:
    """
    Re-generate Debian :file:`Packages` files from file:`dists/` file.

    :param str base: Base directory, which contains the per architecture sub directories.
    """
    A = 'Architecture: '
    F = 'Filename: '
    print('  generating index ...', end=' ')
    for arch in ARCHITECTURES:
        if arch == 'all':
            continue
        src = os.path.join(
            base,
            'dists',
            'ucs%d%d%d' % version.mmp,
            'main',
            'binary-%s' % (arch,),
            'Packages.gz',
        )
        if not os.path.exists(src):
            continue
        lines = []
        names = [os.path.join(base, name, 'Packages') for name in ('all', arch)]
        with gzip.open(src, 'rb') as f_src, open(names[0], 'w') as f_all, open(names[1], 'w') as f_arch:
            for raw in f_src:
                line = raw.decode("UTF-8")
                if line.startswith(A):
                    arch = line[len(A):].strip()
                elif line.startswith(F):
                    line = '%s%s/%s' % (F, version, line[len(F):].lstrip('/'))
                lines.append(line)
                if line == '\n':
                    f = f_all if arch == 'all' else f_arch
                    f.write(''.join(lines))
                    del lines[:]

        for name in names:
            gzip_file(name)

    print('done')


def get_repo_basedir(packages_dir: str) -> str:
    """
    Check if a file path is a UCS package repository.

    :param str package_dir: A directory path.
    :returns: The canonicalized path without the architecture sub directory.
    :rtype: str
    """
    path = os.path.normpath(packages_dir)
    if os.path.isfile(os.path.join(path, 'Packages')):
        head, tail = os.path.split(path)
        if tail in ARCHITECTURES:
            return head
    elif set(os.listdir(path)) & ARCHITECTURES:
        return path

    print('Error: %s does not seem to be a repository.' % packages_dir, file=sys.stderr)
    sys.exit(1)


def assert_local_repository(out: IO[str] = sys.stderr) -> None:
    """
    Exit with error if the local repository is not enabled.

    :param file out: Override error output. Defaults to :py:obj:`sys.stderr`.
    """
    if not ucr.is_true('local/repository', False):
        print('Error: The local repository is not activated. Use "univention-repository-create" to create it or set the Univention Configuration Registry variable "local/repository" to "yes" to re-enable it.', file=out)
        sys.exit(1)
