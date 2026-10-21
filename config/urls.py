from django.urls import path, include
from django.views.generic.base import RedirectView
from django.http import HttpResponse
from fuel_router import views as fuel_views

urlpatterns = [
    # Root redirects directly to the interactive map interface
    path('', RedirectView.as_view(url='/map/', permanent=False), name='root_redirect'),
    path('map/', fuel_views.map_view, name='map_view'),
    path('health/', fuel_views.health_check, name='root_health_check'),
    path('api/', RedirectView.as_view(url='/api/v1/', permanent=False), name='api_redirect'),
    path('api/v1/', include('fuel_router.urls')),
    path('favicon.ico', lambda request: HttpResponse(status=204)),
]
