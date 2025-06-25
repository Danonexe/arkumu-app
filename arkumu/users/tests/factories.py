from collections.abc import Sequence
from typing import Any

from factory import Faker, SubFactory
from factory import post_generation
from factory.django import DjangoModelFactory

from arkumu.users.models import User, Organization


class OrganizationFactory(DjangoModelFactory):
    name = Faker("company")
    code = Faker("domain_word")
    domain = Faker("domain_name")
    shibboleth_entity_id = Faker("url")
    is_active = True

    class Meta:
        model = Organization
        django_get_or_create = ["code"]


class UserFactory(DjangoModelFactory[User]):
    username = Faker("user_name")
    email = Faker("email")
    name = Faker("name")
    role = "researcher"
    auth_source = "local"
    is_federated_user = False
    organization = SubFactory(OrganizationFactory)

    @post_generation
    def password(self, create: bool, extracted: Sequence[Any], **kwargs):  # noqa: FBT001
        password = (
            extracted
            if extracted
            else Faker(
                "password",
                length=42,
                special_chars=True,
                digits=True,
                upper_case=True,
                lower_case=True,
            ).evaluate(None, None, extra={"locale": None})
        )
        self.set_password(password)

    @classmethod
    def _after_postgeneration(cls, instance, create, results=None):
        """Save again the instance if creating and at least one hook ran."""
        if create and results and not cls._meta.skip_postgeneration_save:
            # Some post-generation hooks ran, and may have modified us.
            instance.save()

    class Meta:
        model = User
        django_get_or_create = ["username"]


class ShibbolethUserFactory(UserFactory):
    """Factory for Shibboleth-authenticated users"""
    auth_source = "shibboleth"
    is_federated_user = True
    shibboleth_eppn = Faker("email")
    shibboleth_affiliation = "staff@example.edu"


class ManagerUserFactory(UserFactory):
    """Factory for manager users"""
    role = "manager"


class SuperManagerUserFactory(UserFactory):
    """Factory for super manager users"""
    role = "super_manager"


class SystemAdminUserFactory(UserFactory):
    """Factory for system admin users"""
    role = "system_admin"


class ArchivistUserFactory(UserFactory):
    """Factory for archivist users"""
    role = "archivist"
