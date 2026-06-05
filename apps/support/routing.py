from django.urls import re_path
from apps.support import consumers

websocket_urlpatterns = [
    re_path(r"(?i)ws/support/chat/(?P<room_id>[0-9a-f-]+)/$", consumers.SupportConsumer.as_asgi()),
]
