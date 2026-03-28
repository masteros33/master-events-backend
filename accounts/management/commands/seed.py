from django.core.management.base import BaseCommand
from accounts.models import User
from events.models import Event
from decimal import Decimal

class Command(BaseCommand):
    help = 'Seed database with initial data'

    def handle(self, *args, **kwargs):
        # Create organizer
        if not User.objects.filter(email='jude@test.com').exists():
            User.objects.create_user(
                email='jude@test.com',
                password='test1234',
                first_name='Jude',
                last_name='Test',
                role='organizer'
            )
            self.stdout.write('✅ Organizer created')

        # Create platform account
        if not User.objects.filter(email='platform@masterevents.com').exists():
            User.objects.create_user(
                email='platform@masterevents.com',
                password='platform1234',
                first_name='Master',
                last_name='Events',
                role='organizer'
            )
            self.stdout.write('✅ Platform account created')

        # Create events
        platform = User.objects.get(email='platform@masterevents.com')
        org = User.objects.get(email='jude@test.com')

        events = [
            dict(name="Afrobeats Carnival", category="music", venue="Accra Sports Stadium", city="Accra", date="2026-04-25", time="20:00:00", price=Decimal("150"), total_tickets=5000, description="The biggest Afrobeats night in Ghana!"),
            dict(name="Tech Summit Ghana", category="tech", venue="Kempinski Hotel", city="Accra", date="2026-05-02", time="09:00:00", price=Decimal("350"), total_tickets=500, description="Ghana's premier tech conference."),
            dict(name="Accra Jazz Night", category="music", venue="Alliance Francaise", city="Accra", date="2026-04-20", time="19:00:00", price=Decimal("120"), total_tickets=200, description="An evening of smooth jazz in Accra."),
            dict(name="Taste of Ghana Food Festival", category="food", venue="Labadi Beach Hotel", city="Accra", date="2026-05-10", time="12:00:00", price=Decimal("80"), total_tickets=1000, description="Celebrate Ghanaian cuisine."),
            dict(name="Kumasi Cultural Festival", category="arts", venue="Kumasi Cultural Centre", city="Kumasi", date="2026-05-15", time="10:00:00", price=Decimal("50"), total_tickets=2000, description="Experience Ashanti culture."),
            dict(name="Ghana Business Summit", category="business", venue="Movenpick Hotel", city="Accra", date="2026-05-20", time="08:00:00", price=Decimal("500"), total_tickets=300, description="Connect with business leaders."),
            dict(name="Beach Party Labadi", category="music", venue="Labadi Beach", city="Accra", date="2026-04-18", time="16:00:00", price=Decimal("100"), total_tickets=3000, description="Biggest beach party of the year!"),
            dict(name="Gospel Night Perez Dome", category="music", venue="Perez Dome", city="Accra", date="2026-04-30", time="18:00:00", price=Decimal("60"), total_tickets=10000, description="A night of praise and worship."),
            dict(name="Accra Marathon 2026", category="sports", venue="Independence Square", city="Accra", date="2026-05-05", time="06:00:00", price=Decimal("200"), total_tickets=5000, description="Run through the streets of Accra."),
            dict(name="Comedy Night Accra", category="other", venue="National Theatre", city="Accra", date="2026-04-22", time="19:00:00", price=Decimal("90"), total_tickets=800, description="Laugh out loud with Ghana's best comedians."),
        ]

        org_events = [
            dict(name="Accra Jazz Night", category="music", venue="Alliance Francaise", city="Accra", date="2026-04-20", time="19:00:00", price=Decimal("120"), total_tickets=200, description="An evening of smooth jazz."),
            dict(name="Afrobeats Carnival", category="music", venue="Accra Sports Stadium", city="Accra", date="2026-04-25", time="20:00:00", price=Decimal("150"), total_tickets=5000, description="The biggest Afrobeats night!"),
            dict(name="Tech Summit Ghana", category="tech", venue="Kempinski Hotel", city="Accra", date="2026-05-02", time="09:00:00", price=Decimal("350"), total_tickets=500, description="Ghana's premier tech conference."),
        ]

        for e in events:
            if not Event.objects.filter(name=e['name'], organizer=platform).exists():
                Event.objects.create(organizer=platform, is_active=True, sales_open=True, **e)

        for e in org_events:
            if not Event.objects.filter(name=e['name'], organizer=org).exists():
                Event.objects.create(organizer=org, is_active=True, sales_open=True, **e)

        self.stdout.write(self.style.SUCCESS('✅ Database seeded successfully!'))
