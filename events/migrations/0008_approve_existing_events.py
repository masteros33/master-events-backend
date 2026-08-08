from django.db import migrations


def approve_existing_events(apps, schema_editor):
    """
    One-time backfill: every event that existed before the is_approved
    gate was introduced gets grandfathered in as approved, so nothing
    already live silently disappears from public discovery. Only
    events created AFTER this migration runs start at is_approved=False
    (the model default) and go through the real review flow.
    """
    Event = apps.get_model('events', 'Event')
    Event.objects.all().update(is_approved=True)


def reverse_noop(apps, schema_editor):
    # Intentionally a no-op — reversing this migration shouldn't
    # un-approve events, since that could hide events that were
    # legitimately reviewed and approved through the admin flow
    # after this migration ran.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0007_event_is_approved'),
    ]

    operations = [
        migrations.RunPython(approve_existing_events, reverse_noop),
    ]