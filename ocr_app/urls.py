from django.urls import path
from . import views

urlpatterns = [
    path('new-registration/', views.upload_card, name='new_registration'), 
    path('save/', views.register_card, name='save_card'),
    path('', views.main_page, name='icexpo_home'),

]
