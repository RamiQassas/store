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
        
        target_lang = None
        
        if user and user.is_authenticated:
            target_lang = getattr(user, 'preferred_language', None)
        
        # If no user preference, fallback to session language
        if not target_lang and session:
            target_lang = session.get('_language')

        if target_lang:
            # Sync to session if different
            if session and session.get('_language') != target_lang:
                session['_language'] = target_lang
            
            # If the currently active language (from LocaleMiddleware) 
            # doesn't match the target language, override it.
            current_lang = translation.get_language()
            if current_lang != target_lang:
                translation.activate(target_lang)
                request.LANGUAGE_CODE = translation.get_language()
                
                # For GET requests, redirect to the correctly prefixed URL 
                # to maintain consistency between URL and content.
                if request.method == 'GET' and not request.headers.get('x-requested-with') == 'XMLHttpRequest':
                    full_path = request.get_full_path()
                    new_path = translate_url(full_path, target_lang)
                    if new_path and new_path != full_path:
                        return redirect(new_path)
                
        response = self.get_response(request)
        return response
