from django.urls import path
from apps.stores import views
from apps.site import views as site_views
from apps.support import views as support_views

urlpatterns = [
    # Storefront (Frontend)
    path("", views.store_home, name="store_home"),
    path("", views.store_home, name="home"), # Alias
    path("catalog/", views.store_catalog, name="store_catalog"),
    path("catalog/", views.store_catalog, name="catalog"), # Alias
    path("product/<uuid:pk>/", views.store_product_detail, name="store_product_detail"),
    path("product/<uuid:pk>/", views.store_product_detail, name="product_detail"), # Alias
    path("checkout/<uuid:variant_pk>/", views.store_checkout, name="store_checkout"),
    path("order/<uuid:pk>/", views.store_order_detail, name="store_order_detail"),
    
    # Store Customer Account
    path("auth/login/", views.store_login, name="store_login"),
    path("auth/login/", views.store_login, name="site_login"), # Alias
    path("auth/register/", views.store_register, name="store_register"),
    path("auth/register/", views.store_register, name="site_register"), # Alias
    path("auth/logout/", views.store_logout, name="store_logout"),
    path("auth/logout/", views.store_logout, name="site_logout"), # Alias
    
    path("dashboard/", views.store_dashboard, name="store_dashboard"),
    path("dashboard/", views.store_dashboard, name="dashboard"), # Alias
    path("dashboard/wallet/", views.store_wallet, name="store_wallet"),
    path("dashboard/wallet/", views.store_wallet, name="dashboard_wallet"), # Alias
    path("dashboard/wallet/recharge/", views.store_wallet_recharge, name="store_wallet_recharge"),
    path("dashboard/wallet/recharge/", views.store_wallet_recharge, name="dashboard_recharge_wallet"), # Alias
    
    # Shared Platform Customer Features
    path("dashboard/orders/", site_views.orders_list, name="dashboard_orders"),
    path("dashboard/orders/<uuid:pk>/", site_views.order_detail, name="dashboard_order_detail"),
    path("dashboard/deposits/", site_views.deposits, name="dashboard_deposits"),
    path("dashboard/withdrawals/", site_views.withdrawals, name="dashboard_withdrawals"),
    path("dashboard/transfer/", site_views.transfer_page, name="dashboard_transfer"),
    path("dashboard/transfer/history/", site_views.transfer_history, name="dashboard_transfer_history"),
    path("dashboard/notifications/", site_views.notifications_list, name="notifications_list"),
    path("dashboard/notifications/settings/", site_views.notification_settings, name="notification_settings"),
    path("dashboard/change-password/", site_views.v3_change_password_view, name="change_password"),
    path("dashboard/change-email/", site_views.v3_change_email_view, name="change_email"),
    path("dashboard/2fa/setup/", site_views.v3_2fa_setup_view, name="site_2fa_setup"),
    path("dashboard/security-triggers/", site_views.v3_security_triggers_view, name="site_security_triggers"),
    path("auth/2fa-verify/", site_views.v3_2fa_verify_view, name="site_2fa_verify"),
    path("auth/sp-verify/", site_views.v3_verify_sp_view, name="site_sp_verify"),
    path("dashboard/verification/", site_views.kyc_request_view, name="site_kyc_request"),
    path("privacy-policy/", site_views.privacy_policy, name="privacy_policy"),
    path("terms-of-service/", site_views.terms_of_service, name="terms_of_service"),
    path("refund-policy/", site_views.refund_policy, name="refund_policy"),
    path("contact/", site_views.contact_page, name="contact"),
    path("set-currency/", site_views.set_currency, name="set_currency"),
    path("ajax/validate-coupon/", site_views.ajax_validate_coupon, name="ajax_validate_coupon"),
    
    # Support Chat
    path("support/chats/", support_views.chat_list, name="chat_list"),
    path("support/chats/create/", support_views.create_chat, name="create_chat"),
    path("support/chats/<uuid:room_id>/", support_views.chat_room, name="chat_room"),
    path("support/chats/<uuid:room_id>/upload/", support_views.chat_file_upload, name="chat_file_upload"),
    path("support/chats/<uuid:room_id>/close/", support_views.close_chat, name="close_chat"),
    
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
    path("merchant/settings/domain-diagnostics/", views.merchant_domain_diagnostics, name="merchant_domain_diagnostics"),
    path("merchant/theme-builder/", views.merchant_theme_builder, name="merchant_theme_builder"),
    path("merchant/subscription/", views.merchant_subscription, name="merchant_subscription"),
]
