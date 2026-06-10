from django.views.i18n import set_language

def custom_set_language(request):
    """
    Overrides the default set_language to also persist the choice 
    to the User model if the user is authenticated.
    """
    # 1. If it's a POST, update the user preference in the DB first.
    if request.method == 'POST':
        lang_code = request.POST.get('language')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and lang_code:
            # We don't use _() here because lang_code is a code, 
            # and we just want to save it.
            user.preferred_language = lang_code
            user.save(update_fields=['preferred_language'])
            
    # 2. Call the original set_language to handle session/cookie and redirection.
    # Django's set_language is robust and handles i18n_patterns (prefixes) 
    # if the 'next' parameter is provided correctly.
    return set_language(request)
