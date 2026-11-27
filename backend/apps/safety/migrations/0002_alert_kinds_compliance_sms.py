from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("safety", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="alert",
            name="kind",
            field=models.CharField(
                choices=[
                    ("sos", "Guest SOS"),
                    ("urgent_issue", "Urgent issue"),
                    ("low_review", "Low review"),
                    ("conflict", "Calendar conflict"),
                    ("security", "Security / fraud"),
                    ("payment", "Payment problem"),
                    ("compliance", "Compliance"),
                    ("sms", "SMS delivery"),
                ],
                max_length=14,
            ),
        ),
    ]
