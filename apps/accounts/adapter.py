from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from apps.accounts.models import User

class MySocialAccountAdapter(DefaultSocialAccountAdapter):
    def pre_social_login(self, request, sociallogin):
        """
        Connect existing accounts by email.
        """
        # sociallogin.user.email is the email from Google
        email = sociallogin.user.email
        if not email:
            return

        try:
            user = User.objects.get(email__iexact=email)
            sociallogin.connect(request, user)
        except User.DoesNotExist:
            pass
