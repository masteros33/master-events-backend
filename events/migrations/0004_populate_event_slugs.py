from django.db import migrations
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    Event = apps.get_model('events', 'Event')
    for event in Event.objects.filter(slug=''):
        base = slugify(event.name)[:40] or f"event-{event.id}"
        slug = base
        i = 1
        while Event.objects.filter(slug=slug).exclude(pk=event.pk).exists():
            slug = f"{base}-{i}"
            i += 1
        event.slug = slug
        event.save(update_fields=['slug'])


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0003_event_country_event_currency_event_event_type_and_more'),
    ]

    operations = [
        migrations.RunPython(populate_slugs, reverse_func),
    ]