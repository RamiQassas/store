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

        # Get host from headers to resolve store context
        host = ""
        for name, value in self.scope.get("headers", []):
            if name == b"host":
                host = value.decode("utf-8").split(":")[0].lower()
                break

        self.store = await self.resolve_store_from_host(host)
        print(f"WS Connect Attempt: User={self.user}, Room={self.room_id}, Resolved Store={self.store}")

        # Verify access for both authenticated and guest users
        try:
            print(f"WS Checking access for Room {self.room_id}...")
            has_access = await self.can_access_room()
            if not has_access:
                print(f"WS Reject: Access Denied for Room {self.room_id} (User: {self.user})")
                await self.close(code=4003)
                return
        except Exception as e:
            print(f"WS Error during access check: {str(e)}")
            import traceback
            traceback.print_exc()
            await self.close(code=4000)
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()
        print(f"WS Accepted: Room {self.room_id} by User {self.user}")

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
            
            broadcast_data = {
                "type": "chat.message",
                "message": message,
                "sender_email": saved_msg["sender_email"],
                "sender_name": saved_msg["sender_name"],
                "is_staff_reply": saved_msg["is_staff_reply"],
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
            # Better sender name detection for typing
            room_data = await self.get_room_data()
            if self.user.is_authenticated:
                is_staff = await self.is_staff_user_async()
                if is_staff:
                    sender_name = "الدعم الفني"
                    sender_email = "support@raqamiyat.com"
                else:
                    sender_name = f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email
                    sender_email = self.user.email
            else:
                sender_name = room_data.get('guest_name') or f"Visitor #{self.room_id[:8]}"
                sender_email = f"guest_{self.room_id}@raqamiyat.com"

            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "chat.typing",
                    "sender_name": sender_name,
                    "sender_email": sender_email,
                    "is_typing": data.get("is_typing", False)
                }
            )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps(event))

    async def chat_typing(self, event):
        await self.send(text_data=json.dumps(event))

    @database_sync_to_async
    def get_room_data(self):
        from apps.common.tenant_utils import set_current_store
        set_current_store(getattr(self, 'store', None))
        try:
            room = ChatRoom.objects.get(id=self.room_id)
            return {
                'guest_name': room.guest_name,
                'user_email': room.user.email,
                'is_guest_room': room.is_guest_room,
                'display_name': room.display_name
            }
        except:
            return {}

    @database_sync_to_async
    def can_access_room(self):
        from apps.common.tenant_utils import set_current_store
        set_current_store(getattr(self, 'store', None))
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
    def is_staff_user_async(self):
        if not self.user or not self.user.is_authenticated:
            return False
        return self.user.is_staff or self.user.is_superuser or self.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()

    @database_sync_to_async
    def get_room_owner(self, room):
        return room.user


    @database_sync_to_async
    def save_message(self, text, file_id=None):
        from apps.common.tenant_utils import set_current_store
        set_current_store(getattr(self, 'store', None))
        room = ChatRoom.objects.get(id=self.room_id)
        
        is_staff_user = False
        if self.user.is_authenticated:
            # Check if user has staff/admin role
            is_staff_user = self.user.is_staff or self.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()
        
        # Determine sender user instance (guest uses room's assigned user)
        sender = self.user if self.user.is_authenticated else room.user

        if file_id:
            try:
                msg = ChatMessage.objects.get(id=file_id, room=room)
                if text: msg.text = text
                msg.save()
            except ChatMessage.DoesNotExist:
                msg = ChatMessage.objects.create(room=room, sender=sender, text=text, is_staff_reply=is_staff_user)
        else:
            msg = ChatMessage.objects.create(room=room, sender=sender, text=text, is_staff_reply=is_staff_user)
        
        room.last_message_at = timezone.now()
        
        if is_staff_user:
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

        # Determine names for broadcast and notifications
        if self.user.is_authenticated:
            if is_staff_user:
                actual_sender_name = "الدعم الفني"
                actual_sender_email = "support@raqamiyat.com"
            else:
                actual_sender_name = f"{self.user.first_name} {self.user.last_name}".strip() or self.user.email
                actual_sender_email = self.user.email
        else:
            actual_sender_name = room.display_name
            actual_sender_email = f"guest_{self.room_id}@raqamiyat.com"
        
        # Real-time Notification Trigger
        from apps.notifications.services import notify_user, notify_staff
        
        if is_staff_user:
            # Manager is replying -> Notify the client
            # But only if the client is NOT also a staff member (prevents admin-to-admin chat double notifications)
            is_client_staff = room.user.is_staff or room.user.groups.filter(name__in=["Support Agent", "Super Admin", "Moderator"]).exists()
            
            if not is_client_staff:
                try:
                    notify_user(
                        user=room.user,
                        title="رد جديد من الدعم الفني",
                        body=text[:100] if text else "قام الموظف بإرسال ملف/صورة",
                        action_url=f"/support/chats/{room.id}/",
                        category="support",
                        priority="high",
                        metadata={"type": "chat_reply", "room_id": str(room.id)},
                        exclude_user=self.user # Don't notify the sender
                    )
                except: pass
        else:
            # Client/Guest is sending -> Notify ALL staff except the sender
            # We only exclude the sender if they are authenticated and actually a staff member
            exclude_u = None
            if self.user.is_authenticated and (self.user.is_staff or self.user.is_superuser):
                exclude_u = self.user

            try:
                notify_staff(
                    title=f"رسالة جديدة من {actual_sender_name}",
                    body=text[:100] if text else "قام العميل بإرسال ملف/صورة",
                    action_url=f"/support/chats/{room.id}/",
                    category='admin_new_support',
                    priority="high",
                    metadata={"type": "chat_user_msg", "room_id": str(room.id)},
                    exclude_user=exclude_u
                )
            except: pass
        
        res = {
            "timestamp": msg.created_at.strftime("%H:%M"),
            "is_staff_reply": is_staff_user,
            "sender_name": actual_sender_name,
            "sender_email": actual_sender_email
        }
        if msg.file:
            res.update({
                "file_url": msg.file.url,
                "is_image": msg.is_image,
                "file_name": msg.file.name.split('/')[-1]
            })
        return res

    @database_sync_to_async
    def resolve_store_from_host(self, host):
        from django.conf import settings
        from urllib.parse import urlparse
        from apps.stores.models import Store
        from apps.common.tenant_utils import bypass_tenant_filter
        
        if not host:
            return None
            
        site_url = getattr(settings, "SITE_URL", "https://raqamiyatapp.com")
        main_domain = urlparse(site_url).hostname or "raqamiyatapp.com"
        main_domain = main_domain.lower()
        if main_domain.startswith("www."):
            main_domain = main_domain[4:]

        main_domains = [main_domain]
        if "onrender.com" in host:
            parts = host.split('.')
            if len(parts) >= 3:
                main_domains.append(".".join(parts[-3:]))
            else:
                main_domains.append(host)

        is_subdomain = False
        subdomain = ""
        for m_domain in main_domains:
            cleaned_m_domain = m_domain[4:] if m_domain.startswith("www.") else m_domain
            if host.endswith("." + cleaned_m_domain) and host != cleaned_m_domain:
                subdomain = host[:-(len(cleaned_m_domain) + 1)]
                is_subdomain = True
                if subdomain == "www":
                    is_subdomain = False
                break

        if not is_subdomain and main_domain in ["localhost", "127.0.0.1", "testserver"]:
            parts = host.split('.')
            if len(parts) > 1 and parts[-1] in ["localhost", "127", "testserver"]:
                subdomain = parts[0]
                is_subdomain = True

        if is_subdomain:
            try:
                with bypass_tenant_filter():
                    return Store.objects.get(subdomain__iexact=subdomain)
            except Store.DoesNotExist:
                return None
        else:
            is_main_domain_or_local = (host in main_domains) or (host in ["localhost", "127.0.0.1", "testserver"]) or any(host.endswith("." + d) for d in main_domains)
            if not is_main_domain_or_local:
                try:
                    with bypass_tenant_filter():
                        return Store.objects.filter(custom_domain=host).first()
                except:
                    return None
        return None
