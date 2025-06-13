#!/usr/bin/python3
# pylint: disable-msg=C0103,E0611,R0904
# SPDX-FileCopyrightText: 2014-2025 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""Unit test for univention.into_tools."""

import pytest

import univention.info_tools as uit


@pytest.fixture
def lval0():
    """Return an empty localized value instance."""
    obj = uit.LocalizedValue()
    uit.set_language('fr')
    return obj


class TestLocalizedValue:
    """Unit test for univention.info_tools.LocalizedValue"""

    def test_basic(self, lval0):
        """set() and get() without locale."""
        lval0.set('foo')
        assert lval0.get() == 'foo'
        assert repr(lval0) == "LocalizedValue({'fr': 'foo'}, __default='')"

    def test_explicit_language(self, lval0):
        """set() and get() with locale."""
        lval0.set('foo', locale='fr')
        lval0.set('bar', locale='en')
        assert lval0.get(locale='fr') == 'foo'

    def test_implicit_language_set(self, lval0):
        """set() without and get() with locale."""
        lval0.set('foo')
        lval0.set('bar', locale='en')
        assert lval0.get(locale='fr') == 'foo'

    def test_default_language_set(self, lval0):
        """set_default() and get() with locale."""
        lval0.set_default('foo')
        lval0.set('bar', locale='en')
        assert lval0.get(locale='fr') == 'foo'

    def test_default_language_get(self, lval0):
        """set_default() and get_default()."""
        lval0.set_default('foo')
        lval0.set('bar', locale='en')
        assert lval0.get_default() == 'foo'

    def test_missing_language(self, lval0):
        """set() and get() with different locale."""
        lval0.set('bar', locale='en')
        assert lval0.get(locale='fr') == ''


@pytest.fixture
def ldict0():
    """Return an empty localized dictionary instance."""
    obj = uit.LocalizedDictionary()
    uit.set_language('fr')
    return obj


class TestLocalizedDictionary:
    """Unit test for univention.info_tools.LocalizedDictionary"""

    def test_basic(self, ldict0):
        """__setitem__() and __getitem__()."""
        ldict0['foo'] = 'bar'
        assert ldict0['foo'] == 'bar'

    def test_setitem_getitem(self, ldict0):
        """__setitem__() and __getitem__()."""
        ldict0['foO'] = 'bar'
        assert ldict0['Foo'] == 'bar'

    def test_default(self, ldict0):
        """__setitem__() and get(default)."""
        assert ldict0.get('foo', 'default') == 'default'

    def test_set_locale(self, ldict0):
        """set() with and get() without locale."""
        ldict0['foo[fr]'] = 'bar'
        assert ldict0.get('foo') == 'bar'
        assert ldict0['foo'] == 'bar'

    def test_get_locale(self, ldict0):
        """set() without and get() with locale."""
        ldict0['foo'] = 'bar'
        assert ldict0.get('foo[fr]') == 'bar'
        assert ldict0['foo[fr]'] == 'bar'

    def test_in(self, ldict0):
        """in and has_key()."""
        assert 'foo' not in ldict0
        assert not ldict0.has_key('foo')
        ldict0['foo'] = 'bar'
        assert 'foO' in ldict0
        assert ldict0.has_key('foO')

    def test_in_locale(self, ldict0):
        """in and has_key() with locale request."""
        ldict0['foo'] = 'bar'
        assert 'foO[fr]' in ldict0
        assert ldict0.has_key('foO[fr]')

    def test_in_locale_set(self, ldict0):
        """in and has_key() with locale set."""
        ldict0['foo[fr]'] = 'bar'
        assert 'foO' in ldict0
        assert ldict0.has_key('foO')

    def test_normalize(self, ldict0):
        """normalize()."""
        reference = {
            'foo[fr]': 'bar',
            'foo[en]': 'baz',
            'foo': 'bam',
        }
        for key, value in reference.items():
            ldict0[key] = value
        norm = ldict0.normalize('foo')
        assert norm == reference

    def test_normalize_unset(self, ldict0):
        assert ldict0.normalize("key") == {}

    def test_get_dict(self, ldict0):
        """get_dict()."""
        reference = {
            'foo[fr]': 'bar',
            'foo[en]': 'baz',
        }
        for key, value in reference.items():
            ldict0[key] = value
        var = ldict0.get_dict('foo')
        assert isinstance(var, uit.LocalizedValue) is True
        assert var['fr'] == 'bar'
        assert var['en'] == 'baz'

    def test_get_dict_unset(self, ldict0):
        assert ldict0.get_dict("key") == {}

    def test_eq(self, ldict0):
        """__eq__ and __neq__."""
        obj = uit.LocalizedDictionary()
        assert ldict0 == obj
        assert obj == ldict0
        ldict0['foo'] = 'bar'
        assert ldict0 != obj
        assert obj != ldict0
        obj['foo'] = 'bar'
        assert ldict0 == obj
        assert obj == ldict0

    def test_eq_other(self, ldict0):
        assert not ldict0.__eq__(())


@pytest.fixture
def lval():
    """Return a pre-initialized localized value instance."""
    lval = uit.LocalizedValue()
    lval['de'] = 'foo'
    lval['en'] = 'bar'
    lval.set_default('baz')
    return lval


@pytest.fixture
def ldict():
    """Return a pre-initialized localized dictionary instance."""
    ldict = uit.LocalizedDictionary()
    ldict['val[de]'] = 'foo'
    ldict['val[en]'] = 'bar'
    ldict['val'] = 'baz'
    return ldict


class TestSetLanguage:
    """Unit test for univention.info_tools.set_language()."""

    def test_global(self, lval, ldict):
        """Test global set_language() setting."""
        uit.set_language('de')
        assert lval.get() == 'foo'
        assert ldict['val'] == 'foo'
        uit.set_language('en')
        assert lval.get() == 'bar'
        assert ldict['val'] == 'bar'

    def test_default(self, lval, ldict):
        """Test default set_language() setting."""
        uit.set_language('fr')
        assert lval.get() == 'baz'
        assert ldict['val'] == 'baz'


class TestUnicodeConfig:

    @pytest.fixture
    def cfg(self):
        """Return UnicodeConfig instance."""
        return uit.UnicodeConfig()

    def test_read(self, cfg, tmpdir):
        tmp = tmpdir / "ini"
        tmp.write("[section]\nkey = value\n")
        cfg.read(str(tmp))
        assert cfg.sections() == ["section"]
        assert cfg.get("section", "key") == "value"

    def test_write(self, cfg, tmpdir):
        cfg.add_section("section")
        cfg.set("section", "key", "value")
        cfg.set("DEFAULT", "key", "value")
        tmp = tmpdir / "ini"
        with tmp.open("w") as fd:
            cfg.write(fd)
        assert tmp.check(file=1)
