from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('events', '0004_populate_event_slugs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='event',
            name='slug',
            field=models.SlugField(blank=True, max_length=60, unique=True),
        ),
    ]