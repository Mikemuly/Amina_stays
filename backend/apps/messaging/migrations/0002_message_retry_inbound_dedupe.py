from django.db import migrations, models


def forget_repeated_inbound_ids(apps, schema_editor):
    """Rows saved from a webhook Africa's Talking delivered twice: the first keeps the provider id, so the
    unique constraint below can be created on a database that already holds such repeats."""
    Message = apps.get_model("messaging", "Message")
    seen = set()
    rows = Message.objects.filter(direction="in").exclude(provider_id="").order_by("id")
    for pk, provider_id in rows.values_list("pk", "provider_id").iterator():
        if provider_id in seen:
            Message.objects.filter(pk=pk).update(provider_id="")
        seen.add(provider_id)


class Migration(migrations.Migration):
    dependencies = [
        ("messaging", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="message",
            name="next_attempt_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Queued: retry from then. Sending: the worker's lease runs out then.",
                null=True,
            ),
        ),
        migrations.RunPython(forget_repeated_inbound_ids, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="message",
            constraint=models.UniqueConstraint(
                condition=models.Q(("direction", "in"), models.Q(("provider_id", ""), _negated=True)),
                fields=("provider_id",),
                name="message_inbound_provider_id_unique",
            ),
        ),
    ]
