from django.urls import path
from apps.site import views, api_views

urlpatterns = [
    # User Dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/wallet/", views.wallet_page, name="dashboard_wallet"),
    path("dashboard/deposits/", views.deposits, name="dashboard_deposits"),
    path("dashboard/withdrawals/", views.withdrawals, name="dashboard_withdrawals"),
    path("dashboard/notifications/settings/", views.notification_settings, name="notification_settings"),

    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/<uuid:pk>/", views.product_detail, name="product_detail"),
    
    # API Endpoints
    path("api/deposits/<uuid:pk>/approve/", api_views.api_deposit_approve, name="api_deposit_approve"),
    path("api/deposits/<uuid:pk>/reject/", api_views.api_deposit_reject, name="api_deposit_reject"),
    path("api/deposits/<uuid:pk>/correct/", api_views.api_deposit_correct, name="api_deposit_correct"),
    path("api/wallets/<uuid:pk>/hold/", api_views.api_wallet_hold, name="api_wallet_hold"),
    path("api/wallets/<uuid:pk>/unhold/", api_views.api_wallet_unhold, name="api_wallet_unhold"),
    path("api/withdrawals/<uuid:pk>/process/", api_views.api_withdrawal_process, name="api_withdrawal_process"),
    path("api/withdrawals/<uuid:pk>/approve/", api_views.api_withdrawal_approve, name="api_withdrawal_approve"),
    path("api/withdrawals/<uuid:pk>/complete/", api_views.api_withdrawal_complete, name="api_withdrawal_complete"),
    path("api/withdrawals/<uuid:pk>/reject/", api_views.api_withdrawal_reject, name="api_withdrawal_reject"),

    # AUTH V3 (FINAL)
    path("auth/login/", views.v3_login_view, name="v3_login"),
    path("auth/register/", views.v3_register_view, name="v3_register"),
    path("auth/verify/", views.v3_verify_otp_view, name="v3_verify_otp"),
    path("auth/forgot-password/", views.v3_forgot_password_view, name="v3_forgot_password"),
    path("auth/reset-password/", views.v3_reset_password_view, name="v3_reset_password"),
    path("auth/logout/", views.v3_logout_view, name="v3_logout"),
    
    # Control Panel
    path("control/", views.control_dashboard, name="control_dashboard"),
    path("control/payment-methods/", views.payment_methods_list, name="payment_methods_list"),
    path("control/payment-methods/create/", views.payment_method_create, name="payment_method_create"),
    path("control/payment-methods/<uuid:pk>/edit/", views.payment_method_edit, name="payment_method_edit"),
    path("control/deposits/", views.control_deposits, name="control_deposits"),
    path("control/withdrawals/", views.control_withdrawals, name="control_withdrawals"),
    path("control/withdrawals/<uuid:pk>/", views.control_withdrawal_detail, name="control_withdrawal_detail"),
    path("control/currencies/", views.currencies_list, name="currencies_list"),
    path("control/currencies/create/", views.currency_create, name="currency_create"),
    path("control/currencies/<uuid:pk>/edit/", views.currency_edit, name="currency_edit"),
    path("control/users/", views.control_users_list, name="control_users_list"),
    path("control/users/<uuid:public_uuid>/moderate/", views.control_user_moderate, name="control_user_moderate"),
    path("control/products/", views.control_products_list, name="control_products_list"),
    path("control/products/create/", views.control_product_create, name="control_product_create"),
    path("control/products/categories/create-ajax/", views.control_category_create_ajax, name="control_category_create_ajax"),
    path("control/products/<uuid:pk>/edit/", views.control_product_edit, name="control_product_edit"),
    path("control/products/<uuid:product_pk>/variants/create/", views.control_variant_create, name="control_variant_create"),
    path("control/variants/<uuid:pk>/edit/", views.control_variant_edit, name="control_variant_edit"),
    path("control/orders/", views.control_orders_list, name="control_orders_list"),
    path("control/orders/<uuid:pk>/", views.control_order_detail, name="control_order_detail"),
    path("control/wallets/", views.control_wallets_list, name="control_wallets_list"),
    path("control/reports/", views.control_reports, name="control_reports"),
    path("control/notifications/send/", views.control_send_notification, name="control_send_notification"),

    # Legal & Support Pages
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("terms-of-service/", views.terms_of_service, name="terms_of_service"),
    path("refund-policy/", views.refund_policy, name="refund_policy"),
    path("contact/", views.contact_page, name="contact"),
    path("sw.js", views.service_worker, name="service_worker"),
    path("set-currency/", views.set_currency, name="set_currency"),
]
