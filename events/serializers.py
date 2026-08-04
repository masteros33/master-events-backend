from rest_framework import serializers
from .models import Event, TicketTier
from accounts.serializers import UserSerializer


class TicketTierSerializer(serializers.ModelSerializer):
    remaining   = serializers.ReadOnlyField()
    is_sold_out = serializers.ReadOnlyField()

    class Meta:
        model  = TicketTier
        fields = ['id', 'name', 'price', 'capacity', 'sold', 'remaining', 'is_sold_out', 'order']
        read_only_fields = ['id', 'sold']


class EventSerializer(serializers.ModelSerializer):
    organizer         = UserSerializer(read_only=True)
    tickets_remaining = serializers.ReadOnlyField()
    is_sold_out       = serializers.ReadOnlyField()
    revenue           = serializers.ReadOnlyField()
    event_url         = serializers.ReadOnlyField()
    registrations_count = serializers.SerializerMethodField()
    tiers             = TicketTierSerializer(many=True, read_only=True)

    class Meta:
        model  = Event
        fields = [
            'id', 'organizer', 'name', 'description', 'category',
            'venue', 'city', 'country', 'date', 'time',
            'event_type', 'currency', 'price',
            'total_tickets', 'tickets_sold', 'tickets_remaining',
            'is_sold_out', 'image', 'sales_open', 'is_active',
            'revenue', 'slug', 'event_url',
            'registrations_count', 'created_at',
            'tiers',
        ]
        read_only_fields = ['tickets_sold', 'organizer', 'slug']

    def get_registrations_count(self, obj):
        try:
            return obj.registrations.count()
        except Exception:
            return 0


class EventCreateSerializer(serializers.ModelSerializer):
    image = serializers.CharField(
        max_length=500, required=False, allow_blank=True, allow_null=True
    )
    ticket_tiers = serializers.ListField(
        child=serializers.DictField(), required=False, write_only=True
    )

    class Meta:
        model  = Event
        fields = [
            'name', 'description', 'category',
            'venue', 'city', 'country',
            'date', 'time',
            'event_type', 'currency', 'price',
            'total_tickets', 'image', 'sales_open',
            'ticket_tiers',
        ]

    def validate(self, data):
        # Free events must have price 0
        if data.get('event_type') == 'free':
            data['price'] = 0
        # Paid events must have price > 0
        if data.get('event_type') == 'paid':
            if not data.get('price') or float(data.get('price', 0)) <= 0:
                raise serializers.ValidationError({'price': 'Paid events must have a price greater than 0.'})
        return data

    def validate_description(self, value):
        return value or ''

    def create(self, validated_data):
        tiers_data = validated_data.pop('ticket_tiers', None)
        validated_data['organizer'] = self.context['request'].user
        event = super().create(validated_data)

        if tiers_data:
            for i, t in enumerate(tiers_data):
                TicketTier.objects.create(
                    event=event,
                    name=t.get('name', f'Tier {i+1}'),
                    price=t.get('price', 0),
                    capacity=t.get('capacity', 0),
                    order=i,
                )
            # keep event.total_tickets consistent with the sum of tier
            # capacities, so non-tier-aware code paths (dashboards, CSV
            # export, etc.) still show correct totals
            event.total_tickets = sum(int(t.get('capacity', 0)) for t in tiers_data)
            event.save(update_fields=['total_tickets'])

        return event

    def update(self, instance, validated_data):
        validated_data.pop('ticket_tiers', None)  # tier edits handled separately, not here
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        return instance


class PublicEventSerializer(serializers.ModelSerializer):
    """Lightweight serializer for public event landing pages — no revenue/organizer details"""
    tickets_remaining   = serializers.ReadOnlyField()
    is_sold_out         = serializers.ReadOnlyField()
    registrations_count = serializers.SerializerMethodField()
    organizer_name      = serializers.SerializerMethodField()
    tiers               = TicketTierSerializer(many=True, read_only=True)

    class Meta:
        model  = Event
        fields = [
            'id', 'name', 'description', 'category',
            'venue', 'city', 'country', 'date', 'time',
            'event_type', 'currency', 'price', 
            'total_tickets', 'tickets_remaining', 'is_sold_out',
            'image', 'sales_open', 'slug',
            'registrations_count', 'organizer_name',
            'tiers',
        ]

    def get_registrations_count(self, obj):
        try:
            return obj.registrations.count()
        except Exception:
            return 0

    def get_organizer_name(self, obj):
        org = obj.organizer
        return org.get_full_name() or org.email