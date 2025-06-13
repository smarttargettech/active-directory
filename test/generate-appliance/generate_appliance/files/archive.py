# SPDX-FileCopyrightText: 2014-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/

from abc import ABCMeta
from collections.abc import Sequence
from hashlib import sha256
from logging import getLogger
from typing import Any

from . import File


log = getLogger(__name__)


class Archive(File, metaclass=ABCMeta):
    def __init__(self, file_list: Sequence[tuple[str, File | bytes]]) -> None:
        for _, source_file in file_list:
            if source_file is not None:
                assert isinstance(source_file, File | bytes)
        self._file_list = file_list
        File.__init__(self)

    @File.hashed
    def hash(self) -> tuple[Any, ...]:
        def hashed(thing: File | bytes) -> str:
            if isinstance(thing, bytes):
                return sha256(thing).hexdigest()
            return thing.hash()

        return (self.__class__, [(name, hashed(source_file)) for name, source_file in self._file_list])
