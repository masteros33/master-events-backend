from rest_framework import serializers
from .models import Event
from accounts.serializers import UserSerializer

class EventSerializer(serializers.ModelSerializer):
    organizer         = UserSerializer(read_only=True)
    tickets_remaining = serializers.ReadOnlyField()
    is_sold_out       = serializers.ReadOnlyField()
    revenue           = serializers.ReadOnlyField()

    class Meta:
        model  = Event
        fields = [
            'id', 'organizer', 'name', 'description', 'category',
            'venue', 'city', 'date', 'time', 'price', 'total_tickets',
            'tickets_sold', 'tickets_remaining', 'is_sold_out',
            'image', 'sales_open', 'is_active', 'revenue', 'created_at'
        ]
        read_only_fields = ['tickets_sold', 'organizer']


class EventCreateSerializer(serializers.ModelSerializer):
    # ✅ image is now a URL string — accept it as CharField
    image = serializers.CharField(max_length=500, required=False, allow_blank=True, allow_null=True)

    class Meta:
        model  = Event
        fields = [
            'name', 'description', 'category', 'venue', 'city',
            'date', 'time', 'price', 'total_tickets', 'image', 'sales_open'
        ]

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