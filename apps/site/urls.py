from django.urls import path

from apps.site import views

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/<slug:slug>/", views.product_detail, name="product_detail"),
    
    # Auth
    path("auth/login/", views.login_view, name="site_login"),
    path("auth/register/", views.register_view, name="site_register"),
    path("auth/verify/<str:uidb64>/<str:token>/", views.email_verify, name="email_verify"),
    path("auth/resend-verification/", views.resend_verification, name="resend_verification"),
    path("logout/", views.logout_view, name="site_logout"),
    
    # User Dashboard
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/wallet/", views.wallet_page, name="dashboard_wallet"),
    path("dashboard/deposits/", views.deposits, name="dashboard_deposits"),
    path("dashboard/withdrawals/", views.withdrawals, name="dashboard_withdrawals"),
    path("dashboard/tickets/", views.tickets, name="dashboard_tickets"),
    path("dashboard/tickets/<uuid:pk>/", views.ticket_detail, name="ticket_detail"),
    
    # Admin Control
    path("control/", views.control_dashboard, name="control_dashboard"),
    path("control/payment-methods/", views.payment_methods_list, name="payment_methods_list"),
    path("control/payment-methods/create/", views.payment_method_create, name="payment_method_create"),
    path("control/payment-methods/<int:pk>/edit/", views.payment_method_edit, name="payment_method_edit"),
    path("control/withdrawals/", views.control_withdrawals, name="control_withdrawals"),
    path("control/currencies/", views.currencies_list, name="currencies_list"),
    path("control/currencies/create/", views.currency_create, name="currency_create"),
    path("control/currencies/<int:pk>/edit/", views.currency_edit, name="currency_edit"),
    path("control/users/", views.control_users_list, name="control_users_list"),
    path("control/users/<int:pk>/moderate/", views.control_user_moderate, name="control_user_moderate"),
    path("control/products/", views.control_products_list, name="control_products_list"),
    path("control/products/create/", views.control_product_create, name="control_product_create"),
    path("control/products/<uuid:pk>/edit/", views.control_product_edit, name="control_product_edit"),
    path("control/products/<uuid:product_pk>/variants/create/", views.control_variant_create, name="control_variant_create"),
    path("control/variants/<uuid:pk>/edit/", views.control_variant_edit, name="control_variant_edit"),
    path("control/tickets/", views.control_tickets_list, name="control_tickets_list"),
    path("control/orders/", views.control_orders_list, name="control_orders_list"),
    path("control/orders/<uuid:pk>/", views.control_order_detail, name="control_order_detail"),
    path("control/wallets/", views.control_wallets_list, name="control_wallets_list"),
    path("control/reports/", views.control_reports, name="control_reports"),

    # Legal & Support Pages
    path("privacy-policy/", views.privacy_policy, name="privacy_policy"),
    path("terms-of-service/", views.terms_of_service, name="terms_of_service"),
    path("refund-policy/", views.refund_policy, name="refund_policy"),
    path("contact/", views.contact_page, name="contact"),
]
