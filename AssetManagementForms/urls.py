"""
URL configuration for GoogleForms_Kompass project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.views.static import serve as static_serve


urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('forms.urls')),
]

urlpatterns += [
    re_path(r'^media/(?P<path>.*)$', static_serve, {'document_root': settings.MEDIA_ROOT}),
]