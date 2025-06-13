#
# Like what you see? Join us!
# https://www.univention.com/about-us/careers/vacancies/
#
# SPDX-FileCopyrightText: 2024-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

from errno import EEXIST, ENOENT
from os import O_CREAT, O_WRONLY, _exit, fork, getpid, open, wait  # noqa: A004

import pytest

import univention.updater.locking as L


@pytest.fixture
def lock(tmpdir, monkeypatch):
    """Mock locking file"""
    lock = tmpdir / "lock"
    monkeypatch.setattr(L, "FN_LOCK_UP", str(lock))
    return lock


def test_empty(lock):
    lock.write("")
    with L.UpdaterLock():
        assert lock.exists()
        assert lock.read() == '%d\n' % getpid()


def test_stale(lock, capsys):
    lock.write("%d\n" % 0x7ffffff)
    with L.UpdaterLock():
        assert lock.exists()
        assert lock.read() == '%d\n' % getpid()

    out, err = capsys.readouterr()
    assert out == ""
    assert "Stale PID " in err


def test_context(lock):
    with L.UpdaterLock():
        assert lock.exists()
        assert lock.read() == '%d\n' % getpid()


def test_recursive(lock):
    with L.UpdaterLock(1) as l1:
        assert l1.lock == 0
        with L.UpdaterLock(1) as l2:
            assert l2.lock == 0
            assert lock.exists()
            assert lock.read() == '%d\n' % getpid()

        assert not lock.exists()


@pytest.mark.timeout(timeout=5)
def test_parent(lock):
    ppid = '%d\n' % getpid()

    with L.UpdaterLock(1):
        pid = fork()
        if not pid:
            with L.UpdaterLock(1) as l2:
                assert l2.lock == 1
                assert lock.exists()
                assert lock.read() == ppid
                _exit(0)

        (cpid, status) = wait()
        assert pid == cpid
        assert status == 0

        assert lock.exists()
        assert lock.read() == ppid


def test_nested(lock, mocker):
    ppid = getpid() ^ 1
    mocker.patch("os.getppid").return_value = ppid
    lock.write("%d\n" % ppid)

    ul = L.UpdaterLock()
    with ul:
        assert ul.lock > 0

    assert lock.exists()


@pytest.mark.parametrize('data', ["INVALID", "\u20ac"])
def test_invalid(data, lock):
    lock.write(data)

    with pytest.raises(L.LockingError) as exc_info:
        lock = L.UpdaterLock(1)
        lock.updater_lock_acquire()
        raise AssertionError()

    assert "Invalid PID" in str(exc_info.value)


@pytest.mark.timeout(timeout=5)
def test_timeout(mocker, lock):
    mocker.patch("os.getppid").return_value = -1
    lock.write("1\n")

    with pytest.raises(L.LockingError) as exc_info:
        lock = L.UpdaterLock(1)
        lock.updater_lock_acquire()
        raise AssertionError()

    assert "Another updater process 1 is currently running according to " in str(exc_info.value)


def test_error_sub_dir(tmpdir, monkeypatch):
    lock = tmpdir / "sub" / "lock"
    monkeypatch.setattr(L, "FN_LOCK_UP", str(lock))
    with pytest.raises(EnvironmentError):
        L.UpdaterLock().updater_lock_acquire()


def test_error_non_file(lock):
    lock.mkdir()
    with pytest.raises(EnvironmentError):
        L.UpdaterLock().updater_lock_acquire()


def test_concurrent(lock, mocker):
    fn = str(lock)
    mocker.patch("os.open").side_effect = [
        OSError(EEXIST, fn),
        OSError(ENOENT, fn),
        open(fn, O_CREAT | O_WRONLY, 0o644),
    ]
    with L.UpdaterLock(1):
        assert lock.exists()


def test_error_enter(lock, capsys):
    lock.write("INVALID")
    with pytest.raises(SystemExit) as exc_info, L.UpdaterLock(1):
        raise AssertionError()

    assert exc_info.value.code == 5
    _out, err = capsys.readouterr()
    assert "Invalid PID" in err


def test_error_gone(lock, capsys):
    with L.UpdaterLock():
        assert lock.check(file=1)
        lock.remove()

    _out, err = capsys.readouterr()
    assert "already released" in err


def test_error_taken(lock):
    with pytest.raises(EnvironmentError), L.UpdaterLock():
        assert lock.check(file=1)
        lock.remove()
        lock.mkdir()


@pytest.fixture
def apt_lock(tmpdir, monkeypatch):
    """Mock APT locking file"""
    lock = tmpdir / "lock"
    monkeypatch.setattr(L, "FN_LOCK_APT", str(lock))
    return lock


@pytest.mark.timeout(timeout=5)
def test_apt_lock(apt_lock, capsys):
    with L.apt_lock(1):
        assert apt_lock.exists()
    assert not apt_lock.exists()
