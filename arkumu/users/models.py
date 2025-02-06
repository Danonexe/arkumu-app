from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
#from arkumu.metadata.models import Hochschule

class CustomUserManager(UserManager):
    def _generate_unique_name(self, email):
        base_name = email.split('@')[0]
        name = base_name
        counter = 1
        
        while self.model.objects.filter(username=name).exists():
            name = f"{base_name}{counter}"
            counter += 1
            
        return name

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        
        unique_name = self._generate_unique_name(email)
        extra_fields.setdefault('username', unique_name)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        return self.create_user(email, password, **extra_fields)

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
            
        email = self.normalize_email(email)
        
        if 'username' not in extra_fields:
            extra_fields['username'] = self._generate_unique_name(email)

        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            # This allows for future SSO integration
            user.set_unusable_password()
        user.save(using=self._db)
        return user

class User(AbstractUser):
    """
    Custom User model that uses email as the primary identifier.
    Designed to be compatible with future SSO/Shibboleth integration.
    """

    class Roles(models.TextChoices):
        BASIC_USER = 'BASIC', _('Basic authenticated user')
        MEDIA_DOC = 'MEDIADOC', _('Media documentalist')
        MANAGER = 'MANAGER', _('Manager')
        SUPERMANAGER = 'SUPER', _('Super manager')
        TECHADMIN = 'TECH', _('Technical administrator')

    name = None  # type: ignore[assignment]
    email = models.EmailField(
        _("Email address"), 
        unique=True,
        help_text=_("User's email address")
    )
    '''
    institution = models.ForeignKey(
        Hochschule,
        on_delete=models.PROTECT,
        related_name='users',
        null=True,
        verbose_name=_("Institution")
    )
    '''
    role = models.CharField(
        max_length=20,
        choices=Roles.choices,
        default=Roles.BASIC_USER,
        verbose_name=_("Role")
    )

    first_name = None  # type: ignore[assignment]
    last_name = None  # type: ignore[assignment]

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # email is already required by USERNAME_FIELD

    objects = CustomUserManager()

    def get_display_name(self):
        """Get the user's display name (their username)."""
        return self.username

    def get_absolute_url(self) -> str:
        """Get URL for user's detail view.

        Returns:
            str: URL for user detail.

        """
        return reverse("users:detail", kwargs={"username": self.username})
