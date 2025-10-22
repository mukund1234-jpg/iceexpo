from django.urls import path
from . import views

urlpatterns = [
    path('upload/', views.upload_card, name='new_registration'),
    path('save/', views.register_card, name='save_card'),
    path('', views.main_page, name='icexpo_home'),
    path('already/', views.login_card, name='already_registered'),
    path('profile/', views.profile, name='profile_page'),
    path('add-login/',views.login_after_card, name='add_login'),
    path('logout/', views.logout_view, name='logout_view')
,]
