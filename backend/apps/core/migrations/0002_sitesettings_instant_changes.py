from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="sitesettings",
            name="instant_changes",
            field=models.BooleanField(
                default=True,
                help_text="Guests can change or extend into free nights and pay the difference instantly; off = you approve each change",
            ),
        ),
    ]
