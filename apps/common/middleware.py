from django.http import HttpResponsePermanentRedirect

class DomainRedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()
        # The primary domain we want to enforce
        primary_domain = 'raqamiyatapp.com'
        
        # If the request comes from the old onrender domain, redirect to the new one
        if 'raqamiyat.onrender.com' in host:
            new_url = f"https://{primary_domain}{request.get_full_path()}"
            return HttpResponsePermanentRedirect(new_url)
            
        # Also handle the 'www' if we want to force non-www or vice-versa
        # The user specified 'https://raqamiyatapp.com/' so we enforce non-www or just the domain
        
        return self.get_response(request)
