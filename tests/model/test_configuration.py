# encoding: utf-8

from nose.tools import (
    assert_raises,
    assert_raises_regexp,
    assert_not_equal,
    eq_,
    set_trace,
)
from core.model import (
    ExternalIntegration,
    ConfigurationSetting,
    Admin,
    AdminRole,
)
from .. import DatabaseTest


class TestExternalIntegration(DatabaseTest):

    def setup(self):
        super(TestExternalIntegration, self).setup()
        self.external_integration, ignore = create(
            self._db, ExternalIntegration, goal=self._str, protocol=self._str
        )

    def test_for_library_and_goal(self):
        goal = self.external_integration.goal
        qu = ExternalIntegration.for_library_and_goal(
            self._db, self._default_library, goal
        )

        # This matches nothing because the ExternalIntegration is not
        # associated with the Library.
        eq_([], qu.all())
        get_one = ExternalIntegration.one_for_library_and_goal
        eq_(None, get_one(self._db, self._default_library, goal))

        # Associate the library with the ExternalIntegration and
        # the query starts matching it. one_for_library_and_goal
        # also starts returning it.
        self.external_integration.libraries.append(self._default_library)
        eq_([self.external_integration], qu.all())
        eq_(self.external_integration,
            get_one(self._db, self._default_library, goal))

        # Create another, similar ExternalIntegration. By itself, this
        # has no effect.
        integration2, ignore = create(
            self._db, ExternalIntegration, goal=goal, protocol=self._str
        )
        eq_([self.external_integration], qu.all())
        eq_(self.external_integration,
            get_one(self._db, self._default_library, goal))

        # Associate that ExternalIntegration with the library, and
        # the query starts picking it up, and one_for_library_and_goal
        # starts raising an exception.
        integration2.libraries.append(self._default_library)
        eq_(set([self.external_integration, integration2]), set(qu.all()))
        assert_raises_regexp(
            CannotLoadConfiguration,
            "Library .* defines multiple integrations with goal .*",
            get_one, self._db, self._default_library, goal
        )

    def test_with_setting_value(self):
        def results():
            # Run the query and return all results.
            return ExternalIntegration.with_setting_value(
                self._db, "protocol", "goal", "key", "value"
            ).all()

        # We start off with no results.
        eq_([], results())

        # This ExternalIntegration will not match the result,
        # even though protocol and goal match, because it
        # doesn't have the 'key' ConfigurationSetting set.
        integration = self._external_integration("protocol", "goal")
        eq_([], results())

        # Now 'key' is set, but set to the wrong value.
        setting = integration.setting("key")
        setting.value = "wrong"
        eq_([], results())

        # Now it's set to the right value, so we get a result.
        setting.value = "value"
        eq_([integration], results())

        # Create another, identical integration.
        integration2, is_new = create(
            self._db, ExternalIntegration, protocol="protocol", goal="goal"
        )
        assert integration2 != integration
        integration2.setting("key").value = "value"

        # Both integrations show up.
        eq_(set([integration, integration2]), set(results()))

        # If the integration's goal doesn't match, it doesn't show up.
        integration2.goal = "wrong"
        eq_([integration], results())

        # If the integration's protocol doesn't match, it doesn't show up.
        integration.protocol = "wrong"
        eq_([], results())

    def test_data_source(self):
        # For most collections, the protocol determines the
        # data source.
        collection = self._collection(protocol=ExternalIntegration.OVERDRIVE)
        eq_(DataSource.OVERDRIVE, collection.data_source.name)

        # For OPDS Import collections, data source is a setting which
        # might not be present.
        eq_(None, self._default_collection.data_source)

        # data source will be automatically created if necessary.
        self._default_collection.external_integration.setting(
            Collection.DATA_SOURCE_NAME_SETTING
        ).value = "New Data Source"
        eq_("New Data Source", self._default_collection.data_source.name)

    def test_set_key_value_pair(self):
        """Test the ability to associate extra key-value pairs with
        an ExternalIntegration.
        """
        eq_([], self.external_integration.settings)

        setting = self.external_integration.set_setting("website_id", "id1")
        eq_("website_id", setting.key)
        eq_("id1", setting.value)

        # Calling set() again updates the key-value pair.
        eq_([setting.id], [x.id for x in self.external_integration.settings])
        setting2 = self.external_integration.set_setting("website_id", "id2")
        eq_(setting.id, setting2.id)
        eq_("id2", setting2.value)

        eq_(setting2, self.external_integration.setting("website_id"))

    def test_explain(self):
        integration = self._external_integration(
            "protocol", "goal"
        )
        integration.name = "The Integration"
        integration.url = "http://url/"
        integration.username = "someuser"
        integration.password = "somepass"
        integration.setting("somesetting").value = "somevalue"

        # Two different libraries have slightly different
        # configurations for this integration.
        self._default_library.name = "First Library"
        self._default_library.integrations.append(integration)
        ConfigurationSetting.for_library_and_externalintegration(
            self._db, "library-specific", self._default_library, integration
        ).value = "value1"

        library2 = self._library()
        library2.name = "Second Library"
        library2.integrations.append(integration)
        ConfigurationSetting.for_library_and_externalintegration(
            self._db, "library-specific", library2, integration
        ).value = "value2"

        # If we decline to pass in a library, we get information about how
        # each library in the system configures this integration.

        expect = """ID: %s
Name: The Integration
Protocol/Goal: protocol/goal
library-specific='value1' (applies only to First Library)
library-specific='value2' (applies only to Second Library)
somesetting='somevalue'
url='http://url/'
username='someuser'""" % integration.id
        actual = integration.explain()
        eq_(expect, "\n".join(actual))

        # If we pass in a library, we only get information about
        # how that specific library configures the integration.
        for_library_2 = "\n".join(integration.explain(library=library2))
        assert "applies only to First Library" not in for_library_2
        assert "applies only to Second Library" in for_library_2

        # If we pass in True for include_secrets, we see the passwords.
        with_secrets = integration.explain(include_secrets=True)
        assert "password='somepass'" in with_secrets

class TestConfigurationSetting(DatabaseTest):

    def test_is_secret(self):
        """Some configuration settings are considered secrets,
        and some are not.
        """
        m = ConfigurationSetting._is_secret
        eq_(True, m('secret'))
        eq_(True, m('password'))
        eq_(True, m('its_a_secret_to_everybody'))
        eq_(True, m('the_password'))
        eq_(True, m('password_for_the_account'))
        eq_(False, m('public_information'))

        eq_(True,
            ConfigurationSetting.sitewide(self._db, "secret_key").is_secret)
        eq_(False,
            ConfigurationSetting.sitewide(self._db, "public_key").is_secret)

    def test_value_or_default(self):
        integration, ignore = create(
            self._db, ExternalIntegration, goal=self._str, protocol=self._str
        )
        setting = integration.setting("key")
        eq_(None, setting.value)

        # If the setting has no value, value_or_default sets the value to
        # the default, and returns the default.
        eq_("default value", setting.value_or_default("default value"))
        eq_("default value", setting.value)

        # Once the value is set, value_or_default returns the value.
        eq_("default value", setting.value_or_default("new default"))

        # If the setting has any value at all, even the empty string,
        # it's returned instead of the default.
        setting.value = ""
        eq_("", setting.value_or_default("default"))

    def test_value_inheritance(self):

        key = "SomeKey"

        # Here's a sitewide configuration setting.
        sitewide_conf = ConfigurationSetting.sitewide(self._db, key)

        # Its value is not set.
        eq_(None, sitewide_conf.value)

        # Set it.
        sitewide_conf.value = "Sitewide value"
        eq_("Sitewide value", sitewide_conf.value)

        # Here's an integration, let's say the SIP2 authentication mechanism
        sip, ignore = create(
            self._db, ExternalIntegration,
            goal=ExternalIntegration.PATRON_AUTH_GOAL, protocol="SIP2"
        )

        # It happens to a ConfigurationSetting for the same key used
        # in the sitewide configuration.
        sip_conf = ConfigurationSetting.for_externalintegration(key, sip)

        # But because the meaning of a configuration key differ so
        # widely across integrations, the SIP2 integration does not
        # inherit the sitewide value for the key.
        eq_(None, sip_conf.value)
        sip_conf.value = "SIP2 value"

        # Here's a library which has a ConfigurationSetting for the same
        # key used in the sitewide configuration.
        library = self._default_library
        library_conf = ConfigurationSetting.for_library(key, library)

        # Since all libraries use a given ConfigurationSetting to mean
        # the same thing, a library _does_ inherit the sitewide value
        # for a configuration setting.
        eq_("Sitewide value", library_conf.value)

        # Change the site-wide configuration, and the default also changes.
        sitewide_conf.value = "New site-wide value"
        eq_("New site-wide value", library_conf.value)

        # The per-library value takes precedence over the site-wide
        # value.
        library_conf.value = "Per-library value"
        eq_("Per-library value", library_conf.value)

        # Now let's consider a setting like the patron identifier
        # prefix.  This is set on the combination of a library and a
        # SIP2 integration.
        key = "patron_identifier_prefix"
        library_patron_prefix_conf = ConfigurationSetting.for_library_and_externalintegration(
            self._db, key, library, sip
        )
        eq_(None, library_patron_prefix_conf.value)

        # If the SIP2 integration has a value set for this
        # ConfigurationSetting, that value is inherited for every
        # individual library that uses the integration.
        generic_patron_prefix_conf = ConfigurationSetting.for_externalintegration(
            key, sip
        )
        eq_(None, generic_patron_prefix_conf.value)
        generic_patron_prefix_conf.value = "Integration-specific value"
        eq_("Integration-specific value", library_patron_prefix_conf.value)

        # Change the value on the integration, and the default changes
        # for each individual library.
        generic_patron_prefix_conf.value = "New integration-specific value"
        eq_("New integration-specific value", library_patron_prefix_conf.value)

        # The library+integration setting takes precedence over the
        # integration setting.
        library_patron_prefix_conf.value = "Library-specific value"
        eq_("Library-specific value", library_patron_prefix_conf.value)

    def test_duplicate(self):
        """You can't have two ConfigurationSettings for the same key,
        library, and external integration.

        (test_relationships shows that you can have two settings for the same
        key as long as library or integration is different.)
        """
        key = self._str
        integration, ignore = create(
            self._db, ExternalIntegration, goal=self._str, protocol=self._str
        )
        library = self._default_library
        setting = ConfigurationSetting.for_library_and_externalintegration(
            self._db, key, library, integration
        )
        setting2 = ConfigurationSetting.for_library_and_externalintegration(
            self._db, key, library, integration
        )
        eq_(setting.id, setting2.id)
        assert_raises(
            IntegrityError,
            create, self._db, ConfigurationSetting,
            key=key,
            library=library, external_integration=integration
        )

    def test_relationships(self):
        integration, ignore = create(
            self._db, ExternalIntegration, goal=self._str, protocol=self._str
        )
        eq_([], integration.settings)

        library = self._default_library
        eq_([], library.settings)

        # Create four different ConfigurationSettings with the same key.
        cs = ConfigurationSetting
        key = self._str

        for_neither = cs.sitewide(self._db, key)
        eq_(None, for_neither.library)
        eq_(None, for_neither.external_integration)

        for_library = cs.for_library(key, library)
        eq_(library, for_library.library)
        eq_(None, for_library.external_integration)

        for_integration = cs.for_externalintegration(key, integration)
        eq_(None, for_integration.library)
        eq_(integration, for_integration.external_integration)

        for_both = cs.for_library_and_externalintegration(
            self._db, key, library, integration
        )
        eq_(library, for_both.library)
        eq_(integration, for_both.external_integration)

        # We got four distinct objects with the same key.
        objs = [for_neither, for_library, for_integration, for_both]
        eq_(4, len(set(objs)))
        for o in objs:
            eq_(o.key, key)

        eq_([for_library, for_both], library.settings)
        eq_([for_integration, for_both], integration.settings)
        eq_(library, for_both.library)
        eq_(integration, for_both.external_integration)

        # If we delete the integration, all configuration settings
        # associated with it are deleted, even the one that's also
        # associated with the library.
        self._db.delete(integration)
        self._db.commit()
        eq_([for_library.id], [x.id for x in library.settings])

    def test_int_value(self):
        number = ConfigurationSetting.sitewide(self._db, "number")
        eq_(None, number.int_value)

        number.value = "1234"
        eq_(1234, number.int_value)

        number.value = "tra la la"
        assert_raises(ValueError, lambda: number.int_value)

    def test_float_value(self):
        number = ConfigurationSetting.sitewide(self._db, "number")
        eq_(None, number.int_value)

        number.value = "1234.5"
        eq_(1234.5, number.float_value)

        number.value = "tra la la"
        assert_raises(ValueError, lambda: number.float_value)

    def test_json_value(self):
        jsondata = ConfigurationSetting.sitewide(self._db, "json")
        eq_(None, jsondata.int_value)

        jsondata.value = "[1,2]"
        eq_([1,2], jsondata.json_value)

        jsondata.value = "tra la la"
        assert_raises(ValueError, lambda: jsondata.json_value)

    def test_explain(self):
        """Test that ConfigurationSetting.explain gives information
        about all site-wide configuration settings.
        """
        ConfigurationSetting.sitewide(self._db, "a_secret").value = "1"
        ConfigurationSetting.sitewide(self._db, "nonsecret_setting").value = "2"

        integration = self._external_integration("a protocol", "a goal")

        actual = ConfigurationSetting.explain(self._db, include_secrets=True)
        expect = """Site-wide configuration settings:
---------------------------------
a_secret='1'
nonsecret_setting='2'"""
        eq_(expect, "\n".join(actual))

        without_secrets = "\n".join(ConfigurationSetting.explain(
            self._db, include_secrets=False
        ))
        assert 'a_secret' not in without_secrets
        assert 'nonsecret_setting' in without_secrets


class TestAdmin(DatabaseTest):
    def setup(self):
        super(TestAdmin, self).setup()
        self.admin, ignore = create(self._db, Admin, email=u"admin@nypl.org")
        self.admin.password = u"password"

    def test_password_hashed(self):
        assert_raises(NotImplementedError, lambda: self.admin.password)
        assert self.admin.password_hashed.startswith('$2a$')

    def test_with_password(self):
        self._db.delete(self.admin)
        eq_([], Admin.with_password(self._db).all())

        admin, ignore = create(self._db, Admin, email="admin@nypl.org")
        eq_([], Admin.with_password(self._db).all())

        admin.password = "password"
        eq_([admin], Admin.with_password(self._db).all())

        admin2, ignore = create(self._db, Admin, email="admin2@nypl.org")
        eq_([admin], Admin.with_password(self._db).all())

        admin2.password = "password2"
        eq_(set([admin, admin2]), set(Admin.with_password(self._db).all()))

    def test_has_password(self):
        eq_(True, self.admin.has_password(u"password"))
        eq_(False, self.admin.has_password(u"banana"))

    def test_authenticate(self):
        other_admin, ignore = create(self._db, Admin, email=u"other@nypl.org")
        other_admin.password = u"banana"
        eq_(self.admin, Admin.authenticate(self._db, "admin@nypl.org", "password"))
        eq_(None, Admin.authenticate(self._db, "other@nypl.org", "password"))
        eq_(None, Admin.authenticate(self._db, "example@nypl.org", "password"))

    def test_roles(self):
        # The admin has no roles yet.
        eq_(False, self.admin.is_system_admin())
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(False, self.admin.is_librarian(self._default_library))

        self.admin.add_role(AdminRole.SYSTEM_ADMIN)
        eq_(True, self.admin.is_system_admin())
        eq_(True, self.admin.is_sitewide_library_manager())
        eq_(True, self.admin.is_sitewide_librarian())
        eq_(True, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_librarian(self._default_library))

        self.admin.remove_role(AdminRole.SYSTEM_ADMIN)
        self.admin.add_role(AdminRole.SITEWIDE_LIBRARY_MANAGER)
        eq_(False, self.admin.is_system_admin())
        eq_(True, self.admin.is_sitewide_library_manager())
        eq_(True, self.admin.is_sitewide_librarian())
        eq_(True, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_librarian(self._default_library))

        self.admin.remove_role(AdminRole.SITEWIDE_LIBRARY_MANAGER)
        self.admin.add_role(AdminRole.SITEWIDE_LIBRARIAN)
        eq_(False, self.admin.is_system_admin())
        eq_(False, self.admin.is_sitewide_library_manager())
        eq_(True, self.admin.is_sitewide_librarian())
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_librarian(self._default_library))

        self.admin.remove_role(AdminRole.SITEWIDE_LIBRARIAN)
        self.admin.add_role(AdminRole.LIBRARY_MANAGER, self._default_library)
        eq_(False, self.admin.is_system_admin())
        eq_(False, self.admin.is_sitewide_library_manager())
        eq_(False, self.admin.is_sitewide_librarian())
        eq_(True, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_librarian(self._default_library))

        self.admin.remove_role(AdminRole.LIBRARY_MANAGER, self._default_library)
        self.admin.add_role(AdminRole.LIBRARIAN, self._default_library)
        eq_(False, self.admin.is_system_admin())
        eq_(False, self.admin.is_sitewide_library_manager())
        eq_(False, self.admin.is_sitewide_librarian())
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_librarian(self._default_library))

        self.admin.remove_role(AdminRole.LIBRARIAN, self._default_library)
        eq_(False, self.admin.is_system_admin())
        eq_(False, self.admin.is_sitewide_library_manager())
        eq_(False, self.admin.is_sitewide_librarian())
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(False, self.admin.is_librarian(self._default_library))

        other_library = self._library()
        self.admin.add_role(AdminRole.LIBRARY_MANAGER, other_library)
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_library_manager(other_library))
        self.admin.add_role(AdminRole.SITEWIDE_LIBRARIAN)
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(True, self.admin.is_library_manager(other_library))
        eq_(True, self.admin.is_librarian(self._default_library))
        eq_(True, self.admin.is_librarian(other_library))
        self.admin.remove_role(AdminRole.LIBRARY_MANAGER, other_library)
        eq_(False, self.admin.is_library_manager(self._default_library))
        eq_(False, self.admin.is_library_manager(other_library))
        eq_(True, self.admin.is_librarian(self._default_library))
        eq_(True, self.admin.is_librarian(other_library))

    def test_can_see_collection(self):
        # This collection is only visible to system admins since it has no libraries.
        c1 = self._collection()

        # This collection is visible to libraries of its library.
        c2 = self._collection()
        c2.libraries += [self._default_library]

        # The admin has no roles yet.
        eq_(False, self.admin.can_see_collection(c1));
        eq_(False, self.admin.can_see_collection(c2));

        self.admin.add_role(AdminRole.SYSTEM_ADMIN)
        eq_(True, self.admin.can_see_collection(c1))
        eq_(True, self.admin.can_see_collection(c2))

        self.admin.remove_role(AdminRole.SYSTEM_ADMIN)
        self.admin.add_role(AdminRole.SITEWIDE_LIBRARY_MANAGER)
        eq_(False, self.admin.can_see_collection(c1));
        eq_(True, self.admin.can_see_collection(c2));

        self.admin.remove_role(AdminRole.SITEWIDE_LIBRARY_MANAGER)
        self.admin.add_role(AdminRole.SITEWIDE_LIBRARIAN)
        eq_(False, self.admin.can_see_collection(c1));
        eq_(True, self.admin.can_see_collection(c2));

        self.admin.remove_role(AdminRole.SITEWIDE_LIBRARIAN)
        self.admin.add_role(AdminRole.LIBRARY_MANAGER, self._default_library)
        eq_(False, self.admin.can_see_collection(c1));
        eq_(True, self.admin.can_see_collection(c2));

        self.admin.remove_role(AdminRole.LIBRARY_MANAGER, self._default_library)
        self.admin.add_role(AdminRole.LIBRARIAN, self._default_library)
        eq_(False, self.admin.can_see_collection(c1));
        eq_(True, self.admin.can_see_collection(c2));

        self.admin.remove_role(AdminRole.LIBRARIAN, self._default_library)
        eq_(False, self.admin.can_see_collection(c1));
        eq_(False, self.admin.can_see_collection(c2));
