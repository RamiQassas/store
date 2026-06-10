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
        # 1. Safe access to user and session
        user = getattr(request, 'user', None)
        session = getattr(request, 'session', None)
        
        if user and user.is_authenticated and session is not None:
            # Sync user's saved preference to session if it's different.
            user_pref = getattr(user, 'preferred_language', None)
            # '_language' is the standard Django session key for language
            session_lang = session.get('_language')
            
            if user_pref and user_pref != session_lang:
                session['_language'] = user_pref
                # Activate immediately so current request uses it
                translation.activate(user_pref)
                request.LANGUAGE_CODE = translation.get_language()
                
        response = self.get_response(request)
        return response
