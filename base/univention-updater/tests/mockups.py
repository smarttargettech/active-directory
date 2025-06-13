#!/usr/bin/python3
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import json
from collections.abc import Iterable
from itertools import groupby
from operator import itemgetter


# from ../conftest.py
MAJOR, MINOR, PATCH = RELEASE = (3, 0, 1)
ERRAT = 3
ARCH = 'amd64'
DATA = b'x' * 100  # univention.updater.tools.MIN_GZIP
RJSON = '/ucs-releases.json'


def gen_releases(releases: Iterable[tuple[int, int, int]] = [], major: int = MAJOR, minor: int = MINOR, patches: Iterable[int] = range(PATCH + 1)) -> bytes:
    """
    Generate a `ucs-releases.json` string from a list of given releases.

    :param releases: List of UCS releases.
    :param major: UCS major version.
    :param minor: UCS minor version.
    :param patches: List of UCS patch-level versions.

    >>> gen_releases([(MAJOR, MINOR, 0), (MAJOR, MINOR, 1)]) == gen_releases(patches=[0, 1])
    True
    """
    releases = list(releases) or [(major, minor, patch) for patch in patches]
    data = {
        "releases": [
            {
                "major": major,
                "minors": [
                    {
                        "minor": minor,
                        "patchlevels": [
                            {
                                "patchlevel": patchlevel,
                                "status": "maintained",
                            } for major, minor, patchlevel in patchelevels
                        ],
                    } for minor, patchelevels in groupby(minors, key=itemgetter(1))
                ],
            } for major, minors in groupby(releases, key=itemgetter(0))
        ],
    }
    return json.dumps(data).encode('UTF-8')
