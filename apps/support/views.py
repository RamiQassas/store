from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from .models import ChatRoom, ChatMessage, ChatCannedReply


def can_manage_support(user):
    if not user.is_authenticated:
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
    if request.user.is_authenticated and can_manage_support(request.user):
        rooms = ChatRoom.objects.all().select_related('user', 'assigned_agent')
    elif request.user.is_authenticated:
        rooms = ChatRoom.objects.filter(user=request.user).select_related('assigned_agent')
    else:
        # Guest user - track by session
        guest_id = get_guest_id(request)
        rooms = ChatRoom.objects.filter(metadata__guest_id=guest_id).select_related('assigned_agent')
    
    # If a guest/user has only one room, redirect directly to it
    if rooms.count() == 1 and not (request.user.is_authenticated and can_manage_support(request.user)):
        return redirect('chat_room', room_id=rooms.first().id)
    elif rooms.count() == 0 and not (request.user.is_authenticated and can_manage_support(request.user)):
        return redirect('create_chat')

    return render(request, 'site/chat_list.html', {'rooms': rooms})


def chat_room(request, room_id):
    """Displays an individual chat room with message history."""
    is_manager = can_manage_support(request.user)
    if is_manager:
        room = get_object_or_404(ChatRoom, id=room_id)
    elif request.user.is_authenticated:
        room = get_object_or_404(ChatRoom, id=room_id, user=request.user)
    else:
        guest_id = get_guest_id(request)
        room = get_object_or_404(ChatRoom, id=room_id, metadata__guest_id=guest_id)
    
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
        'canned_replies': canned_replies
    })


def create_chat(request):
    """Initializes a new support chat room."""
    subject = request.GET.get('subject', 'طلب دعم فني')
    
    if request.user.is_authenticated:
        # Check if there's already an active (not closed) chat for this user
        active_chat = ChatRoom.objects.filter(user=request.user).exclude(status=ChatRoom.Status.CLOSED).first()
        if active_chat:
            return redirect('chat_room', room_id=active_chat.id)
        room = ChatRoom.objects.create(user=request.user, subject=subject)
        user_label = request.user.email
    else:
        # Guest user
        guest_id = get_guest_id(request)
        active_chat = ChatRoom.objects.filter(metadata__guest_id=guest_id).exclude(status=ChatRoom.Status.CLOSED).first()
        if active_chat:
            return redirect('chat_room', room_id=active_chat.id)
            
        # We need a placeholder user for ChatRoom if the model requires it
        # Let's see if we have a designated 'Guest' user or if we can make user nullable
        # For now, I'll assume we might need a system user or if nullable is allowed.
        # Looking at models.py, user is NOT nullable. 
        # I will look for a user named 'guest' or similar, or prompt to create one.
        from apps.accounts.models import User
        system_guest = User.objects.filter(email="guest@raqamiyat.com").first()
        if not system_guest:
             # Fallback to any staff or first user if guest doesn't exist (safety)
             system_guest = User.objects.filter(is_staff=True).first()
        
        room = ChatRoom.objects.create(
            user=system_guest, 
            subject=f"{subject} (زائر)",
            metadata={"guest_id": guest_id, "is_guest": True}
        )
        user_label = f"زائر ({guest_id[:8]})"
    
    from apps.notifications.services import notify_staff
    notify_staff(
        title="طلب دعم جديد",
        body=f"قام {user_label} بفتح تذكرة دعم جديدة: {subject}",
        action_url=f"/support/chats/{room.id}/"
    )

    return redirect('chat_room', room_id=room.id)


def chat_file_upload(request, room_id):
    if request.method == "POST" and request.FILES.get("file"):
        room = get_object_or_404(ChatRoom, id=room_id)
        
        # Permission check
        is_manager = can_manage_support(request.user)
        is_owner = False
        if request.user.is_authenticated and room.user == request.user:
            is_owner = True
        elif not request.user.is_authenticated:
            guest_id = get_guest_id(request)
            if room.metadata.get('guest_id') == guest_id:
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
        
        sender_name = f"{request.user.first_name} {request.user.last_name}" if request.user.is_authenticated else "زائر"
        
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
    """Allows staff to close a chat room."""
    if not can_manage_support(request.user):
        messages.error(request, "غير مصرح لك بإغلاق المحادثات.")
        return redirect('chat_list')
        
    room = get_object_or_404(ChatRoom, id=room_id)
    room.status = ChatRoom.Status.CLOSED
    room.save()
    messages.success(request, f"تم إغلاق المحادثة #{room.id} بنجاح.")
    return redirect('chat_list')
