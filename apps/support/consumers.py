import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.utils import timezone
from apps.support.models import ChatRoom, ChatMessage
from django.contrib.auth import get_user_model

User = get_user_model()

class SupportConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.user = self.scope["user"]
        self.room_id = self.scope["url_route"]["kwargs"]["room_id"]
        self.room_group_name = f"chat_{self.room_id}"
        self.session = self.scope.get("session")

        print(f"WS Connect Attempt: User={self.user}, Room={self.room_id}")

        # Verify access for both authenticated and guest users
        try:
            has_access = await self.can_access_room()
            if not has_access:
                print(f"WS Reject: Access Denied for Room {self.room_id}")
                await self.close()
                return
        except Exception as e:
            print(f"WS Error during access check: {str(e)}")
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f"WS Accepted: Room {self.room_id}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("type")

        if action == "chat_message":
            message = data.get("message", "")
            file_id = data.get("file_id")
            
            saved_msg = await self.save_message(message, file_id)
            
            # Determine sender details
            if self.user.is_authenticated:
                sender_email = self.user.email
                sender_name = f"{self.user.first_name} {self.user.last_name}"
            else:
                sender_email = "guest@raqamiyat.com"
                sender_name = await self.get_guest_name()

            broadcast_data = {
                "type": "chat.message",
                "message": message,
                "sender_email": sender_email,
                "sender_name": sender_name,
                "is_staff_reply": is_staff,
                "timestamp": saved_msg["timestamp"],
            }
            
            if saved_msg.get("file_url"):
                broadcast_data.update({
                    "file_url": saved_msg["file_url"],
                    "is_image": saved_msg["is_image"],
                    "file_name": saved_msg["file_name"]
                })

            await self.channel_layer.group_send(self.room_group_name, broadcast_data)
        
        elif action == "typing":
            sender_name = self.user.first_name if self.user.is_authenticated else "زائر"
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.typing",
                    "sender_name": sender_name,
                    "is_typing": data.get("is_typing", False)
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def can_access_room(self):
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            if self.user.is_authenticated:
                if room.user == self.user:
                    return True
                # Staff / Support Agent check
                if self.user.is_staff or self.user.is_superuser:
                    return True
                return self.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()
            else:
                # Guest Check via Session
                session_room_id = self.session.get('support_chat_room_id')
                return str(session_room_id) == str(self.room_id)
        except ChatRoom.DoesNotExist:
            return False

    @database_sync_to_async
    def get_guest_name(self):
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            if "زائر:" in room.subject:
                return room.subject.split("زائر: ")[1]
            return "زائر"
        except:
            return "زائر"

    @database_sync_to_async
    def save_message(self, text, file_id=None):
        room = ChatRoom.objects.get(id=self.room_id)
        
        is_staff = False
        if self.user.is_authenticated:
            is_staff = self.user.is_staff or self.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()
        
        # Determine sender user instance (guest uses system guest user)
        sender = self.user if self.user.is_authenticated else room.user

        # If we have a file_id (from an AJAX upload), we update that message rather than creating a new one
        if file_id:
            try:
                msg = ChatMessage.objects.get(id=file_id, room=room)
                if text: msg.text = text
                msg.save()
            except ChatMessage.DoesNotExist:
                msg = ChatMessage.objects.create(room=room, sender=sender, text=text, is_staff_reply=is_staff)
        else:
            msg = ChatMessage.objects.create(room=room, sender=sender, text=text, is_staff_reply=is_staff)
        
        room.last_message_at = timezone.now()
        
        if is_staff:
            room.unread_user_count += 1
            if room.status == ChatRoom.Status.WAITING:
                room.status = ChatRoom.Status.IN_PROGRESS
        else:
            room.unread_staff_count += 1
            if room.status == ChatRoom.Status.CLOSED:
                room.status = ChatRoom.Status.REOPENED
            elif room.status in [ChatRoom.Status.ASSIGNED, ChatRoom.Status.IN_PROGRESS]:
                room.status = ChatRoom.Status.WAITING

        room.save()
        
        # Real-time Web Push Trigger (only for authenticated users)
        if is_staff and room.user.is_authenticated:
            try:
                from apps.notifications.services import notify_user
                notify_user(
                    user=room.user,
                    title="رد جديد من الدعم الفني",
                    body=text[:100] if text else "قام الموظف بإرسال ملف/صورة",
                    action_url=f"/support/chats/{room.id}/",
                    category="support",
                    priority="high",
                    metadata={"type": "chat_reply", "room_id": str(room.id)}
                )
            except: pass
        
        res = {"timestamp": msg.created_at.strftime("%H:%M")}
        if msg.file:
            res.update({
                "file_url": msg.file.url,
                "is_image": msg.is_image,
                "file_name": msg.file.name.split('/')[-1]
            })
        return res
