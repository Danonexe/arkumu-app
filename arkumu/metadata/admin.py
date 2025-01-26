from django.contrib import admin
from .models import Projekt, Akteur

@admin.register(Projekt)
class ProjektAdmin(admin.ModelAdmin):
    fields = ['bevorzugter_titel']
    list_display = ['bevorzugter_titel']

@admin.register(Akteur)
class AkteurAdmin(admin.ModelAdmin):
    fields = ['name_de']
    list_display = ['name_de']
    
