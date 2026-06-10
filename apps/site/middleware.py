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
        if request.user.is_authenticated:
            # Sync user's saved preference to session if it's different.
            # This handles the case where a user logs in from a new device.
            user_pref = getattr(request.user, 'preferred_language', None)
            session_lang = request.session.get(translation.LANGUAGE_SESSION_KEY)
            
            if user_pref and user_pref != session_lang:
                request.session[translation.LANGUAGE_SESSION_KEY] = user_pref
                # Optional: Activate immediately so current request uses it
                translation.activate(user_pref)
                request.LANGUAGE_CODE = translation.get_language()
                
        response = self.get_response(request)
        return response
