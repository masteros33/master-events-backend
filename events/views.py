from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from .models import Event
from .serializers import EventSerializer, EventCreateSerializer

@api_view(['GET'])
@permission_classes([AllowAny])
def event_list(request):
    city = request.query_params.get('city', None)
    category = request.query_params.get('category', None)
    search = request.query_params.get('search', None)

    events = Event.objects.filter(is_active=True, sales_open=True)

    if city:
        events = events.filter(city__icontains=city)
    if category:
        events = events.filter(category=category)
    if search:
        events = events.filter(name__icontains=search)

    serializer = EventSerializer(events, many=True)
    return Response(serializer.data)

@api_view(['GET'])
@permission_classes([AllowAny])
def event_detail(request, pk):
    try:
        event = Event.objects.get(pk=pk, is_active=True)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = EventSerializer(event)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def event_create(request):
    if request.user.role != 'organizer':
        return Response({'error': 'Only organizers can create events'}, status=status.HTTP_403_FORBIDDEN)
    serializer = EventCreateSerializer(data=request.data, context={'request': request})
    if serializer.is_valid():
        event = serializer.save()
        return Response(EventSerializer(event).data, status=status.HTTP_201_CREATED)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def event_update(request, pk):
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
    serializer = EventCreateSerializer(event, data=request.data, partial=True)
    if serializer.is_valid():
        serializer.save()
        return Response(EventSerializer(event).data)
    return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def event_delete(request, pk):
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
    event.is_active = False
    event.save()
    return Response({'message': 'Event deleted'})

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_events(request):
    if request.user.role != 'organizer':
        return Response({'error': 'Only organizers can view this'}, status=status.HTTP_403_FORBIDDEN)
    events = Event.objects.filter(organizer=request.user, is_active=True)
    serializer = EventSerializer(events, many=True)
    return Response(serializer.data)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_sales(request, pk):
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
    event.sales_open = not event.sales_open
    event.save()
    return Response({'sales_open': event.sales_open})