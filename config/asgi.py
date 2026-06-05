import os
from django.core.asgi import get_asgi_application

# 1. Initialize Django settings FIRST
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

# 2. Get the ASGI application (Establish environment)
django_asgi_app = get_asgi_application()

# 3. Import routing ONLY AFTER Django is setup to avoid ImproperlyConfigured
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from channels.security.websocket import AllowedHostsOriginValidator
import apps.support.routing

# 4. Build the final application
application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AllowedHostsOriginValidator(
        AuthMiddlewareStack(
            URLRouter(
                apps.support.routing.websocket_urlpatterns
            )
        )
    ),
})
