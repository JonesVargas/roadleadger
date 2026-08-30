from django.db import migrations


def publish_legal_documents(apps, schema_editor):
    LegalPage = apps.get_model("core", "LegalPage")
    from core.legal_content import LEGAL_VERSION, PRIVACY_PT_BR, TERMS_PT_BR

    LegalPage.objects.update_or_create(
        kind="terms", defaults={"version": LEGAL_VERSION, "body": TERMS_PT_BR}
    )
    LegalPage.objects.update_or_create(
        kind="privacy", defaults={"version": LEGAL_VERSION, "body": PRIVACY_PT_BR}
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0001_initial")]
    operations = [migrations.RunPython(publish_legal_documents, migrations.RunPython.noop)]
