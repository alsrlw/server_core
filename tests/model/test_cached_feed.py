# encoding: utf-8
import datetime
from nose.tools import (
    assert_raises,
    assert_raises_regexp,
    assert_not_equal,
    eq_,
    set_trace,
)
import core.lane
from core.lane import (
    Facets,
    Pagination,
    WorkList,
)
import core.model
from core.model.cached_feed import (
    CachedFeed,
)
import core.classifier
from core.classifier import (
    Classifier,
    Fantasy,
    Romance,
    Science_Fiction,
    Drama,
)
from .. import DatabaseTest

class TestCachedFeed(DatabaseTest):

    def test_fetch_page_feeds(self):
        """CachedFeed.fetch retrieves paginated feeds from the database if
        they exist, and prepares them for creation if not.
        """
        m = CachedFeed.fetch
        lane = self._lane()
        page = CachedFeed.PAGE_TYPE
        annotator = object()

        # A page feed for a lane with no facets or pagination.
        feed, fresh = m(self._db, lane, page, None, None, annotator)
        eq_(page, feed.type)

        # The feed is not usable as-is because there's no content.
        eq_(False, fresh)

        # If we set content, we can fetch the same feed and then it
        # becomes usable.
        feed.content = "some content"
        feed.timestamp = (
            datetime.datetime.utcnow() - datetime.timedelta(seconds=5)
        )
        feed2, fresh = m(self._db, lane, page, None, None, annotator)
        eq_(feed, feed2)
        eq_(True, fresh)

        # But a feed is not considered fresh if it's older than `max_age`
        # seconds.
        feed, fresh = m(
            self._db, lane, page, None, None, annotator, max_age=0
        )
        eq_(False, fresh)

        # This feed has no unique key because its lane ID and type
        # are enough to uniquely identify it.
        eq_(None, feed.unique_key)
        eq_("", feed.pagination)
        eq_("", feed.facets)

        # Now let's introduce some pagination and facet information.
        facets = Facets.default(self._default_library)
        pagination = Pagination.default()
        feed2, fresh = m(
            self._db, lane, page, facets, pagination, annotator
        )
        assert feed2 != feed
        eq_(pagination.query_string, feed2.pagination)
        eq_(facets.query_string, feed2.facets)

        # There's still no need for a unique key because pagination
        # and facets are taken into account when trying to uniquely
        # identify a feed.
        eq_(None, feed.unique_key)

        # However, a lane based on a WorkList has no lane ID, so a
        # unique key is necessary.
        worklist = WorkList()
        worklist.initialize(
            library=self._default_library, display_name="aworklist",
            languages=["eng", "spa"], audiences=[Classifier.AUDIENCE_CHILDREN]
        )
        feed, fresh = m(
            self._db, worklist, page, None, None, annotator
        )
        # The unique key incorporates the WorkList's display name,
        # its languages, and its audiences.
        eq_("aworklist-eng,spa-Children", feed.unique_key)

    def test_fetch_group_feeds(self):
        # Group feeds don't need to worry about facets or pagination,
        # but they have their own complications.

        m = CachedFeed.fetch
        lane = self._lane()
        groups = CachedFeed.GROUPS_TYPE
        annotator = object()

        # Ask for a groups feed for a lane.
        feed, usable = m(self._db, lane, groups, None, None, annotator)

        # The feed is not usable because there's no content.
        eq_(False, usable)

        # Group-type feeds are too expensive to generate, so when
        # asked to produce one we prepared a page-type feed instead.
        eq_(CachedFeed.PAGE_TYPE, feed.type)
        eq_(lane, feed.lane)
        eq_(None, feed.unique_key)
        eq_("", feed.facets)
        eq_("", feed.pagination)

        # But what if a group feed had been created ahead of time
        # through some other mechanism?
        feed.content = "some content"
        feed.type = groups
        feed.timestamp = datetime.datetime.utcnow()

        # Now fetch() finds the feed, but because there was content
        # and a recent timestamp, it's now usable and there's no need
        # to change the type.
        feed2, usable = m(self._db, lane, groups, None, None, annotator)
        eq_(feed, feed2)
        eq_(True, usable)
        eq_(groups, feed.type)
        eq_("some content", feed.content)

        # If we pass in force_refresh then the feed is always treated as
        # stale.
        feed, usable = m(self._db, lane, groups, None, None, annotator,
                         force_refresh=True)
        eq_(False, usable)
