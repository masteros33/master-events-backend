from rest_framework import serializers
from .models import Event
from accounts.serializers import UserSerializer


class EventSerializer(serializers.ModelSerializer):
    organizer         = UserSerializer(read_only=True)
    tickets_remaining = serializers.ReadOnlyField()
    is_sold_out       = serializers.ReadOnlyField()
    revenue           = serializers.ReadOnlyField()
    event_url         = serializers.ReadOnlyField()
    registrations_count = serializers.SerializerMethodField()

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

    class Meta:
        model  = Event
        fields = [
            'name', 'description', 'category',
            'venue', 'city', 'country',
            'date', 'time',
            'event_type', 'currency', 'price',
            'total_tickets', 'image', 'sales_open',
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
        validated_data['organizer'] = self.context['request'].user
        return super().create(validated_data)

    def update(self, instance, validated_data):
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

    class Meta:
        model  = Event
        fields = [
            'id', 'name', 'description', 'category',
            'venue', 'city', 'country', 'date', 'time',
            'event_type', 'currency', 'price',
            'total_tickets', 'tickets_remaining', 'is_sold_out',
            'image', 'sales_open', 'slug',
            'registrations_count', 'organizer_name',
        ]

    def get_registrations_count(self, obj):
        try:
            return obj.registrations.count()
        except Exception:
            return 0

    def get_organizer_name(self, obj):
        org = obj.organizer
        return org.get_full_name() or org.email