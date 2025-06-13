#!/usr/bin/python3
# pylint: disable-msg=C0103,E0611,R0904
# SPDX-FileCopyrightText: 2014-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit test for univention.config_registry."""

from importlib import reload
from time import sleep

import pytest

import univention.config_registry as UCR


def test_private(tmpucr):
    assert UCR.ucr_factory() is not UCR.ucr_factory()


def test_ro(ucrf):
    reload(UCR)
    assert not isinstance(UCR.ucr, UCR.ConfigRegistry)
    assert UCR.ucr["foo"] == "LDAP"
    assert UCR.ucr["bam"] is None
    with pytest.raises(TypeError):
        UCR.ucr["foo"] = "42"
    with pytest.raises(TypeError):
        del UCR.ucr["foo"]


@pytest.mark.parametrize("autoload,before,after", [
    pytest.param(lambda: UCR.ConfigRegistry(), None, None, id="Manual"),  # noqa: PLW0108
    pytest.param(lambda: UCR.ucr, "BEFORE", "BEFORE", id="Once"),
    pytest.param(lambda: UCR.ucr_live, "BEFORE", "AFTER", id="Always"),
    pytest.param(lambda: UCR.ucr_live.__enter__(), "BEFORE", "BEFORE", id="View"),  # noqa: PLW0108
])
def test_autoload(autoload, before, after, ucr0):
    reload(UCR)

    ucr0["baz"] = "BEFORE"
    ucr0.save()

    sleep(.1)

    ucr = autoload()
    assert ucr["baz"] == before

    ucr0["baz"] = "AFTER"
    ucr0.save()

    assert ucr["baz"] == after


@pytest.mark.slow
@pytest.mark.parametrize("autoload", [
    pytest.param(lambda ucr: ucr.load(), id="Default"),
    pytest.param(lambda ucr: ucr.load(autoload=UCR.Load.ALWAYS), id="Always"),
    pytest.param(lambda ucr: ucr.load(autoload=UCR.Load.ALWAYS).__enter__(), id="View"),
])
def test_benchmark_autoload(autoload, benchmark, ucr0):
    ucr0["foo"] = "value"
    ucr0.save()

    ucr = autoload(UCR.ConfigRegistry())
    benchmark(ucr.get, "foo")
