from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from .models import Event
from .serializers import EventSerializer, EventCreateSerializer

def upload_image_to_cloudinary(image_source):
    """Upload file or base64 to Cloudinary, return secure URL or None"""
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            image_source,
            folder="master_events/events",
            resource_type="image",
            transformation=[{
                'width': 1200, 'height': 600,
                'crop': 'fill', 'quality': 'auto', 'fetch_format': 'auto'
            }]
        )
        print(f"✅ Cloudinary upload: {result['secure_url']}")
        return result['secure_url']
    except Exception as e:
        print(f"⚠️ Cloudinary upload failed: {e}")
        return None


@api_view(['GET'])
@permission_classes([AllowAny])
def event_list(request):
    city     = request.query_params.get('city')
    category = request.query_params.get('category')
    search   = request.query_params.get('search')
    events   = Event.objects.filter(is_active=True, sales_open=True)
    if city:     events = events.filter(city__icontains=city)
    if category: events = events.filter(category=category)
    if search:   events = events.filter(name__icontains=search)
    return Response(EventSerializer(events, many=True).data)


@api_view(['GET'])
@permission_classes([AllowAny])
def event_detail(request, pk):
    try:
        event = Event.objects.get(pk=pk, is_active=True)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)
    return Response(EventSerializer(event).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def event_create(request):
    if request.user.role != 'organizer':
        return Response({'error': 'Only organizers can create events'}, status=403)

    # Build mutable data dict
    data = {}
    for key in request.data:
        data[key] = request.data[key]

    # ── Handle image ──────────────────────────────────────────
    image_file = request.FILES.get('image')
    image_str  = data.get('image', '')

    if image_file:
        # Real file upload
        url = upload_image_to_cloudinary(image_file)
        if url:
            data['image'] = url
        else:
            data.pop('image', None)

    elif isinstance(image_str, str) and image_str.startswith('data:'):
        # Base64 from frontend
        url = upload_image_to_cloudinary(image_str)
        if url:
            data['image'] = url
        else:
            data.pop('image', None)

    elif isinstance(image_str, str) and image_str.startswith('http'):
        # Already a URL — keep as is
        pass

    else:
        # No image — remove so serializer doesn't complain
        data.pop('image', None)

    serializer = EventCreateSerializer(data=data, context={'request': request})
    if serializer.is_valid():
        event = serializer.save()
        return Response(EventSerializer(event).data, status=201)

    print(f"Event create errors: {serializer.errors}")
    return Response(serializer.errors, status=400)


@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def event_update(request, pk):
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)

    data = {}
    for key in request.data:
        data[key] = request.data[key]

    image_file = request.FILES.get('image')
    image_str  = data.get('image', '')

    if image_file:
        url = upload_image_to_cloudinary(image_file)
        if url: data['image'] = url
    elif isinstance(image_str, str) and image_str.startswith('data:'):
        url = upload_image_to_cloudinary(image_str)
        if url: data['image'] = url

    serializer = EventCreateSerializer(event, data=data, partial=True, context={'request': request})
    if serializer.is_valid():
        serializer.save()
        return Response(EventSerializer(event).data)
    return Response(serializer.errors, status=400)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def event_delete(request, pk):
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)
    event.is_active = False
    event.save()
    return Response({'message': 'Event deleted'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_events(request):
    if request.user.role != 'organizer':
        return Response({'error': 'Only organizers can view this'}, status=403)
    events = Event.objects.filter(organizer=request.user, is_active=True)
    return Response(EventSerializer(events, many=True).data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def toggle_sales(request, pk):
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)
    event.sales_open = not event.sales_open
    event.save()
    return Response({'sales_open': event.sales_open})