# from django.contrib import admin
# from django.urls import path, include
# from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
# from django.shortcuts import render
# from core.views import home
# from django.conf import settings
# from django.conf.urls.static import static

# def home(request):
#       return render(request, 'home.html')

# urlpatterns = [
#     path('admin/', admin.site.urls),
#     path('api/', include('core.urls')),  # core app APIs
#     path('', home),  # This will handle the root URL
# ]


# if settings.DEBUG:
#     urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
#     urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)