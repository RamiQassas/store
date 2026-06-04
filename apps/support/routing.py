from django.urls import re_path
from apps.support import consumers

websocket_urlpatterns = [
    re_path(r"^ws/support/chat/(?P<room_id>[^/]+)/$", consumers.SupportConsumer.as_asgi()),
]
