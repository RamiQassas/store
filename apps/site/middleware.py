from django.utils import translation
from django.conf import settings
from django.shortcuts import redirect
from django.urls import translate_url

class UserLanguageMiddleware:
    """
    Middleware that ensures an authenticated user's preferred language 
    is synchronized with the current session and enforced globally.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # 1. Safe access to user and session
        user = getattr(request, 'user', None)
        session = getattr(request, 'session', None)
        
        if user and user.is_authenticated and session is not None:
            user_pref = getattr(user, 'preferred_language', None)
            
            if user_pref:
                # Sync user's saved preference to session if it's different.
                session_lang = session.get('_language')
                if user_pref != session_lang:
                    session['_language'] = user_pref
                
                # If the currently active language (from LocaleMiddleware) 
                # doesn't match the user preference, override it.
                current_lang = translation.get_language()
                if current_lang != user_pref:
                    translation.activate(user_pref)
                    request.LANGUAGE_CODE = translation.get_language()
                    
                    # For GET requests, redirect to the correctly prefixed URL 
                    # to maintain consistency between URL and content.
                    if request.method == 'GET' and not request.headers.get('x-requested-with') == 'XMLHttpRequest':
                        full_path = request.get_full_path()
                        new_path = translate_url(full_path, user_pref)
                        if new_path and new_path != full_path:
                            return redirect(new_path)
                
        response = self.get_response(request)
        return response
