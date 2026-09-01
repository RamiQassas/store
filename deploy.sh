#!/bin/bash
# ==============================================================================
# Deploy Script for Hetzner Cloud VPS
# ==============================================================================

set -e

echo "🚀 بدء عملية النشر التلقائي على Hetzner..."

# 1. التحري عن ملف البيئة .env
if [ ! -f .env ]; then
    echo "⚠️ لم يتم العثور على ملف .env، يتم إنشاء ملف جديد من .env.example..."
    if [ -f .env.example ]; then
        cp .env.example .env
    else
        touch .env
    fi
    echo "❗ يرجى مراجعة ملف .env وتعديل بيانات السرية وقواعد البيانات قبل المتابعة."
fi

# 2. إنشاء المجلدات المطلوبة
mkdir -p nginx certbot/conf certbot/www

# 3. بناء وتشغيل الحاويات باستخدام Docker Compose
echo "📦 بناء وتشغيل حاويات Docker..."
docker compose -f docker-compose.prod.yml up -d --build

# 4. تنظيف الصور القديمة والمهملة
echo "🧹 تنظيف مخلفات Docker القديمة..."
docker image prune -f

echo "✅ تم تشغيل جميع الخدمات بنجاح!"
echo "--------------------------------------------------------"
echo "🔒 تفعيل شهادة SSL لـ raqamiyatapp.com..."
docker run --rm \
  -v $(pwd)/certbot/conf:/etc/letsencrypt \
  -v $(pwd)/certbot/www:/var/www/certbot \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d raqamiyatapp.com -d www.raqamiyatapp.com \
  --register-unsafely-without-email --non-interactive --agree-tos || true
echo "--------------------------------------------------------"

