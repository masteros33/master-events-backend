from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, parser_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.response import Response
from .models import Event
from .serializers import EventSerializer, EventCreateSerializer, PublicEventSerializer


def upload_to_cloudinary(source):
    try:
        import cloudinary.uploader
        result = cloudinary.uploader.upload(
            source,
            folder="master_events/events",
            resource_type="image",
            transformation=[{
                'width': 1200, 'height': 600,
                'crop': 'fill', 'quality': 'auto', 'fetch_format': 'auto'
            }]
        )
        print(f"✅ Cloudinary upload OK: {result['secure_url']}")
        return result['secure_url']
    except Exception as e:
        print(f"⚠️ Cloudinary upload failed: {e}")
        return None


# ── Public event list ─────────────────────────────────────────
@api_view(['GET', 'HEAD'])
@permission_classes([AllowAny])
def event_list(request):
    if request.method == 'HEAD':
        return Response(status=200)
    city       = request.query_params.get('city')
    category   = request.query_params.get('category')
    search     = request.query_params.get('search')
    event_type = request.query_params.get('event_type')
    currency   = request.query_params.get('currency')
    events     = Event.objects.filter(is_active=True, sales_open=True)
    if city:       events = events.filter(city__icontains=city)
    if category:   events = events.filter(category=category)
    if search:     events = events.filter(name__icontains=search)
    if event_type: events = events.filter(event_type=event_type)
    if currency:   events = events.filter(currency=currency)
    return Response(EventSerializer(events, many=True).data)


# ── Public event detail by ID ─────────────────────────────────
@api_view(['GET'])
@permission_classes([AllowAny])
def event_detail(request, pk):
    try:
        event = Event.objects.get(pk=pk, is_active=True)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)
    return Response(EventSerializer(event).data)


# ── NEW: Public event landing page by slug ────────────────────
# This powers tgma.masterevents.events → /api/events/slug/tgma/
@api_view(['GET'])
@permission_classes([AllowAny])
def event_by_slug(request, slug):
    try:
        event = Event.objects.get(slug=slug, is_active=True)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)
    return Response(PublicEventSerializer(event).data)


# ── NEW: Organizer event attendees/registrations ──────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def event_attendees(request, pk):
    """Returns both paid ticket holders and free registrations for an event"""
    try:
        event = Event.objects.get(pk=pk, organizer=request.user)
    except Event.DoesNotExist:
        return Response({'error': 'Event not found'}, status=404)

    from tickets.models import Ticket, Registration

    # Paid ticket holders
    tickets = Ticket.objects.filter(
        event=event
    ).exclude(status='transferred').select_related('owner')

    ticket_data = [{
        'type':        'ticket',
        'name':        t.owner.get_full_name() or t.owner.email,
        'email':       t.owner.email,
        'quantity':    t.quantity,
        'amount_paid': float(t.price_paid),
        'status':      t.status,
        'ticket_id':   str(t.ticket_id),
        'joined_at':   t.created_at.isoformat(),
        'redeemed':    t.status == 'redeemed',
    } for t in tickets]

    # Free registrations
    registrations = Registration.objects.filter(
        event=event
    ).select_related('attendee')

    reg_data = [{
        'type':            'registration',
        'name':            r.attendee.get_full_name() or r.attendee.email,
        'email':           r.attendee.email,
        'quantity':        r.quantity,
        'amount_paid':     0,
        'status':          r.status,
        'registration_id': str(r.registration_id),
        'joined_at':       r.created_at.isoformat(),
        'redeemed':        r.status == 'redeemed',
    } for r in registrations]

    return Response({
        'event_name':          event.name,
        'event_type':          event.event_type,
        'total_attendees':     len(ticket_data) + len(reg_data),
        'ticket_holders':      ticket_data,
        'registrations':       reg_data,
    })


# ── Create event ──────────────────────────────────────────────
@api_view(['POST'])
@permission_classes([IsAuthenticated])
@parser_classes([MultiPartParser, FormParser, JSONParser])
def event_create(request):
    if request.user.role != 'organizer':
        return Response(
            {'error': 'Only organizers can create events'},
            status=status.HTTP_403_FORBIDDEN
        )

    data = {}
    for key in request.data:
        val = request.data[key]
        data[key] = val[0] if isinstance(val, list) else val

    image_file = request.FILES.get('image')
    image_val  = data.get('image', '')

    if image_file:
        url = upload_to_cloudinary(image_file)
        data['image'] = url or ''
    elif isinstance(image_val, str) and image_val.startswith('data:image'):
        url = upload_to_cloudinary(image_val)
        data['image'] = url or ''
    elif isinstance(image_val, str) and image_val.startswith('http'):
        data['image'] = image_val
    else:
        data['image'] = ''

    serializer = EventCreateSerializer(data=data, context={'request': request})
    if serializer.is_valid():
        event = serializer.save()
        print(f"✅ Event created: {event.name} (id={event.id}, slug={event.slug}, type={event.event_type})")
        return Response(EventSerializer(event).data, status=201)

    print(f"❌ Event create validation errors: {serializer.errors}")
    return Response(serializer.errors, status=400)


# ── Update event ──────────────────────────────────────────────
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
        val = request.data[key]
        data[key] = val[0] if isinstance(val, list) else val

    image_file = request.FILES.get('image')
    image_val  = data.get('image', '')

    if image_file:
        url = upload_to_cloudinary(image_file)
        if url: data['image'] = url
    elif isinstance(image_val, str) and image_val.startswith('data:image'):
        url = upload_to_cloudinary(image_val)
        if url: data['image'] = url
    elif isinstance(image_val, str) and image_val.startswith('http'):
        data['image'] = image_val

    serializer = EventCreateSerializer(
        event, data=data, partial=True, context={'request': request}
    )
    if serializer.is_valid():
        serializer.save()
        return Response(EventSerializer(event).data)

    print(f"❌ Event update errors: {serializer.errors}")
    return Response(serializer.errors, status=400)


# ── Delete event ──────────────────────────────────────────────
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


# ── My events ─────────────────────────────────────────────────
@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_events(request):
    if request.user.role != 'organizer':
        return Response({'error': 'Only organizers can view this'}, status=403)
    events = Event.objects.filter(organizer=request.user, is_active=True)
    return Response(EventSerializer(events, many=True).data)


# ── Toggle sales ──────────────────────────────────────────────
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