from django.urls import path

from apps.site import views

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("catalog/<slug:slug>/", views.product_detail, name="product_detail"),
    path("auth/login/", views.login_view, name="site_login"),
    path("auth/register/", views.register_view, name="site_register"),
    path("logout/", views.logout_view, name="site_logout"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/wallet/", views.wallet_page, name="dashboard_wallet"),
    path("dashboard/deposits/", views.deposits, name="dashboard_deposits"),
    path("dashboard/tickets/", views.tickets, name="dashboard_tickets"),
    path("control/", views.control_dashboard, name="control_dashboard"),
]
