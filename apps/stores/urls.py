from django.urls import path
from apps.stores import views

urlpatterns = [
    # Storefront (Frontend)
    path("", views.store_home, name="store_home"),
    path("catalog/", views.store_catalog, name="store_catalog"),
    path("product/<uuid:pk>/", views.store_product_detail, name="store_product_detail"),
    path("checkout/<uuid:variant_pk>/", views.store_checkout, name="store_checkout"),
    path("order/<uuid:pk>/", views.store_order_detail, name="store_order_detail"),
    
    # Store Customer Account
    path("auth/login/", views.store_login, name="store_login"),
    path("auth/register/", views.store_register, name="store_register"),
    path("auth/logout/", views.store_logout, name="store_logout"),
    
    path("dashboard/", views.store_dashboard, name="store_dashboard"),
    path("dashboard/wallet/", views.store_wallet, name="store_wallet"),
    path("dashboard/wallet/recharge/", views.store_wallet_recharge, name="store_wallet_recharge"),
    
    # Custom Pages
    path("page/<slug:slug>/", views.store_custom_page, name="store_custom_page"),
    
    # ==========================================
    # --- MERCHANT DASHBOARD ---
    # ==========================================
    path("merchant/", views.merchant_dashboard, name="merchant_dashboard"),
    
    # Products & Variants & Keys
    path("merchant/products/", views.merchant_products, name="merchant_products"),
    path("merchant/products/create/", views.merchant_product_form, name="merchant_product_create"),
    path("merchant/products/<uuid:pk>/edit/", views.merchant_product_form, name="merchant_product_edit"),
    path("merchant/products/<uuid:pk>/delete/", views.merchant_product_delete, name="merchant_product_delete"),
    path("merchant/products/<uuid:product_pk>/variants/create/", views.merchant_variant_form, name="merchant_variant_create"),
    path("merchant/variants/<uuid:pk>/edit/", views.merchant_variant_form, name="merchant_variant_edit"),
    path("merchant/variants/<uuid:pk>/keys/", views.merchant_variant_keys, name="merchant_variant_keys"),
    
    # Categories
    path("merchant/categories/", views.merchant_categories, name="merchant_categories"),
    path("merchant/categories/create/", views.merchant_category_form, name="merchant_category_create"),
    path("merchant/categories/<uuid:pk>/edit/", views.merchant_category_form, name="merchant_category_edit"),
    path("merchant/categories/<uuid:pk>/delete/", views.merchant_category_delete, name="merchant_category_delete"),
    
    # Orders
    path("merchant/orders/", views.merchant_orders, name="merchant_orders"),
    path("merchant/orders/<uuid:pk>/", views.merchant_order_detail, name="merchant_order_detail"),
    path("merchant/orders/<uuid:pk>/update-status/", views.merchant_order_status_update, name="merchant_order_status_update"),
    
    # Coupons
    path("merchant/coupons/", views.merchant_coupons, name="merchant_coupons"),
    path("merchant/coupons/create/", views.merchant_coupon_form, name="merchant_coupon_create"),
    path("merchant/coupons/<uuid:pk>/edit/", views.merchant_coupon_form, name="merchant_coupon_edit"),
    path("merchant/coupons/<uuid:pk>/delete/", views.merchant_coupon_delete, name="merchant_coupon_delete"),
    
    # Staff / Employees
    path("merchant/employees/", views.merchant_employees, name="merchant_employees"),
    path("merchant/employees/create/", views.merchant_employee_form, name="merchant_employee_create"),
    path("merchant/employees/<uuid:pk>/edit/", views.merchant_employee_form, name="merchant_employee_edit"),
    path("merchant/employees/<uuid:pk>/delete/", views.merchant_employee_delete, name="merchant_employee_delete"),
    
    # Pages CRUD
    path("merchant/pages/", views.merchant_pages, name="merchant_pages"),
    path("merchant/pages/create/", views.merchant_page_form, name="merchant_page_create"),
    path("merchant/pages/<uuid:pk>/edit/", views.merchant_page_form, name="merchant_page_edit"),
    path("merchant/pages/<uuid:pk>/delete/", views.merchant_page_delete, name="merchant_page_delete"),
    
    # Settings & Colors
    path("merchant/settings/", views.merchant_settings, name="merchant_settings"),
    path("merchant/subscription/", views.merchant_subscription, name="merchant_subscription"),
]
