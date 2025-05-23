from django.conf import settings
from rest_framework.routers import DefaultRouter
from rest_framework.routers import SimpleRouter

from arkumu.users.api.views import UserViewSet
from arkumu.rest.views.import_viewsets import ImportViewSet, TestingViewSet

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

# User viewsets
router.register("users", UserViewSet)

# Import viewsets - explicitly set basename and viewset
router.register(r'import', ImportViewSet, basename='import')
router.register(r'testing', TestingViewSet, basename='testing')

app_name = "api"
urlpatterns = router.urls
