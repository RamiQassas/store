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
    if request.user.is_authenticated and request.method == 'POST':
        lang_code = request.POST.get('language')
        if lang_code:
            # We don't need to validate choices here because User model 
            # and Django's set_language already handle it.
            request.user.preferred_language = lang_code
            request.user.save(update_fields=['preferred_language'])
            
    return response
