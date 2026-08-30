from django.db import models


class Feature(models.Model):
    title = models.CharField(max_length=120)
    description = models.TextField()
    icon = models.CharField(max_length=40, default="route")
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]


class FAQ(models.Model):
    question = models.CharField(max_length=240)
    answer = models.TextField()
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]


class UpdatePost(models.Model):
    title = models.CharField(max_length=180)
    slug = models.SlugField(unique=True)
    summary = models.TextField()
    body = models.TextField()
    published_at = models.DateTimeField()
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_at"]


class LegalPage(models.Model):
    kind = models.CharField(
        max_length=20, choices=[("terms", "Termos"), ("privacy", "Privacidade")], unique=True
    )
    version = models.CharField(max_length=20)
    body = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)


class ServiceStatus(models.Model):
    name = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=[("operational", "Operacional"), ("degraded", "Instável"), ("down", "Indisponível")],
        default="operational",
    )
    message = models.CharField(max_length=240, blank=True)
    updated_at = models.DateTimeField(auto_now=True)


class SocialLink(models.Model):
    name = models.CharField(max_length=50)
    url = models.URLField()
    active = models.BooleanField(default=True)
