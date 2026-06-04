from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Q
from .models import ChatRoom, ChatMessage, ChatCannedReply


@login_required
def chat_list(request):
    """Lists available chat rooms for the user or staff."""
    if request.user.is_staff:
        rooms = ChatRoom.objects.all().select_related('user', 'assigned_agent')
    else:
        rooms = ChatRoom.objects.filter(user=request.user).select_related('assigned_agent')
    
    return render(request, 'site/chat_list.html', {'rooms': rooms})


@login_required
def chat_room(request, room_id):
    """Displays an individual chat room with message history."""
    if request.user.is_staff:
        room = get_object_or_404(ChatRoom, id=room_id)
    else:
        room = get_object_or_404(ChatRoom, id=room_id, user=request.user)
    
    messages_history = room.messages.all().select_related('sender')
    
    # Reset unread count
    if request.user.is_staff:
        room.unread_staff_count = 0
    else:
        room.unread_user_count = 0
    room.save()
    
    canned_replies = ChatCannedReply.objects.filter(is_active=True) if request.user.is_staff else None
    
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
    return redirect('chat_room', room_id=room.id)


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
