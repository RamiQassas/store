#!/bin/bash
set -e

cat << 'EOF' > .env
DJANGO_SECRET_KEY=django-insecure-prod-hetzner-key-9823419823
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=raqamiyatapp.com,www.raqamiyatapp.com,2.29.26.113,localhost,127.0.0.1
DJANGO_CSRF_TRUSTED_ORIGINS=https://raqamiyatapp.com,https://www.raqamiyatapp.com,http://2.29.26.113,http://2.29.26.113:8000

POSTGRES_DB=store
POSTGRES_USER=store
POSTGRES_PASSWORD=store_secure_password_2026
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

REDIS_URL=redis://redis:6379/0
DJANGO_USE_REDIS_CACHE=True

GOOGLE_CLIENT_ID=723304203570-dgh580lvgds8oe40rhkjholrpfmf6cfe.apps.googleusercontent.com
GOOGLE_CLIENT_SECRET=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

BREVO_API_KEY=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
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=ad3ef4001@smtp-brevo.com
EMAIL_HOST_PASSWORD=xsmtpsib-4ee5dd71322192c6110f1f55a8d0093b02fc55853d5eabfb95511c401d55f5b1-0k0hKdBdfb8b75FB
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
DEFAULT_FROM_EMAIL=noreply@raqamiyatapp.com
REPLY_TO_EMAIL=support@raqamiyatapp.com

SITE_NAME=Raqamiyat
SITE_URL=https://raqamiyatapp.com
VAPID_ADMIN_EMAIL=noreply@raqamiyatapp.com
VAPID_PUBLIC_KEY=BEA2XAFFTAyCDeE-ax8Q0T_RejV1Noo432TqQDSFjmNflOuSYnczsKPZTGGlsBjls_z0374FM0yBugmxhpYbrwE
VAPID_PRIVATE_KEY=W3P1k2Yo2STn90wwDPqkEcrE8ucxqP16nZ3tVAol1Lw
EOF

docker compose -f docker-compose.prod.yml up -d --build
docker cp backup_data.json $(docker compose -f docker-compose.prod.yml ps -q web):/app/backup_data.json
docker compose -f docker-compose.prod.yml exec web python manage.py loaddata backup_data.json
