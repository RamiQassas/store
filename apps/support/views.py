from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from django.utils import timezone
from django.http import JsonResponse
from .models import ChatRoom, ChatMessage, ChatCannedReply


def can_manage_support(user):
    if user.is_staff or user.is_superuser:
        return True
    return user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()


@login_required
def chat_list(request):
    """Lists available chat rooms for the user or staff."""
    if can_manage_support(request.user):
        rooms = ChatRoom.objects.all().select_related('user', 'assigned_agent')
    else:
        rooms = ChatRoom.objects.filter(user=request.user).select_related('assigned_agent')
    
    return render(request, 'site/chat_list.html', {'rooms': rooms})


@login_required
def chat_room(request, room_id):
    """Displays an individual chat room with message history."""
    is_manager = can_manage_support(request.user)
    if is_manager:
        room = get_object_or_404(ChatRoom, id=room_id)
    else:
        room = get_object_or_404(ChatRoom, id=room_id, user=request.user)
    
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


@login_required
def create_chat(request):
    """Initializes a new support chat room."""
    # Check if there's already an active (not closed) chat for this user
    active_chat = ChatRoom.objects.filter(user=request.user).exclude(status=ChatRoom.Status.CLOSED).first()
    if active_chat:
        return redirect('chat_room', room_id=active_chat.id)
        
    subject = request.GET.get('subject', 'طلب دعم فني')
    room = ChatRoom.objects.create(user=request.user, subject=subject)
    
    from apps.notifications.services import notify_staff
    notify_staff(
        title="طلب دعم جديد",
        body=f"قام {request.user.email} بفتح تذكرة دعم جديدة: {subject}",
        action_url=f"/support/chats/{room.id}/"
    )

    return redirect('chat_room', room_id=room.id)


from django.http import JsonResponse

@login_required
def chat_file_upload(request, room_id):
    if request.method == "POST" and request.FILES.get("file"):
        room = get_object_or_404(ChatRoom, id=room_id)
        if not (request.user.is_staff or room.user == request.user):
            return JsonResponse({"status": "error", "message": "Permission denied"}, status=403)
            
        file = request.FILES.get("file")
        is_image = file.content_type.startswith("image/")
        
        message = ChatMessage.objects.create(
            room=room,
            sender=request.user,
            file=file,
            is_image=is_image,
            is_staff_reply=can_manage_support(request.user)
        )
        
        # Trigger room updates
        room.last_message_at = timezone.now()
        if message.is_staff_reply:
            room.unread_user_count += 1
        else:
            room.unread_staff_count += 1
        room.save()
        
        return JsonResponse({
            "status": "success",
            "message_id": str(message.id),
            "file_id": str(message.id),
            "file_url": message.file.url,
            "is_image": is_image,
            "timestamp": message.created_at.strftime("%H:%M"),
            "sender_name": f"{request.user.first_name} {request.user.last_name}"
        })
@login_required
def close_chat(request, room_id):
    """Allows staff to close a chat room."""
    if not request.user.is_staff:
        messages.error(request, "غير مصرح لك بإغلاق المحادثات.")
        return redirect('chat_list')
        
    room = get_object_or_404(ChatRoom, id=room_id)
    room.status = ChatRoom.Status.CLOSED
    room.save()
    messages.success(request, f"تم إغلاق المحادثة #{room.id} بنجاح.")
    return redirect('chat_list')
