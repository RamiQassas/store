from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from .models import ChatRoom, ChatMessage, ChatCannedReply


def can_manage_support(user, store=None):
    if not user.is_authenticated:
        return False
    if store:
        if store.owner == user:
            return True
        if user.store_employments.filter(store=store, role__in=["owner", "manager", "support"]).exists():
            return True
        if user.is_staff or user.is_superuser:
            return True
        return False
    if user.is_staff or user.is_superuser:
        return True
    return user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()


def get_guest_id(request):
    """Retrieves or creates a unique session-based guest ID."""
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def chat_list(request):
    """Lists available chat rooms for the user or staff."""
    active_store = getattr(request, 'store', None)
    is_manager = can_manage_support(request.user, active_store)
    
    if request.user.is_authenticated and is_manager:
        rooms = ChatRoom.objects.filter(store=active_store).select_related('user', 'assigned_agent')
    elif request.user.is_authenticated:
        rooms = ChatRoom.objects.filter(store=active_store, user=request.user).select_related('assigned_agent')
    else:
        # Guest user - track by session
        room_id = request.session.get('support_chat_room_id')
        if room_id:
            rooms = ChatRoom.objects.filter(store=active_store, id=room_id).select_related('assigned_agent')
        else:
            rooms = ChatRoom.objects.none()
    
    # If a guest/user has only one room, redirect directly to it
    if rooms.count() == 1 and not (request.user.is_authenticated and is_manager):
        return redirect('chat_room', room_id=rooms.first().id)
    elif rooms.count() == 0 and not (request.user.is_authenticated and is_manager):
        return redirect('create_chat')

    return render(request, 'site/chat_list.html', {'rooms': rooms, 'is_manager': is_manager})


def chat_room(request, room_id):
    """Displays an individual chat room with message history."""
    active_store = getattr(request, 'store', None)
    is_manager = can_manage_support(request.user, active_store)
    if is_manager:
        room = get_object_or_404(ChatRoom, id=room_id, store=active_store)
    elif request.user.is_authenticated:
        room = get_object_or_404(ChatRoom, id=room_id, user=request.user, store=active_store)
    else:
        # Guest check
        session_room_id = request.session.get('support_chat_room_id')
        if not session_room_id or str(session_room_id) != str(room_id):
             raise Http404("Chat room not found or access denied.")
        room = get_object_or_404(ChatRoom, id=room_id, store=active_store)
    
    messages_history = room.messages.all().select_related('sender')
    
    # Reset unread count
    if is_manager:
        room.unread_staff_count = 0
    else:
        room.unread_user_count = 0
    room.save()
    
    canned_replies = ChatCannedReply.objects.filter(is_active=True) if is_manager else None
    
    return render(request, 'site/chat_room.html', {
        'room': room,
        'chat_messages': messages_history,
        'canned_replies': canned_replies,
        'is_manager': is_manager,
    })


def create_chat(request):
    """Initializes a new support chat room."""
    active_store = getattr(request, 'store', None)
    subject = request.GET.get('subject', 'طلب دعم فني')
    guest_name = request.POST.get('guest_name', '').strip()
    guest_phone = request.POST.get('guest_phone', '').strip()
    
    if request.user.is_authenticated:
        # Check if there's already an active (not closed) chat for this user in this store
        active_chat = ChatRoom.objects.filter(store=active_store, user=request.user).exclude(status=ChatRoom.Status.CLOSED).first()
        if active_chat:
            return redirect('chat_room', room_id=active_chat.id)
        room = ChatRoom.objects.create(store=active_store, user=request.user, subject=subject)
        user_label = request.user.email
    else:
        # Guest user - session tracking
        session_room_id = request.session.get('support_chat_room_id')
        if session_room_id:
            active_chat = ChatRoom.objects.filter(store=active_store, id=session_room_id).exclude(status=ChatRoom.Status.CLOSED).first()
            if active_chat:
                return redirect('chat_room', room_id=active_chat.id)
        
        # If no POST data for name, we might need to show a small form or handle it
        if request.method == "GET" and not guest_name:
            return render(request, 'site/guest_support_init.html', {'subject': subject})

        from apps.accounts.models import User
        system_guest = User.objects.filter(email="guest@raqamiyat.com").first()
        if not system_guest:
             # Fallback to a non-staff user if possible to avoid notification loops
             system_guest = User.objects.filter(is_staff=False, is_superuser=False).first()
             if not system_guest:
                  system_guest = User.objects.filter(is_staff=True).first()
        
        # Since ChatRoom doesn't have metadata field in model (per FieldError earlier), 
        # let's use the subject to store guest info or staff_notes
        room = ChatRoom.objects.create(
            store=active_store,
            user=system_guest, 
            subject=f"{subject} - زائر: {guest_name}",
            staff_notes=f"بيانات الزائر:\nالاسم: {guest_name}\nالهاتف: {guest_phone or 'غير متوفر'}"
        )
        request.session['support_chat_room_id'] = str(room.id)
        user_label = f"الزائر {guest_name}"

    # Auto-add welcome message (Admin Configurable)
    from apps.accounts.models import User
    from .models import SupportSettings
    
    settings_obj = SupportSettings.objects.first()
    if settings_obj:
        welcome_text = settings_obj.welcome_message
    else:
        # Fallback to canned replies or default
        welcome_reply = ChatCannedReply.objects.filter(title__icontains="ترحيب", is_active=True).first()
        welcome_text = welcome_reply.body if welcome_reply else "مرحباً بك! كيف يمكننا مساعدتك اليوم؟"
    
    # Get a staff/admin user to be the sender of the welcome message
    welcome_sender = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first()
    
    if welcome_sender:
        ChatMessage.objects.create(
            room=room,
            sender=welcome_sender,
            text=welcome_text,
            is_staff_reply=True
        )
    
    if active_store:
        from apps.notifications.services import notify_user
        if active_store.owner:
            notify_user(
                user=active_store.owner,
                title="طلب دعم جديد",
                body=f"قام {user_label} بفتح تذكرة دعم جديدة في متجرك: {subject}",
                action_url=f"/support/chats/{room.id}/",
                category='admin_new_support'
            )
        for employee in active_store.employees.select_related('user'):
            if employee.user and employee.user != active_store.owner:
                notify_user(
                    user=employee.user,
                    title="طلب دعم جديد",
                    body=f"قام {user_label} بفتح تذكرة دعم جديدة في المتجر: {subject}",
                    action_url=f"/support/chats/{room.id}/",
                    category='admin_new_support'
                )
    else:
        from apps.notifications.services import notify_staff
        notify_staff(
            title="طلب دعم جديد",
            body=f"قام {user_label} بفتح تذكرة دعم جديدة: {subject}",
            action_url=f"/support/chats/{room.id}/",
            category='admin_new_support'
        )

    return redirect('chat_room', room_id=room.id)


def chat_file_upload(request, room_id):
    active_store = getattr(request, 'store', None)
    if request.method == "POST" and request.FILES.get("file"):
        room = get_object_or_404(ChatRoom, id=room_id, store=active_store)
        
        # Permission check
        is_manager = can_manage_support(request.user, active_store)
        is_owner = False
        if request.user.is_authenticated and room.user == request.user:
            is_owner = True
        elif not request.user.is_authenticated:
            session_room_id = request.session.get('support_chat_room_id')
            if str(session_room_id) == str(room.id):
                is_owner = True
                
        if not (is_manager or is_owner):
            return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)
            
        file = request.FILES.get("file")
        is_image = file.content_type.startswith("image/")
        
        # For guest sender, we use the system guest user
        sender = request.user if request.user.is_authenticated else room.user

        message = ChatMessage.objects.create(
            room=room,
            sender=sender,
            file=file,
            is_image=is_image,
            is_staff_reply=is_manager
        )
        
        # Trigger room updates
        room.last_message_at = timezone.now()
        if message.is_staff_reply:
            room.unread_user_count += 1
        else:
            room.unread_staff_count += 1
        room.save()
        
        if is_manager:
            sender_name = "الدعم الفني"
        else:
            sender_name = f"{request.user.first_name} {request.user.last_name}".strip() or request.user.email if request.user.is_authenticated else "زائر"
        
        return JsonResponse({
            "status": "success",
            "message_id": str(message.id),
            "file_id": str(message.id),
            "file_url": message.file.url,
            "is_image": is_image,
            "timestamp": message.created_at.strftime("%H:%M"),
            "sender_name": sender_name
        })


def close_chat(request, room_id):
    """Allows staff or owners to close a chat room."""
    active_store = getattr(request, 'store', None)
    room = get_object_or_404(ChatRoom, id=room_id, store=active_store)
    
    # Permission Check: Staff OR Owner OR Guest with session
    can_close = False
    if can_manage_support(request.user, active_store):
        can_close = True
    elif request.user.is_authenticated and room.user == request.user:
        can_close = True
    elif not request.user.is_authenticated:
        session_room_id = request.session.get('support_chat_room_id')
        if str(session_room_id) == str(room.id):
            can_close = True
            
    if not can_close:
        messages.error(request, "غير مصرح لك بإغلاق هذه المحادثة.")
        return redirect('chat_list')
        
    room.status = ChatRoom.Status.CLOSED
    room.save()
    messages.success(request, f"تم إغلاق المحادثة بنجاح.")
    return redirect('chat_list')
