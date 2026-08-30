from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("O e-mail é obrigatório")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("email_verified", True)
        return self.create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField("e-mail", unique=True)
    full_name = models.CharField("nome completo", max_length=160)
    country = models.CharField("país", max_length=80, default="Brasil")
    language = models.CharField(max_length=10, default="pt-br")
    timezone = models.CharField(max_length=64, default="America/Sao_Paulo")
    email_verified = models.BooleanField(default=False)
    lifetime_access = models.BooleanField(default=False)
    communications_opt_in = models.BooleanField(default=False)
    terms_version = models.CharField(max_length=20, default="1.0")
    terms_accepted_at = models.DateTimeField(null=True, blank=True)
    privacy_version = models.CharField(max_length=20, default="1.0")
    privacy_accepted_at = models.DateTimeField(null=True, blank=True)
    deletion_requested_at = models.DateTimeField(null=True, blank=True)
    USERNAME_FIELD, REQUIRED_FIELDS = "email", ["full_name"]
    objects = UserManager()

    def __str__(self):
        return self.email
