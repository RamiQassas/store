from django.utils import translation
from django.conf import settings

class UserLanguageMiddleware:
    """
    Middleware that ensures an authenticated user's preferred language 
    is synchronized with the current session.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Safe access to user (avoid AttributeError if Middleware order is wrong or during ASGI startup)
        user = getattr(request, 'user', None)
        
        if user and user.is_authenticated:
            # Sync user's saved preference to session if it's different.
            user_pref = getattr(user, 'preferred_language', None)
            session_lang = request.session.get(translation.LANGUAGE_SESSION_KEY)
            
            if user_pref and user_pref != session_lang:
                request.session[translation.LANGUAGE_SESSION_KEY] = user_pref
                # Activate immediately so current request uses it
                translation.activate(user_pref)
                request.LANGUAGE_CODE = translation.get_language()
                
        response = self.get_response(request)
        return response
