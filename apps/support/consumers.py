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

        print(f"WS Connect Attempt: User={self.user}, Room={self.room_id}")

        if not self.user.is_authenticated:
            print("WS Reject: User not authenticated")
            await self.close()
            return

        # Verify access
        try:
            if not await self.can_access_room():
                print(f"WS Reject: User {self.user.email} has no access to room {self.room_id}")
                await self.close()
                return
        except Exception as e:
            print(f"WS Error during access check: {str(e)}")
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f"WS Accepted: Room {self.room_id} for {self.user.email}")

    async def disconnect(self, close_code):
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        action = data.get("type")

        if action == "chat_message":
            message = data.get("message")
            if message:
                saved_msg = await self.save_message(message)
                await self.channel_layer.group_send(
                    self.room_group_name,
                    {
                        "type": "chat.message",
                        "message": message,
                        "sender_email": self.user.email,
                        "sender_name": f"{self.user.first_name} {self.user.last_name}",
                        "is_staff": self.user.is_staff,
                        "timestamp": saved_msg["timestamp"],
                    }
                )
        
        elif action == "typing":
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.typing",
                    "sender_name": self.user.first_name,
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
            if room.user == self.user:
                return True
            # Staff / Support Agent check
            if self.user.is_staff or self.user.is_superuser:
                return True
            return self.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()
        except ChatRoom.DoesNotExist:
            return False

    @database_sync_to_async
    def save_message(self, text):
        room = ChatRoom.objects.get(id=self.room_id)
        is_staff = self.user.is_staff or self.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()
        
        msg = ChatMessage.objects.create(
            room=room,
            sender=self.user,
            text=text,
            is_staff_reply=is_staff
        )
        
        room.last_message_at = timezone.now()
        
        if is_staff:
            room.unread_user_count += 1
            if room.status == ChatRoom.Status.WAITING:
                room.status = ChatRoom.Status.IN_PROGRESS
        else:
            room.unread_staff_count += 1
            # If user sends message, mark as waiting (action required)
            if room.status == ChatRoom.Status.CLOSED:
                room.status = ChatRoom.Status.REOPENED
            elif room.status in [ChatRoom.Status.ASSIGNED, ChatRoom.Status.IN_PROGRESS]:
                room.status = ChatRoom.Status.WAITING
            elif room.status == ChatRoom.Status.WAITING:
                pass # Already waiting

        room.save()
        return {"timestamp": msg.created_at.strftime("%H:%M")}
