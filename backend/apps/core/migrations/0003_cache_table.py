from django.core.management import call_command
from django.db import migrations


def create_cache_table(apps, schema_editor):
    # the shared cache (settings.CACHES); a no-op when the configured cache isn't database-backed
    call_command("createcachetable", database=schema_editor.connection.alias, verbosity=0)


class Migration(migrations.Migration):
    dependencies = [("core", "0002_sitesettings_instant_changes")]

    operations = [migrations.RunPython(create_cache_table, migrations.RunPython.noop)]
