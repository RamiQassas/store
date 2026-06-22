from django.urls import path, include

# ============================================================
# Multi-Tenant URL Configuration
# ============================================================
# This urlconf is used ONLY when request.store is set (i.e., a subdomain
# or custom domain request). It maps store URLs to the SAME views used
# by the main Raqamiyat platform.
#
# KEY PRINCIPLE: No separate views or templates per store.
# - site_views handles all storefront pages (home, catalog, product, dashboard, etc.)
# - TenantManager automatically filters all DB queries to this store's data
# - Store branding (logo, colors, name) is injected via tenant_context processor
# - The only store-specific views are the Merchant Dashboard (merchant_*)
#   which are for the store owner/employees to manage their own store.
# ============================================================

# Shared platform views — same code as main Raqamiyat site
from apps.site import views as site_views
from apps.support import views as support_views

# Store-specific views — merchant dashboard only
from apps.stores import views as merchant_views

urlpatterns = [
    # ==========================================
    # --- STOREFRONT (Customer Facing) ---
    # These use the SAME views and templates as the main Raqamiyat site.
    # TenantManager ensures data is scoped to this store only.
    # ==========================================

    # Home & Catalog
    path("", site_views.home, name="home"),
    path("", site_views.home, name="store_home"),          # Alias for backward compat
    path("catalog/", site_views.catalog, name="catalog"),
    path("catalog/", site_views.catalog, name="store_catalog"),  # Alias
    path("catalog/<uuid:pk>/", site_views.product_detail, name="product_detail"),
    path("catalog/<uuid:pk>/", site_views.product_detail, name="store_product_detail"),  # Alias

    # Authentication — same auth flow as main platform
    path("auth/login/", site_views.v3_login_view, name="site_login"),
    path("auth/login/", site_views.v3_login_view, name="store_login"),          # Alias
    path("auth/register/", site_views.v3_register_view, name="site_register"),
    path("auth/register/", site_views.v3_register_view, name="store_register"),  # Alias
    path("auth/logout/", site_views.v3_logout_view, name="site_logout"),
    path("auth/logout/", site_views.v3_logout_view, name="store_logout"),        # Alias
    path("auth/verify-otp/", site_views.v3_verify_otp_view, name="site_verify_otp"),
    path("auth/2fa-verify/", site_views.v3_2fa_verify_view, name="site_2fa_verify"),
    path("auth/sp-verify/", site_views.v3_verify_sp_view, name="site_sp_verify"),
    path("accounts/", include("allauth.urls")),

    # Customer Dashboard — same dashboard as main platform, filtered by store
    path("dashboard/", site_views.dashboard, name="dashboard"),
    path("dashboard/", site_views.dashboard, name="store_dashboard"),           # Alias
    path("dashboard/wallet/", site_views.wallet_page, name="dashboard_wallet"),
    path("dashboard/wallet/", site_views.wallet_page, name="store_wallet"),     # Alias
    path("dashboard/orders/", site_views.orders_list, name="dashboard_orders"),
    path("dashboard/orders/<uuid:pk>/", site_views.order_detail, name="dashboard_order_detail"),
    path("dashboard/orders/<uuid:pk>/", site_views.order_detail, name="store_order_detail"),  # Alias
    path("dashboard/notifications/", site_views.notifications_list, name="notifications_list"),
    path("dashboard/notifications/settings/", site_views.notification_settings, name="notification_settings"),
    path("dashboard/change-password/", site_views.v3_change_password_view, name="change_password"),
    path("dashboard/change-email/", site_views.v3_change_email_view, name="change_email"),
    path("dashboard/2fa/setup/", site_views.v3_2fa_setup_view, name="site_2fa_setup"),
    path("dashboard/security-triggers/", site_views.v3_security_triggers_view, name="site_security_triggers"),
    path("dashboard/verification/", site_views.kyc_request_view, name="site_kyc_request"),

    # Wallet Recharge — uses merchant_views since it's store-specific (recharge cards)
    path("dashboard/wallet/recharge/", merchant_views.store_wallet_recharge, name="dashboard_recharge_wallet"),
    path("dashboard/wallet/recharge/", merchant_views.store_wallet_recharge, name="store_wallet_recharge"),  # Alias

    # Deposits & Withdrawals — shared with main platform
    path("dashboard/deposits/", site_views.deposits, name="dashboard_deposits"),
    path("dashboard/withdrawals/", site_views.withdrawals, name="dashboard_withdrawals"),
    path("dashboard/transfer/", site_views.transfer_page, name="dashboard_transfer"),
    path("dashboard/transfer/history/", site_views.transfer_history, name="dashboard_transfer_history"),

    # Support Chat — same support system
    path("support/chats/", support_views.chat_list, name="chat_list"),
    path("support/chats/create/", support_views.create_chat, name="create_chat"),
    path("support/chats/<uuid:room_id>/", support_views.chat_room, name="chat_room"),
    path("support/chats/<uuid:room_id>/upload/", support_views.chat_file_upload, name="chat_file_upload"),
    path("support/chats/<uuid:room_id>/close/", support_views.close_chat, name="close_chat"),

    # Legal / Static Pages
    path("privacy-policy/", site_views.privacy_policy, name="privacy_policy"),
    path("terms-of-service/", site_views.terms_of_service, name="terms_of_service"),
    path("refund-policy/", site_views.refund_policy, name="refund_policy"),
    path("contact/", site_views.contact_page, name="contact"),

    # Utilities
    path("set-currency/", site_views.set_currency, name="set_currency"),
    path("ajax/validate-coupon/", site_views.ajax_validate_coupon, name="ajax_validate_coupon"),

    # Custom Pages (store-specific static pages created by merchant)
    path("page/<slug:slug>/", merchant_views.store_custom_page, name="store_custom_page"),

    # ==========================================
    # --- MERCHANT DASHBOARD ---
    # These views are ONLY available in tenant context.
    # They allow the store owner/employees to manage their own store.
    # ==========================================
    path("merchant/", merchant_views.merchant_dashboard, name="merchant_dashboard"),

    # Products & Variants & Keys
    path("merchant/products/", merchant_views.merchant_products, name="merchant_products"),
    path("merchant/products/create/", merchant_views.merchant_product_form, name="merchant_product_create"),
    path("merchant/products/<uuid:pk>/edit/", merchant_views.merchant_product_form, name="merchant_product_edit"),
    path("merchant/products/<uuid:pk>/delete/", merchant_views.merchant_product_delete, name="merchant_product_delete"),
    path("merchant/products/<uuid:product_pk>/variants/create/", merchant_views.merchant_variant_form, name="merchant_variant_create"),
    path("merchant/variants/<uuid:pk>/edit/", merchant_views.merchant_variant_form, name="merchant_variant_edit"),
    path("merchant/variants/<uuid:pk>/keys/", merchant_views.merchant_variant_keys, name="merchant_variant_keys"),

    # Categories
    path("merchant/categories/", merchant_views.merchant_categories, name="merchant_categories"),
    path("merchant/categories/create/", merchant_views.merchant_category_form, name="merchant_category_create"),
    path("merchant/categories/<uuid:pk>/edit/", merchant_views.merchant_category_form, name="merchant_category_edit"),
    path("merchant/categories/<uuid:pk>/delete/", merchant_views.merchant_category_delete, name="merchant_category_delete"),

    # Orders
    path("merchant/orders/", merchant_views.merchant_orders, name="merchant_orders"),
    path("merchant/orders/<uuid:pk>/", merchant_views.merchant_order_detail, name="merchant_order_detail"),
    path("merchant/orders/<uuid:pk>/update-status/", merchant_views.merchant_order_status_update, name="merchant_order_status_update"),

    # Coupons
    path("merchant/coupons/", merchant_views.merchant_coupons, name="merchant_coupons"),
    path("merchant/coupons/create/", merchant_views.merchant_coupon_form, name="merchant_coupon_create"),
    path("merchant/coupons/<uuid:pk>/edit/", merchant_views.merchant_coupon_form, name="merchant_coupon_edit"),
    path("merchant/coupons/<uuid:pk>/delete/", merchant_views.merchant_coupon_delete, name="merchant_coupon_delete"),

    # Staff / Employees
    path("merchant/employees/", merchant_views.merchant_employees, name="merchant_employees"),
    path("merchant/employees/create/", merchant_views.merchant_employee_form, name="merchant_employee_create"),
    path("merchant/employees/<uuid:pk>/edit/", merchant_views.merchant_employee_form, name="merchant_employee_edit"),
    path("merchant/employees/<uuid:pk>/delete/", merchant_views.merchant_employee_delete, name="merchant_employee_delete"),

    # Custom Pages CRUD
    path("merchant/pages/", merchant_views.merchant_pages, name="merchant_pages"),
    path("merchant/pages/create/", merchant_views.merchant_page_form, name="merchant_page_create"),
    path("merchant/pages/<uuid:pk>/edit/", merchant_views.merchant_page_form, name="merchant_page_edit"),
    path("merchant/pages/<uuid:pk>/delete/", merchant_views.merchant_page_delete, name="merchant_page_delete"),

    # Store Settings & Theme
    path("merchant/settings/", merchant_views.merchant_settings, name="merchant_settings"),
    path("merchant/settings/domain-diagnostics/", merchant_views.merchant_domain_diagnostics, name="merchant_domain_diagnostics"),
    path("merchant/theme-builder/", merchant_views.merchant_theme_builder, name="merchant_theme_builder"),
    path("merchant/subscription/", merchant_views.merchant_subscription, name="merchant_subscription"),
]
