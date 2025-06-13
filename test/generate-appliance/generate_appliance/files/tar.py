# SPDX-FileCopyrightText: 2014-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/

import stat
import tarfile
from collections.abc import Sequence
from io import BytesIO
from logging import getLogger
from pathlib import Path

from . import File
from .archive import Archive


log = getLogger(__name__)


class Tar(Archive):
    SUFFIX = ".tar"

    def __init__(self, file_list: Sequence[tuple[str, File | bytes]], fileformat: int = tarfile.USTAR_FORMAT) -> None:
        Archive.__init__(self, file_list)
        self._format = fileformat

    def _create(self, path: Path) -> None:
        _ = [source_file.path() for _, source_file in self._file_list if isinstance(source_file, File)]
        log.info('Creating TAR %s', path)
        with tarfile.TarFile(name=path.as_posix(), mode='w', format=self._format) as archive:
            for name, source_file in self._file_list:
                log.info('  %s', name)
                info = tarfile.TarInfo(name)
                info.uname = info.gname = 'someone'
                info.mode = stat.S_IRUSR | stat.S_IWUSR
                if isinstance(source_file, bytes):
                    info.size = len(source_file)
                    handle = BytesIO(source_file)  # type: IO[bytes]
                else:
                    info.size = source_file.file_size()
                    handle = source_file.path().open("rb")

                archive.addfile(info, handle)
