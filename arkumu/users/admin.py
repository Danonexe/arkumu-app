from allauth.account.decorators import secure_admin_login
from django.conf import settings
from django.contrib import admin
from django.contrib.auth import admin as auth_admin
from django.utils.translation import gettext_lazy as _

from .forms import UserAdminChangeForm
from .forms import UserAdminCreationForm
from .models import User, Organization

if settings.DJANGO_ADMIN_FORCE_ALLAUTH:
    # Force the `admin` sign in process to go through the `django-allauth` workflow:
    # https://docs.allauth.org/en/latest/common/admin.html#admin
    admin.autodiscover()
    admin.site.login = secure_admin_login(admin.site.login)  # type: ignore[method-assign]


@admin.register(User)
class UserAdmin(auth_admin.UserAdmin):
    form = UserAdminChangeForm
    add_form = UserAdminCreationForm
    fieldsets = (
        (None, {"fields": ("username", "password")}),
        (_("Personal info"), {"fields": ("name", "email")}),
        (_("Organization & Role"), {"fields": ("organization", "role")}),
        (_("Shibboleth Integration"), {
            "fields": (
                "auth_source", 
                "shibboleth_eppn", 
                "shibboleth_persistent_id",
                "shibboleth_affiliation",
                "is_federated_user",
                "last_shibboleth_login"
            ),
            "classes": ("collapse",),
        }),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                ),
            },
        ),
        (_("Important dates"), {"fields": ("last_login", "date_joined")}),
    )
    list_display = ["username", "name", "organization", "role", "is_active", "is_staff", "is_superuser"]
    list_filter = ["is_active", "is_staff", "is_superuser", "role", "organization"]
    search_fields = ["name", "username", "email", "shibboleth_eppn"]
    autocomplete_fields = ["organization"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "domain", "is_active"]
    list_filter = ["is_active"]
    search_fields = ["name", "code", "domain"]
    prepopulated_fields = {"code": ["name"]}
    
    def get_queryset(self, request):
        """Optimize queries by prefetching related users."""
        return super().get_queryset(request).prefetch_related("users")
