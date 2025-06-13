#!/usr/bin/python3
# pylint: disable-msg=C0301,R0903,R0913
#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import builtins
import subprocess
import urllib.parse
import urllib.response
from collections.abc import Sequence
from io import BytesIO, StringIO, TextIOWrapper
from os.path import abspath, dirname, join
from typing import IO, Any

import pytest

import univention.updater.tools as U
from univention.config_registry import ConfigRegistry


# from tests/mockups.py
MAJOR, MINOR, PATCH = RELEASE = (3, 0, 1)
ERRAT = 3


@pytest.fixture(autouse=True)
def ucslog():
    """Enable :py:mod:`univention.debug` logging."""
    U.ud.init("stderr", U.ud.NO_FLUSH, U.ud.NO_FUNCTION)
    U.ud.set_level(U.ud.NETWORK, U.ud.ALL)


@pytest.fixture(autouse=True)
def testdir(doctest_namespace):
    """Return path to directory :file:`test/`."""
    testdir = join(dirname(__file__), "tests", "data")
    doctest_namespace["TESTDIR"] = testdir
    return testdir


@pytest.fixture(autouse=True)
def ucr(monkeypatch, tmpdir):
    """Return mock Univention Config Registry"""
    db = tmpdir / "base.conf"
    monkeypatch.setenv("UNIVENTION_BASECONF", str(db))
    cr = ConfigRegistry()

    def extra(conf={}, **kwargs):
        cr.update(conf)
        cr.update(kwargs)
        cr.save()

    extra({
        'version/version': '%d.%d' % (MAJOR, MINOR),
        'version/patchlevel': '%d' % (PATCH,),
        'version/erratalevel': '%d' % (ERRAT,),
    })

    return extra


@pytest.fixture
def http(mocker):
    """Mock HTTP requests via py3:urllib.requests"""
    ressources = {}

    def extra(uris={}, netloc=""):
        uris = {join('/', key): value for key, value in uris.items()}
        ressources.setdefault(netloc, {}).update(uris)

    def fopen(req, *args, **kwargs):
        url = req.get_full_url()
        p = urllib.parse.urlparse(url)
        try:
            try:
                res = ressources[p.netloc][p.path]
            except LookupError:
                res = ressources[""][p.path]

            if isinstance(res, Exception):
                raise res
            elif isinstance(res, bytes):
                return urllib.response.addinfourl(BytesIO(res), {"content-length": len(res)}, url, 200)
            else:
                return res
        except LookupError:
            raise U.urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    director = mocker.patch("univention.updater.tools.urllib.request.OpenerDirector", autospec=True)
    director.open.side_effect = fopen
    opener = mocker.patch("univention.updater.tools.urllib.request.build_opener")
    opener.return_value = director
    U.UCSHttpServer.reinit()

    return extra


class MockPopen:
    """Mockup for :py:class:`subprocess.Popen`."""

    mock_commands: list[Sequence[str]] = []
    mock_stdout = b''
    mock_stderr = b''

    def __init__(self, cmd, shell=False, *args, **kwargs):  # pylint: disable-msg=W0613
        self.returncode = 0
        self.stdin = b''
        self.stdout = MockPopen.mock_stdout
        self.stderr = MockPopen.mock_stderr
        if shell:
            MockPopen.mock_commands.append(cmd)
        else:
            if isinstance(cmd, str):
                cmd = (cmd,)
            try:
                with open(cmd[0]) as fd_script:
                    content = fd_script.read(1024)
            except (OSError, UnicodeDecodeError) as ex:
                content = ex
            MockPopen.mock_commands.append((*tuple(cmd), content))

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def wait(self, timeout=None):
        """Return result code."""
        return self.returncode

    def poll(self):
        """Return result code."""
        return self.returncode

    def communicate(self, stdin=None):  # pylint: disable-msg=W0613
        """Return stdout and strerr."""
        return self.stdout, self.stderr

    @classmethod
    def mock_get(cls):
        """Return list of called commands."""
        commands = cls.mock_commands
        cls.mock_commands = []
        return commands

    @classmethod
    def mock_reset(cls):
        """Reset list of called commands."""
        cls.mock_commands = []
        cls.mock_stdout = cls.mock_stderr = b''


@pytest.fixture
def mockpopen(monkeypatch):
    """Mock :py:meth:`subprocess.Popen()` usage"""
    monkeypatch.setattr(subprocess, 'Popen', MockPopen)
    yield MockPopen
    MockPopen.mock_reset()


class MockFileManager:
    """Mockup for :py:func:`open()`"""

    def __init__(self, tmpdir: Any) -> None:
        self.files: dict[str, StringIO | BytesIO | Exception] = {}
        self._open = builtins.open
        self._tmpdir = tmpdir

    def open(self, name: str, mode: str = 'r', buffering: int = -1, **options: Any) -> IO:
        name = abspath(name)
        buf = self.files.get(name)

        if name.startswith(str(self._tmpdir)):
            return self._open(name, mode, buffering, **options)

        #    | pos | read | write
        # ===+=====+======+======
        # r  | 0   | pos  | -
        # r+ | 0   | pos  | pos
        # w  | 0   | -    | pos
        # w+ | 0   | pos  | pos
        # x  | 0   | -    | pos TODO
        # a  | end | -    | end FIXME
        # a+ | end | pos  | end FIXME
        binary = "b" in mode
        if "w" in mode or (("r+" in mode or "a" in mode) and not buf):
            self.files[name] = buf = self._new(name, b"" if binary else "")
        elif "r" in mode and not buf:
            return self._open(name, mode, buffering, **options)

        buf = self.files[name]
        if isinstance(buf, Exception):
            raise buf

        if "r" in mode:
            buf.seek(0)

        return TextIOWrapper(buf, "utf-8") if isinstance(buf, BytesIO) and not binary else buf

    def _new(self, name: str, data: bytes | str = b"") -> StringIO | BytesIO:
        buf: StringIO | BytesIO = BytesIO(data) if isinstance(data, bytes) else StringIO(data)
        buf.name = name
        buf.close = lambda: None
        buf.fileno = lambda: -1
        return buf

    def write(self, name: str, text: bytes) -> None:
        name = abspath(name)
        buf = self._new(name, text)
        self.files[name] = buf

    def read(self, name: str) -> bytes:
        name = abspath(name)
        if name not in self.files:
            raise FileNotFoundError(2, "No such file or directory: '%s'" % name)

        buf = self.files[name]
        assert not isinstance(buf, Exception)
        val = buf.getvalue()
        return val if isinstance(val, bytes) else val.encode("utf-8")

    def __setitem__(self, name: str, ex: Exception) -> None:
        name = abspath(name)
        self.files[name] = ex


@pytest.fixture
def mockopen(monkeypatch, tmpdir):
    """Mock :py:func:`open()` usage"""
    manager = MockFileManager(tmpdir)
    monkeypatch.setattr(builtins, "open", manager.open)
    return manager
