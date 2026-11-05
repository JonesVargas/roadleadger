from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def preserve_access(apps, schema_editor):
    db = schema_editor.connection.alias
    User = apps.get_model("accounts", "User")
    Subscription = apps.get_model("subscriptions", "Subscription")
    Grant = apps.get_model("subscriptions", "AppGrant")
    from django.utils import timezone
    now = timezone.now()
    editions = {"player": ("offline", "player"), "company": ("offline", "player", "company")}
    for user in User.objects.using(db).filter(is_active=True).iterator():
        access = {}

        def include(product, expiry, plan_code="", features=()):
            for app in editions.get(product, ()):
                previous = access.get(app)
                if previous is None or (previous["expires_at"] is not None and
                                        (expiry is None or expiry > previous["expires_at"])):
                    access[app] = {"expires_at": expiry, "plan_code": plan_code, "features": list(features)}

        sub = Subscription.objects.using(db).filter(user=user, status__in=("active", "authorized")).select_related("plan").first()
        if sub and (sub.current_period_end is None or sub.current_period_end > now):
            include(sub.plan.product, sub.current_period_end, sub.plan.code, sub.plan.entitlements)
        if user.manual_access_expires_at is None or user.manual_access_expires_at > now:
            include(user.manual_plan, user.manual_access_expires_at)
        if user.lifetime_access:
            for app in editions["company"]:
                access[app] = {"expires_at": None, "plan_code": "lifetime", "features": ["all"]}
        for app, defaults in access.items():
            Grant.objects.using(db).get_or_create(user_id=user.pk, application=app, defaults=defaults)


class Migration(migrations.Migration):
    dependencies = [("subscriptions", "0006_planchange_operation"), ("accounts", "0004_companyownershiplicense")]
    operations = [
        migrations.CreateModel(
            name="AppGrant",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("application", models.CharField(max_length=12)),
                ("enabled", models.BooleanField(default=True)),
                ("expires_at", models.DateTimeField(blank=True, null=True)),
                ("plan_code", models.CharField(blank=True, max_length=50)),
                ("features", models.JSONField(blank=True, default=list)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="+", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="app_grants", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "application"), name="one_grant_per_roadledger_app")]},
        ),
        migrations.RunPython(preserve_access, migrations.RunPython.noop),
    ]
