from django.views.i18n import set_language
from django.shortcuts import redirect

def custom_set_language(request):
    """
    Overrides the default set_language to also persist the choice 
    to the User model if the user is authenticated.
    """
    # 1. Call the original set_language to handle session/cookie
    response = set_language(request)
    
    # 2. If successful and user is logged in, save preference to DB
    user = getattr(request, 'user', None)
    if user and user.is_authenticated and request.method == 'POST':
        lang_code = request.POST.get('language')
        if lang_code:
            user.preferred_language = lang_code
            user.save(update_fields=['preferred_language'])
            
    return response
