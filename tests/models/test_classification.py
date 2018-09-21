# encoding: utf-8
from nose.tools import (
    assert_raises,
    assert_raises_regexp,
    eq_,
    set_trace,
)
from psycopg2.extras import NumericRange
from sqlalchemy.exc import IntegrityError
from .. import DatabaseTest
from classifier import Classifier
from core.model import (
    create,
    get_one,
    get_one_or_create,
)
from core.model.classification import (
    Subject,
    Genre,
)

class TestSubject(DatabaseTest):

    def test_lookup_errors(self):
        """Subject.lookup will complain if you don't give it
        enough information to find a Subject.
        """
        assert_raises_regexp(
            ValueError, "Cannot look up Subject with no type.",
            Subject.lookup, self._db, None, "identifier", "name"
        )
        assert_raises_regexp(
            ValueError,
            "Cannot look up Subject when neither identifier nor name is provided.",
            Subject.lookup, self._db, Subject.TAG, None, None
        )

    def test_lookup_autocreate(self):
        # By default, Subject.lookup creates a Subject that doesn't exist.
        identifier = self._str
        name = self._str
        subject, was_new = Subject.lookup(
            self._db, Subject.TAG, identifier, name
        )
        eq_(True, was_new)
        eq_(identifier, subject.identifier)
        eq_(name, subject.name)

        # But you can tell it not to autocreate.
        identifier2 = self._str
        subject, was_new = Subject.lookup(
            self._db, Subject.TAG, identifier2, None, autocreate=False
        )
        eq_(False, was_new)
        eq_(None, subject)

    def test_lookup_by_name(self):
        """We can look up a subject by its name, without providing an
        identifier."""
        s1 = self._subject(Subject.TAG, "i1")
        s1.name = "A tag"
        eq_((s1, False), Subject.lookup(self._db, Subject.TAG, None, "A tag"))

        # If we somehow get into a state where there are two Subjects
        # with the same name, Subject.lookup treats them as interchangeable.
        s2 = self._subject(Subject.TAG, "i2")
        s2.name = "A tag"

        subject, is_new = Subject.lookup(self._db, Subject.TAG, None, "A tag")
        assert subject in [s1, s2]
        eq_(False, is_new)

    def test_assign_to_genre_can_remove_genre(self):
        # Here's a Subject that identifies children's books.
        subject, was_new = Subject.lookup(self._db, Subject.TAG, "Children's books", None)

        # The genre and audience data for this Subject is totally wrong.
        subject.audience = Classifier.AUDIENCE_ADULT
        subject.target_age = NumericRange(1,10)
        subject.fiction = False
        sf, ignore = Genre.lookup(self._db, "Science Fiction")
        subject.genre = sf

        # But calling assign_to_genre() will fix it.
        subject.assign_to_genre()
        eq_(Classifier.AUDIENCE_CHILDREN, subject.audience)
        eq_(NumericRange(None, None, '[]'), subject.target_age)
        eq_(None, subject.genre)
        eq_(None, subject.fiction)

class TestGenre(DatabaseTest):

    def test_full_table_cache(self):
        """We use Genre as a convenient way of testing
        HasFullTableCache.populate_cache, which requires a real
        SQLAlchemy ORM class to operate on.
        """

        # We start with an unusable object as the cache.
        eq_(Genre.RESET, Genre._cache)
        eq_(Genre.RESET, Genre._id_cache)

        # When we call populate_cache()...
        Genre.populate_cache(self._db)

        # Every Genre in the database is copied to the cache.
        dont_call_this = object
        drama, is_new = Genre.by_cache_key(self._db, "Drama", dont_call_this)
        eq_("Drama", drama.name)
        eq_(False, is_new)

        # The ID of every genre is copied to the ID cache.
        eq_(drama, Genre._id_cache[drama.id])
        drama2 = Genre.by_id(self._db, drama.id)
        eq_(drama2, drama)

    def test_by_id(self):

        # Get a genre to test with.
        drama = get_one(self._db, Genre, name="Drama")

        # Since we went right to the database, that didn't change the
        # fact that the ID cache is uninitialized.
        eq_(Genre.RESET, Genre._id_cache)

        # Look up the same genre using by_id...
        eq_(drama, Genre.by_id(self._db, drama.id))

        # ... and the ID cache is fully initialized.
        eq_(drama, Genre._id_cache[drama.id])
        assert len(Genre._id_cache) > 1

    def test_by_cache_key_miss_triggers_create_function(self):
        _db = self._db
        class Factory(object):

            def __init__(self):
                self.called = False

            def call_me(self):
                self.called = True
                genre, is_new = get_one_or_create(_db, Genre, name="Drama")
                return genre, is_new

        factory = Factory()
        Genre._cache = {}
        Genre._id_cache = {}
        genre, is_new = Genre.by_cache_key(self._db, "Drama", factory.call_me)
        eq_("Drama", genre.name)
        eq_(False, is_new)
        eq_(True, factory.called)

        # The Genre object created in call_me has been associated with the
        # Genre's cache key in the table-wide cache.
        eq_(genre, Genre._cache[genre.cache_key()])

        # The cache by ID has been similarly populated.
        eq_(genre, Genre._id_cache[genre.id])

    def test_by_cache_key_miss_when_cache_is_reset_populates_cache(self):
        # The cache is not in a state to be used.
        eq_(Genre._cache, Genre.RESET)

        # Call Genreby_cache_key...
        drama, is_new = Genre.by_cache_key(
            self._db, "Drama",
            lambda: get_one_or_create(self._db, Genre, name="Drama")
        )
        eq_("Drama", drama.name)
        eq_(False, is_new)

        # ... and the cache is repopulated
        assert drama.cache_key() in Genre._cache
        assert drama.id in Genre._id_cache

    def test_by_cache_key_hit_returns_cached_object(self):

        # If the object we ask for is not already in the cache, this
        # function will be called and raise an exception.
        def exploding_create_hook():
            raise Exception("Kaboom")
        drama, ignore = get_one_or_create(self._db, Genre, name="Drama")
        Genre._cache = { "Drama": drama }
        drama2, is_new = Genre.by_cache_key(
            self._db, "Drama", exploding_create_hook
        )

        # The object was already in the cache, so we just looked it up.
        # No exception.
        eq_(drama, drama2)
        eq_(False, is_new)

    def test_name_is_unique(self):
        g1, ignore = Genre.lookup(self._db, "A Genre", autocreate=True)
        g2, ignore = Genre.lookup(self._db, "A Genre", autocreate=True)
        eq_(g1, g2)

        assert_raises(IntegrityError, create, self._db, Genre, name="A Genre")

    def test_default_fiction(self):
        sf, ignore = Genre.lookup(self._db, "Science Fiction")
        nonfiction, ignore = Genre.lookup(self._db, "History")
        eq_(True, sf.default_fiction)
        eq_(False, nonfiction.default_fiction)

        # Create a previously unknown genre.
        genre, ignore = Genre.lookup(
            self._db, "Some Weird Genre", autocreate=True
        )

        # We don't know its default fiction status.
        eq_(None, genre.default_fiction)
