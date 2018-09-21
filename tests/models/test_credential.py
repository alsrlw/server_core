# encoding: utf-8
from nose.tools import (
    eq_,
    set_trace,
)
import datetime
from .. import DatabaseTest
from core.model.credential import (
    Credential,
    DelegatedPatronIdentifier,
    DRMDeviceIdentifier,
)
from core.model.datasource import DataSource

class TestCredentials(DatabaseTest):

    def test_temporary_token(self):

        # Create a temporary token good for one hour.
        duration = datetime.timedelta(hours=1)
        data_source = DataSource.lookup(self._db, DataSource.ADOBE)
        patron = self._patron()
        now = datetime.datetime.utcnow()
        expect_expires = now + duration
        token, is_new = Credential.temporary_token_create(
            self._db, data_source, "some random type", patron, duration)
        eq_(data_source, token.data_source)
        eq_("some random type", token.type)
        eq_(patron, token.patron)
        expires_difference = abs((token.expires-expect_expires).seconds)
        assert expires_difference < 2

        # Now try to look up the credential based solely on the UUID.
        new_token = Credential.lookup_by_token(
            self._db, data_source, token.type, token.credential)
        eq_(new_token, token)

        # When we call lookup_and_expire_temporary_token, the token is automatically
        # expired and we cannot use it anymore.
        new_token = Credential.lookup_and_expire_temporary_token(
            self._db, data_source, token.type, token.credential)
        eq_(new_token, token)
        assert new_token.expires < now

        new_token = Credential.lookup_by_token(
            self._db, data_source, token.type, token.credential)
        eq_(None, new_token)

        new_token = Credential.lookup_and_expire_temporary_token(
            self._db, data_source, token.type, token.credential)
        eq_(None, new_token)

        # A token with no expiration date is treated as expired...
        token.expires = None
        self._db.commit()
        no_expiration_token = Credential.lookup_by_token(
            self._db, data_source, token.type, token.credential)
        eq_(None, no_expiration_token)

        # ...unless we specifically say we're looking for a persistent token.
        no_expiration_token = Credential.lookup_by_token(
            self._db, data_source, token.type, token.credential,
            allow_persistent_token=True
        )
        eq_(token, no_expiration_token)

    def test_specify_value_of_temporary_token(self):
        """By default, a temporary token has a randomly generated value, but
        you can give a specific value to represent a temporary token you got
        from somewhere else.
        """
        patron = self._patron()
        duration = datetime.timedelta(hours=1)
        data_source = DataSource.lookup(self._db, DataSource.ADOBE)
        token, is_new = Credential.temporary_token_create(
            self._db, data_source, "some random type", patron, duration,
            "Some random value"
        )
        eq_("Some random value", token.credential)

    def test_temporary_token_overwrites_old_token(self):
        duration = datetime.timedelta(hours=1)
        data_source = DataSource.lookup(self._db, DataSource.ADOBE)
        patron = self._patron()
        old_token, is_new = Credential.temporary_token_create(
            self._db, data_source, "some random type", patron, duration)
        eq_(True, is_new)
        old_credential = old_token.credential

        # Creating a second temporary token overwrites the first.
        token, is_new = Credential.temporary_token_create(
            self._db, data_source, "some random type", patron, duration)
        eq_(False, is_new)
        eq_(token.id, old_token.id)
        assert old_credential != token.credential

    def test_persistent_token(self):

        # Create a persistent token.
        data_source = DataSource.lookup(self._db, DataSource.ADOBE)
        patron = self._patron()
        token, is_new = Credential.persistent_token_create(
            self._db, data_source, "some random type", patron
        )
        eq_(data_source, token.data_source)
        eq_("some random type", token.type)
        eq_(patron, token.patron)

        # Now try to look up the credential based solely on the UUID.
        new_token = Credential.lookup_by_token(
            self._db, data_source, token.type, token.credential,
            allow_persistent_token=True
        )
        eq_(new_token, token)
        credential = new_token.credential

        # We can keep calling lookup_by_token and getting the same
        # Credential object with the same .credential -- it doesn't
        # expire.
        again_token = Credential.lookup_by_token(
            self._db, data_source, token.type, token.credential,
            allow_persistent_token=True
        )
        eq_(again_token, new_token)
        eq_(again_token.credential, credential)

    def test_cannot_look_up_nonexistent_token(self):
        data_source = DataSource.lookup(self._db, DataSource.ADOBE)
        new_token = Credential.lookup_by_token(
            self._db, data_source, "no such type", "no such credential")
        eq_(None, new_token)


class TestDelegatedPatronIdentifier(DatabaseTest):

    def test_get_one_or_create(self):
        library_uri = self._url
        patron_identifier = self._str
        identifier_type = DelegatedPatronIdentifier.ADOBE_ACCOUNT_ID
        def make_id():
            return "id1"
        identifier, is_new = DelegatedPatronIdentifier.get_one_or_create(
            self._db, library_uri, patron_identifier, identifier_type,
            make_id
        )
        eq_(True, is_new)
        eq_(library_uri, identifier.library_uri)
        eq_(patron_identifier, identifier.patron_identifier)
        # id_1() was called.
        eq_("id1", identifier.delegated_identifier)

        # Try the same thing again but provide a different create_function
        # that raises an exception if called.
        def explode():
            raise Exception("I should never be called.")
        identifier2, is_new = DelegatedPatronIdentifier.get_one_or_create(
            self._db, library_uri, patron_identifier, identifier_type, explode
        )
        # The existing identifier was looked up.
        eq_(False, is_new)
        eq_(identifier2.id, identifier.id)
        # id_2() was not called.
        eq_("id1", identifier2.delegated_identifier)


class TestDRMDeviceIdentifier(DatabaseTest):

    def setup(self):
        super(TestDRMDeviceIdentifier, self).setup()
        self.data_source = DataSource.lookup(self._db, DataSource.ADOBE)
        self.patron = self._patron()
        self.credential, ignore = Credential.persistent_token_create(
            self._db, self.data_source, "Some Credential", self.patron)

    def test_devices_for_credential(self):
        device_id_1, new = self.credential.register_drm_device_identifier("foo")
        eq_("foo", device_id_1.device_identifier)
        eq_(self.credential, device_id_1.credential)
        eq_(True, new)

        device_id_2, new = self.credential.register_drm_device_identifier("foo")
        eq_(device_id_1, device_id_2)
        eq_(False, new)

        device_id_3, new = self.credential.register_drm_device_identifier("bar")

        eq_(set([device_id_1, device_id_3]), set(self.credential.drm_device_identifiers))

    def test_deregister(self):
        device, new = self.credential.register_drm_device_identifier("foo")
        self.credential.deregister_drm_device_identifier("foo")
        eq_([], self.credential.drm_device_identifiers)
        eq_([], self._db.query(DRMDeviceIdentifier).all())
