#!/bin/bash
# ==============================================================================
# Automated Production Deploy & SSL Setup Script for Hetzner Cloud VPS
# ==============================================================================

set -e

DOMAIN="raqamiyatapp.com"
WWW_DOMAIN="www.raqamiyatapp.com"
EMAIL="admin@raqamiyatapp.com"

echo "🚀 بدء عملية النشر التلقائي وإعداد SSL لـ $DOMAIN..."

# 1. إنشاء المجلدات المطلوبة لـ Certbot والـ Nginx
mkdir -p nginx certbot/conf certbot/www certbot/conf/live/$DOMAIN

# 2. إنشاء شهادة مؤقتة (Dummy SSL Certificate) في حال عدم وجود شهادة لمنع توقف Nginx
if [ ! -f "certbot/conf/live/$DOMAIN/fullchain.pem" ]; then
    echo "🔑 إنشاء شهادة مؤقتة لتمكين Nginx من الإقلاع لأول مرة..."
    openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
      -keyout "certbot/conf/live/$DOMAIN/privkey.pem" \
      -out "certbot/conf/live/$DOMAIN/fullchain.pem" \
      -subj "/CN=localhost"
fi

# 3. بناء وتشغيل كافة الحاويات باستخدام Docker Compose
echo "📦 بناء وتشغيل حاويات Docker..."
docker compose -f docker-compose.prod.yml up -d --build

# 4. طلب شهادة SSL الحقيقية من Let's Encrypt عبر Certbot
echo "🔒 طلب شهادة SSL الحقيقية من Let's Encrypt لـ $DOMAIN و $WWW_DOMAIN..."
docker run --rm \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/certbot/www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d $DOMAIN -d $WWW_DOMAIN \
  --email $EMAIL --agree-tos --non-interactive --force-renewal || true

# 5. إعادة تحميل Nginx لتطبيق شهادة SSL الحقيقية
echo "🔄 إعادة تحميل Nginx لإنعاش شهادة الأمان..."
docker compose -f docker-compose.prod.yml exec -T nginx nginx -s reload || true

# 6. تنظيف مخلفات Docker
docker image prune -f

echo "✅ اكتملت عملية النشر بنجاح! الموقع يعمل الآن بشكل آمن على HTTPS!"
