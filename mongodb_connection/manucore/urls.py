from django.urls import path
from .views import landing_page, login_process, register, admin_page, operator_page, client_page

urlpatterns = [
    path("", landing_page, name="home"),
    path("login/", login_process, name="login"),
    path("register/", register, name="register"),
    path('admin-page/', admin_page, name='admin_page'),
    path('operator-page/', operator_page, name='operator_page'),
    path('client-page/', client_page, name='client_page'),
]