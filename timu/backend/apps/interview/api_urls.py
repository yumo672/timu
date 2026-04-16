from django.urls import path

from . import views


urlpatterns = [
    path("", views.api_root, name="api-root"),
    path("register/", views.register_user, name="api-register"),
    path("login/", views.login_user, name="api-login"),
    path("logout/", views.logout_user, name="api-logout"),
    path("session/", views.session_user, name="api-session"),
    path("purchases/", views.purchases, name="api-purchases"),
    path("purchases/<int:request_id>/", views.purchase_detail, name="api-purchase-detail"),
    path("purchases/<int:request_id>/submit/", views.submit_purchase, name="api-purchase-submit"),
    path("purchases/<int:request_id>/approve/", views.approve_purchase, name="api-purchase-approve"),
    path("purchases/<int:request_id>/reject/", views.reject_purchase, name="api-purchase-reject"),
]
