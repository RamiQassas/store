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
from apps.site import api_views as site_api_views

# Import API components from config and REST framework
from config.urls import health, router
from apps.accounts.views import LoginView, RegisterView
from rest_framework_simplejwt.views import TokenRefreshView

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
    path("auth/sso-callback/", site_views.sso_transfer_view, name="sso_transfer_subdomain"),
    path("auth/forgot-password/", site_views.v3_forgot_password_view, name="site_forgot_password"),
    path("auth/reset-password/", site_views.v3_reset_password_view, name="site_reset_password"),
    path("auth/resend-verification/", site_views.resend_verification, name="resend_verification"),
    path("auth/email-verify/<uidb64>/<token>/", site_views.email_verify, name="email_verify"),
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
    path("suggestions/new/", site_views.site_product_suggestion, name="site_product_suggestion"),

    # Custom Pages (store-specific static pages created by merchant)
    path("page/<slug:slug>/", merchant_views.store_custom_page, name="store_custom_page"),

    # ==========================================
    # --- MERCHANT DASHBOARD ---
    # These views are ONLY available in tenant context.
    # They allow the store owner/employees to manage their own store.
    # ==========================================
    # These views are ONLY available in tenant context.
    # They allow the store owner/employees to manage their own store.
    # ==========================================
    path("merchant/", site_views.control_dashboard, name="control_dashboard"),
    path("merchant/dashboard-alias/", site_views.control_dashboard, name="merchant_dashboard"),

    # Products & Variants & Keys
    path("merchant/products/", site_views.control_products_list, name="control_products_list"),
    path("merchant/products/alias/", site_views.control_products_list, name="merchant_products"),
    path("merchant/products/create/", site_views.control_product_create, name="control_product_create"),
    path("merchant/products/create/alias/", site_views.control_product_create, name="merchant_product_create"),
    path("merchant/products/<uuid:pk>/edit/", site_views.control_product_edit, name="control_product_edit"),
    path("merchant/products/<uuid:pk>/edit/alias/", site_views.control_product_edit, name="merchant_product_edit"),
    path("merchant/products/<uuid:pk>/delete/", site_views.control_product_delete, name="control_product_delete"),
    path("merchant/products/<uuid:pk>/delete/alias/", site_views.control_product_delete, name="merchant_product_delete"),
    path("merchant/products/<uuid:product_pk>/variants/create/", site_views.control_variant_create, name="control_variant_create"),
    path("merchant/products/<uuid:product_pk>/variants/create/alias/", site_views.control_variant_create, name="merchant_variant_create"),
    path("merchant/products/import/", site_views.control_product_import, name="control_product_import"),
    path("merchant/products/import-raqamiyat/", merchant_views.merchant_import_raqamiyat_products, name="merchant_import_raqamiyat_products"),
    path("merchant/products/reorder-bulk-ajax/", site_views.control_products_reorder_bulk_ajax, name="control_products_reorder_bulk_ajax"),
    path("merchant/variants/<uuid:pk>/edit/", site_views.control_variant_edit, name="control_variant_edit"),
    path("merchant/variants/<uuid:pk>/edit/alias/", site_views.control_variant_edit, name="merchant_variant_edit"),
    path("merchant/variants/<uuid:pk>/keys/", site_views.control_variant_keys, name="control_variant_keys"),
    path("merchant/variants/<uuid:pk>/keys/alias/", site_views.control_variant_keys, name="merchant_variant_keys"),

    # Categories
    path("merchant/categories/", site_views.control_categories_list, name="control_categories_list"),
    path("merchant/categories/alias/", site_views.control_categories_list, name="merchant_categories"),
    path("merchant/categories/create/", site_views.control_category_edit, name="control_category_create"),
    path("merchant/categories/create/alias/", site_views.control_category_edit, name="merchant_category_create"),
    path("merchant/categories/create-ajax/", site_views.control_category_create_ajax, name="control_category_create_ajax"),
    path("merchant/categories/<uuid:pk>/edit/", site_views.control_category_edit, name="control_category_edit"),
    path("merchant/categories/<uuid:pk>/edit/alias/", site_views.control_category_edit, name="merchant_category_edit"),
    path("merchant/categories/<uuid:pk>/delete/", site_views.control_category_delete, name="control_category_delete"),
    path("merchant/categories/<uuid:pk>/delete/alias/", site_views.control_category_delete, name="merchant_category_delete"),

    # Orders
    path("merchant/orders/", site_views.control_orders_list, name="control_orders_list"),
    path("merchant/orders/alias/", site_views.control_orders_list, name="merchant_orders"),
    path("merchant/orders/<uuid:pk>/", site_views.control_order_detail, name="control_order_detail"),
    path("merchant/orders/<uuid:pk>/alias/", site_views.control_order_detail, name="merchant_order_detail"),
    path("merchant/orders/<uuid:pk>/update-status/", site_views.control_order_status_update, name="merchant_order_status_update"),

    # Coupons
    path("merchant/coupons/", site_views.control_coupons_list, name="control_coupons_list"),
    path("merchant/coupons/alias/", site_views.control_coupons_list, name="merchant_coupons"),
    path("merchant/coupons/create/", site_views.control_coupon_create, name="control_coupon_create"),
    path("merchant/coupons/create/alias/", site_views.control_coupon_create, name="merchant_coupon_create"),
    path("merchant/coupons/<uuid:pk>/edit/", site_views.control_coupon_edit, name="control_coupon_edit"),
    path("merchant/coupons/<uuid:pk>/edit/alias/", site_views.control_coupon_edit, name="merchant_coupon_edit"),
    path("merchant/coupons/<uuid:pk>/delete/", site_views.control_coupon_delete, name="control_coupon_delete"),
    path("merchant/coupons/<uuid:pk>/delete/alias/", site_views.control_coupon_delete, name="merchant_coupon_delete"),
    path("merchant/coupons/geo-stats/", site_views.control_geo_stats, name="control_geo_stats"),
    path("merchant/coupons/usage/", site_views.control_coupon_usage, name="control_coupon_usage"),
    path("merchant/coupons/usage/export/", site_views.export_coupon_usage_csv, name="control_coupon_usage_export"),

    # Deposits
    path("merchant/deposits/", site_views.control_deposits, name="control_deposits"),
    path("merchant/deposits/<uuid:pk>/", site_views.control_deposit_detail, name="control_deposit_detail"),

    # Withdrawals
    path("merchant/withdrawals/", site_views.control_withdrawals, name="control_withdrawals"),
    path("merchant/withdrawals/<uuid:pk>/", site_views.control_withdrawal_detail, name="control_withdrawal_detail"),

    # Transfers
    path("merchant/transfers/", site_views.control_transfers, name="control_transfers"),
    path("merchant/transfers/<uuid:pk>/reverse/", site_views.control_transfer_reverse, name="control_transfer_reverse"),
    path("merchant/transfers/<uuid:pk>/suspend/", site_views.control_transfer_suspend, name="control_transfer_suspend"),
    path("merchant/transfers/<uuid:pk>/unsuspend/", site_views.control_transfer_unsuspend, name="control_transfer_unsuspend"),
    path("merchant/transfers/<uuid:pk>/edit-amount/", site_views.control_transfer_edit_amount, name="control_transfer_edit_amount"),

    # Debts
    path("merchant/debts/", site_views.control_debts, name="control_debts"),

    # Wallets
    path("merchant/wallets/", site_views.control_wallets_list, name="control_wallets_list"),

    # Recharge Cards
    path("merchant/recharge-cards/", site_views.control_recharge_cards, name="control_recharge_cards"),
    path("merchant/recharge-cards/generate/", site_views.control_recharge_cards_generate, name="control_recharge_cards_generate"),
    path("merchant/recharge-cards/<uuid:pk>/cancel/", site_views.control_recharge_card_cancel, name="control_recharge_card_cancel"),

    # Currencies
    path("merchant/currencies/", site_views.currencies_list, name="currencies_list"),
    path("merchant/currencies/create/", site_views.currency_create, name="currency_create"),
    path("merchant/currencies/<uuid:pk>/edit/", site_views.currency_edit, name="currency_edit"),

    # Payment Methods
    path("merchant/payment-methods/", site_views.payment_methods_list, name="payment_methods_list"),
    path("merchant/payment-methods/create/", site_views.payment_method_create, name="payment_method_create"),
    path("merchant/payment-methods/<uuid:pk>/edit/", site_views.payment_method_edit, name="payment_method_edit"),

    # Users
    path("merchant/users/", site_views.control_users_list, name="control_users_list"),
    path("merchant/users/<uuid:public_uuid>/moderate/", site_views.control_user_moderate, name="control_user_moderate"),

    # KYC Verification
    path("merchant/kyc/", site_views.control_kycs_list, name="control_kycs_list"),
    path("merchant/kyc/settings/", site_views.control_kyc_settings, name="control_kyc_settings"),
    path("merchant/kyc/<uuid:pk>/", site_views.control_kyc_detail, name="control_kyc_detail"),

    # Product Suggestions
    path("merchant/suggestions/", site_views.control_product_suggestions_list, name="control_product_suggestions_list"),
    path("merchant/suggestions/<uuid:pk>/", site_views.control_product_suggestion_detail, name="control_product_suggestion_detail"),

    # Support / Open Ticket
    path("merchant/support/chat-open/", site_views.control_support_chat_open, name="control_support_chat_open"),

    # Reports
    path("merchant/reports/", site_views.control_reports, name="control_reports"),

    # Send Notification
    path("merchant/notifications/send/", site_views.control_send_notification, name="control_send_notification"),

    # Testimonials / Customer Reviews
    path("merchant/testimonials/", site_views.control_testimonials_list, name="control_testimonials_list"),
    path("merchant/testimonials/<uuid:pk>/moderate/", site_views.control_testimonial_moderate, name="control_testimonial_moderate"),

    # Announcements
    path("merchant/announcements/", site_views.control_announcements, name="control_announcements"),
    path("merchant/announcements/create/", site_views.control_announcement_create, name="control_announcement_create"),
    path("merchant/announcements/<uuid:pk>/edit/", site_views.control_announcement_edit, name="control_announcement_edit"),
    path("merchant/announcements/<uuid:pk>/delete/", site_views.control_announcement_delete, name="control_announcement_delete"),

    # Database Maintenance
    path("merchant/db-maintenance/", site_views.control_db_maintenance, name="control_db_maintenance"),

    # API Integrations & Alkasr Dashboard
    path("merchant/api-integrations/", site_views.control_api_integrations_list, name="control_api_integrations_list"),
    path("merchant/api-integrations/create/", site_views.control_api_integration_create, name="control_api_integration_create"),
    path("merchant/api-integrations/<uuid:pk>/edit/", site_views.control_api_integration_edit, name="control_api_integration_edit"),
    path("merchant/api-integrations/<uuid:pk>/delete/", site_views.control_api_integration_delete, name="control_api_integration_delete"),
    path("merchant/apicontrol/", site_views.control_apicontrol_dashboard, name="control_apicontrol_dashboard"),

    # Staff / Employees (Store-specific)
    path("merchant/employees/", merchant_views.merchant_employees, name="merchant_employees"),
    path("merchant/employees/create/", merchant_views.merchant_employee_form, name="merchant_employee_create"),
    path("merchant/employees/<uuid:pk>/edit/", merchant_views.merchant_employee_form, name="merchant_employee_edit"),
    path("merchant/employees/<uuid:pk>/delete/", merchant_views.merchant_employee_delete, name="merchant_employee_delete"),

    # Custom Pages CRUD (Store-specific)
    path("merchant/pages/", merchant_views.merchant_pages, name="merchant_pages"),
    path("merchant/pages/create/", merchant_views.merchant_page_form, name="merchant_page_create"),
    path("merchant/pages/<uuid:pk>/edit/", merchant_views.merchant_page_form, name="merchant_page_edit"),
    path("merchant/pages/<uuid:pk>/delete/", merchant_views.merchant_page_delete, name="merchant_page_delete"),

    # Store Settings & Theme (Store-specific)
    path("merchant/settings/", merchant_views.merchant_settings, name="merchant_settings"),
    path("merchant/settings/domain-diagnostics/", merchant_views.merchant_domain_diagnostics, name="merchant_domain_diagnostics"),
    path("merchant/theme-builder/", merchant_views.merchant_theme_builder, name="merchant_theme_builder"),
    path("merchant/subscription/", merchant_views.merchant_subscription, name="merchant_subscription"),

    # Ajax Searches
    path("ajax/user-search/", site_views.ajax_user_search, name="ajax_user_search"),
    path("ajax/product-search/", site_views.ajax_product_search, name="ajax_product_search"),
    path("ajax/country-search/", site_views.ajax_country_search, name="ajax_country_search"),

    # Root Assets (Service Worker)
    path("sw.js", site_views.service_worker, name="service_worker"),

    # REST APIs from config/urls.py
    path("api/health/", health),
    path("api/auth/register/", RegisterView.as_view(), name="register"),
    path("api/auth/login/", LoginView.as_view(), name="login"),
    path("api/auth/token/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("api/", include(router.urls)),

    # Custom Platform APIs (Wallet holds, Deposits, Withdrawals processing)
    path("api/deposits/<uuid:pk>/approve/", site_api_views.api_deposit_approve, name="api_deposit_approve"),
    path("api/deposits/<uuid:pk>/reject/", site_api_views.api_deposit_reject, name="api_deposit_reject"),
    path("api/deposits/<uuid:pk>/correct/", site_api_views.api_deposit_correct, name="api_deposit_correct"),
    path("api/withdrawals/max-amount/", site_api_views.get_max_withdrawable, name="api_get_max_withdrawable"),
    path("api/conversion-preview/", site_api_views.get_conversion_preview, name="api_get_conversion_preview"),
    path("api/wallets/<uuid:pk>/hold/", site_api_views.api_wallet_hold, name="api_wallet_hold"),
    path("api/wallets/<uuid:pk>/unhold/", site_api_views.api_wallet_unhold, name="api_wallet_unhold"),
    path("api/withdrawals/<uuid:pk>/process/", site_api_views.api_withdrawal_process, name="api_withdrawal_process"),
    path("api/withdrawals/<uuid:pk>/approve/", site_api_views.api_withdrawal_approve, name="api_withdrawal_approve"),
    path("api/withdrawals/<uuid:pk>/complete/", site_api_views.api_withdrawal_complete, name="api_withdrawal_complete"),
    path("api/withdrawals/<uuid:pk>/reject/", site_api_views.api_withdrawal_reject, name="api_withdrawal_reject"),
    path("api/orders/<uuid:pk>/mark-read/", site_api_views.api_order_mark_read, name="api_order_mark_read"),
    path("api/users/search/", site_api_views.api_user_search, name="api_user_search"),
    path("api/users/lookup/", site_api_views.api_lookup_user, name="api_lookup_user"),
]

# Serve media files on subdomains
from django.views.static import serve
from django.urls import re_path
from django.conf import settings
urlpatterns += [
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
]
