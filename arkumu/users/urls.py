from django.urls import path
from django.views.generic import RedirectView
from django.urls import reverse_lazy

from .views import user_detail_view
from .views import user_redirect_view
from .views import user_update_view

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("<str:username>/", view=user_detail_view, name="detail"),
    # Temporary Shibboleth login redirect until properly implemented
    path("shibboleth/login/", 
         RedirectView.as_view(url=reverse_lazy('account_login'), 
                            permanent=False),
         name="shibboleth_login"),
]
