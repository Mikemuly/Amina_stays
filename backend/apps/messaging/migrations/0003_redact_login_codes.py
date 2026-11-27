"""Login-code SMS used to be stored with the code in them, so the host inbox showed it. Those codes have long
expired, but no stored copy should hold one: redact them, and any thread preview that quotes one."""

import re

from django.db import migrations

CODE = re.compile(r"\b\d{6}\b")
REDACTED = "••••••"  # as messaging.services.REDACTED


def redact_login_codes(apps, schema_editor):
    Message = apps.get_model("messaging", "Message")
    Thread = apps.get_model("messaging", "Thread")
    for m in Message.objects.filter(kind="otp").only("id", "thread_id", "body").iterator():
        body = CODE.sub(REDACTED, m.body)
        if body != m.body:
            Thread.objects.filter(pk=m.thread_id, last_preview=m.body[:160]).update(last_preview=body[:160])
            Message.objects.filter(pk=m.pk).update(body=body)


class Migration(migrations.Migration):
    dependencies = [("messaging", "0002_message_retry_inbound_dedupe")]

    operations = [migrations.RunPython(redact_login_codes, migrations.RunPython.noop)]
