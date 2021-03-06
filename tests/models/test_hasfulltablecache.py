# encoding: utf-8
from nose.tools import (
    eq_,
    set_trace,
)
from .. import DatabaseTest
from ...model.hasfulltablecache import HasFullTableCache

class MockHasTableCache(HasFullTableCache):

    """A simple HasFullTableCache that returns the same cache key
    for every object.
    """

    _cache = HasFullTableCache.RESET
    _id_cache = HasFullTableCache.RESET

    ID = "the only ID"
    KEY = "the only cache key"

    @property
    def id(self):
        return self.ID

    def cache_key(self):
        return self.KEY

class TestHasFullTableCache(DatabaseTest):

    def setup(self):
        super(TestHasFullTableCache, self).setup()
        self.mock_class = MockHasTableCache
        self.mock = MockHasTableCache()
        self.mock._cache = HasFullTableCache.RESET

    def test_reset_cache(self):
        self.mock_class._cache = object()
        self.mock_class._id_cache = object()
        self.mock_class.reset_cache()
        eq_(HasFullTableCache.RESET, self.mock_class._cache)
        eq_(HasFullTableCache.RESET, self.mock_class._id_cache)

    def test_cache_insert(self):
        temp_cache = {}
        temp_id_cache = {}
        self.mock_class._cache_insert(self.mock, temp_cache, temp_id_cache)
        eq_({MockHasTableCache.KEY: self.mock}, temp_cache)
        eq_({MockHasTableCache.ID: self.mock}, temp_id_cache)

    # populate_cache(), by_cache_key(), and by_id() are tested in
    # TestGenre since those methods must be backed by a real database
    # table.
