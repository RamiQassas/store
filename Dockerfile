# Dockerfile لإنتاج تطبيق Django + Daphne ASGI + Celery
FROM python:3.11-slim

# ضبط متغيرات البيئة لمنع ملفات pyc والطباعة المباشرة في الـ logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# تثبيت المتطلبات الأساسية للنظام
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# تثبيت مكتبات بايثون
COPY requirements.txt /app/
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# نسخ كود المشروع
COPY . /app/

# إنشاء مجلدات الملفات الثابتة والوسائط
RUN mkdir -p /app/staticfiles /app/media

# كشف المنفذ 8000
EXPOSE 8000

# الأمر الافتراضي لتشغيل خادم Daphne ASGI (HTTP + WebSockets)
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
