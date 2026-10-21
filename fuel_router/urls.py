from django.urls import path
from . import views

urlpatterns = [
    path('', views.api_root, name='api_root'),
    path('health/', views.health_check, name='health_check'),
    path('route/plan/', views.plan_fuel_route, name='plan_fuel_route'),
    path('route/optimize/', views.plan_fuel_route, name='optimize_route'),
]
