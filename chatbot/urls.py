from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('ask-ai/', views.ask_ai, name='ask_ai'),
]