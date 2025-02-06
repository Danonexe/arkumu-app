from django.contrib import admin
from django.utils.timezone import now
from .models import Projekt, Akteur

@admin.register(Projekt)
class ProjektAdmin(admin.ModelAdmin):
    fields = ['bevorzugter_titel']
    list_display = ['bevorzugter_titel']

    def save_model(self, request, obj, form, change):
        if not change:  # New instance
            obj.date_created = now()
        obj.last_updated = now()
        super().save_model(request, obj, form, change)

@admin.register(Akteur)
class AkteurAdmin(admin.ModelAdmin):
    fields = ['name_de']
    list_display = ['name_de']

    def save_model(self, request, obj, form, change):
        if not change:  # New instance
            obj.date_created = now()
        obj.last_updated = now()
        super().save_model(request, obj, form, change)
    
