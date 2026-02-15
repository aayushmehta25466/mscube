from django.urls import path 
from . import views

urlpatterns = [
    path('', views.IndexView.as_view(), name='index'),
    path('about/', views.AboutView.as_view(), name='about'),
    path('contact/', views.ContactView.as_view(), name='contact'),
    path('events/', views.EventsView.as_view(), name='events'),
    path('notifications/', views.NotificationsView.as_view(), name='notifications'),
    path('programs/', views.ProgramsView.as_view(), name='programs'),
    path('trainers/', views.TrainersView.as_view(), name='trainers'),
    path('tech/', views.TechView.as_view(), name='tech'),
]
