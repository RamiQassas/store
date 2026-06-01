# Digital Services Marketplace - Django Backend

مشروع Django احترافي كأساس لمنصة عربية لبيع المنتجات الرقمية والخدمات الإلكترونية.

## المكونات

- Django 5 + Django Rest Framework
- JWT + Session Authentication
- PostgreSQL-ready مع SQLite كخيار تطوير سريع
- Redis cache + Celery-ready
- أثناء التطوير يعمل الـ cache محليًا بدون Redis، ويمكن تفعيل Redis عبر `DJANGO_USE_REDIS_CACHE=True`
- تطبيقات مستقلة للحسابات، المحافظ، الدفع، المنتجات، الطلبات، الإشعارات، الدعم، والخدمات
- لوحة إدارة Django لإدارة المستخدمين، المنتجات، الإيداعات، الطلبات، الكوبونات، والخدمات
- RTL/Arabic-ready من ناحية اللغة والمنطقة الزمنية
- صفحات واجهة فعلية للمستخدم والموظف:
  - `/` الصفحة الرئيسية
  - `/catalog/` الكتالوج
  - `/catalog/<slug>/` صفحة المنتج
  - `/auth/login/` و `/auth/register/`
  - `/dashboard/` و `/dashboard/deposits/` و `/dashboard/tickets/`
  - `/control/` لوحة الإدارة الداخلية

## التشغيل المحلي

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
py manage.py migrate
py manage.py createsuperuser
py manage.py seed_demo
py manage.py runserver
```

افتح:

- API health: `http://127.0.0.1:8000/api/health/`
- Admin: `http://127.0.0.1:8000/admin/`

## أهم الـ API endpoints

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/token/refresh/`
- `GET /api/products/`
- `GET /api/categories/`
- `GET /api/wallets/`
- `POST /api/deposits/`
- `POST /api/deposits/{id}/approve/` للموظفين
- `POST /api/orders/`
- `POST /api/orders/{id}/set_status/` للموظفين
- `GET /api/tickets/`
- `POST /api/tickets/{id}/reply/`

## مثال إنشاء طلب

```json
{
  "variant_id": "UUID_OF_PRODUCT_VARIANT",
  "quantity": 1,
  "fulfillment_data": {
    "player_id": "123456789",
    "region": "middle_east"
  },
  "coupon_code": ""
}
```

## ملاحظات إنتاج

- غيّر `DJANGO_SECRET_KEY` وضع `DJANGO_DEBUG=False`.
- استخدم PostgreSQL و Redis حقيقيين.
- اربط SMTP فعلي لتفعيل البريد.
- استبدل `ShamCashPlaceholderGateway` بعميل API الحقيقي عند توفر بيانات البنك.
- ضع التخزين خلف S3-compatible storage أو CDN عند رفع المشروع للإنتاج.
