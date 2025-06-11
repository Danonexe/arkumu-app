from django.contrib import admin
from .models import Mapping


@admin.register(Mapping)
class MappingAdmin(admin.ModelAdmin):
    list_display = ('id', 'scope', 'organization_id', 'created_at')
    list_filter = ('scope', 'organization_id', 'created_at')
    search_fields = ('organization_id',)
    readonly_fields = ('created_at', 'updated_at')
