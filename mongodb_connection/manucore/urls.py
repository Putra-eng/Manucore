from django.urls import path
from . import views

urlpatterns = [
    # Public
    path("",          views.landing_page,  name="home"),
    path("login/process/", views.login_process, name="login_process"),
    path("login/",    views.login_process, name="login"),
    path("logout/",   views.logout_view,   name="logout"),
    path("register/", views.register,      name="register"),

    # Role pages
    path("admin-page/",    views.admin_page,    name="admin_page"),
    path("operator-page/", views.operator_page, name="operator_page"),
    path("client-page/",   views.client_page,   name="client_page"),

    # User CRUD  (staff_users)
    path("user/create/",          views.user_create, name="user_create"),
    path("user/update/<str:id>/", views.user_update, name="user_update"),
    path("user/delete/<str:id>/", views.user_delete, name="user_delete"),

    # Request actions  (requests)
    path("request/approve/<str:id>/",  views.request_approve,  name="request_approve"),
    path("request/reject/<str:id>/",   views.request_reject,   name="request_reject"),
    path("request/download/<str:id>/", views.request_download, name="request_download"),

    # Production Order actions  (production_orders)
    path("po/assign/<str:id>/", views.po_assign, name="po_assign"),
]