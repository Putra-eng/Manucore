from django.urls import path
from . import views

urlpatterns = [
    path("", views.landing_page, name="home"),
    path("login/", views.login_process, name="login"),
    path("register/", views.register, name="register"),

    path("admin-page/", views.admin_page, name="admin_page"),
    path("operator-page/", views.operator_page, name="operator_page"),
    path("client-page/", views.client_page, name="client_page"),

    path("user/delete/<str:id>/", views.user_delete, name="user_delete"),
    path("user/create/", views.user_create, name="user_create"),
    path("user/update/<str:id>/", views.user_update, name="user_update"),
]