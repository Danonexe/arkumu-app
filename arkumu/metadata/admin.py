from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
import json

from .models.mappings import Mapping


@admin.register(Mapping)
class MappingAdmin(admin.ModelAdmin):
    list_display = (
        'name', 
        'organization_id', 
        'validation_status', 
        'dataset_count', 
        'column_count',
        'relationship_count',
        'created_by', 
        'created_at', 
        'last_executed'
    )
    
    list_filter = (
        'validation_status', 
        'organization_id', 
        'created_at', 
        'last_executed'
    )
    
    search_fields = (
        'name', 
        'description', 
        'organization_id',
        'created_by__username'
    )
    
    readonly_fields = (
        'id',
        'created_at', 
        'updated_at', 
        'dataset_count',
        'column_count', 
        'relationship_count',
        'mapping_config_preview',
        'view_graph_link'
    )
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'description', 'organization_id', 'validation_status')
        }),
        ('Configuration', {
            'fields': ('source_datasets', 'mapping_config_preview'),
            'classes': ('collapse',)
        }),
        ('Statistics', {
            'fields': ('dataset_count', 'column_count', 'relationship_count'),
        }),
        ('Execution', {
            'fields': ('last_executed', 'execution_stats'),
            'classes': ('collapse',)
        }),
        ('System', {
            'fields': ('id', 'created_by', 'created_at', 'updated_at', 'view_graph_link'),
            'classes': ('collapse',)
        }),
    )
    
    def dataset_count(self, obj):
        """Number of source datasets in this mapping."""
        return len(obj.source_datasets) if obj.source_datasets else 0
    dataset_count.short_description = 'Datasets'
    
    def column_count(self, obj):
        """Number of columns in workspace."""
        workspace_columns = obj.mapping_config.get('workspace_columns', {})
        return len(workspace_columns)
    column_count.short_description = 'Columns'
    
    def relationship_count(self, obj):
        """Number of FK relationships configured."""
        workspace_columns = obj.mapping_config.get('workspace_columns', {})
        fk_count = sum(1 for col in workspace_columns.values() if col.get('is_fk', False))
        context_count = sum(1 for col in workspace_columns.values() if col.get('is_relationship_context', False))
        anchor_count = sum(1 for col in workspace_columns.values() if col.get('is_anchor', False))
        
        if fk_count or context_count or anchor_count:
            return format_html(
                '<span title="FK: {}, Contexts: {}, Anchors: {}">{} relationships</span>',
                fk_count, context_count, anchor_count, fk_count + context_count
            )
        return '0'
    relationship_count.short_description = 'Relationships'
    
    def mapping_config_preview(self, obj):
        """Pretty-printed preview of mapping configuration."""
        if not obj.mapping_config:
            return "No configuration"
        
        # Create a summary instead of full JSON
        config = obj.mapping_config
        workspace_columns = config.get('workspace_columns', {})
        
        summary = {
            'datasets': config.get('selected_datasets', []),
            'columns': len(workspace_columns),
            'relationships': {
                'foreign_keys': sum(1 for col in workspace_columns.values() if col.get('is_fk', False)),
                'anchors': sum(1 for col in workspace_columns.values() if col.get('is_anchor', False)),
                'contexts': sum(1 for col in workspace_columns.values() if col.get('is_relationship_context', False)),
                'external_ontology': sum(1 for col in workspace_columns.values() if col.get('is_external_ontology', False))
            }
        }
        
        # Add some sample columns
        if workspace_columns:
            sample_columns = list(workspace_columns.items())[:3]
            summary['sample_columns'] = {
                col_id: {
                    'name': col_data.get('name'),
                    'dataset': col_data.get('dataset'),
                    'type': col_data.get('type'),
                    'flags': [flag for flag in ['is_fk', 'is_anchor', 'is_multi_value', 'is_relationship_context'] 
                             if col_data.get(flag, False)]
                }
                for col_id, col_data in sample_columns
            }
        
        json_str = json.dumps(summary, indent=2)
        return format_html('<pre style="max-height: 300px; overflow-y: auto; font-size: 11px;">{}</pre>', json_str)
    mapping_config_preview.short_description = 'Configuration Preview'
    
    def view_graph_link(self, obj):
        """Link to view the mapping graph."""
        if obj.pk:
            url = f"/metadata/csv-mapping-editor/?organization={obj.organization_id}"
            return format_html(
                '<a href="{}" target="_blank" class="button">📊 Open in Editor</a> | '
                '<a href="/metadata/mapping-graph-data/?organization={}&mapping_id={}" target="_blank" class="button">🔗 View Graph Data</a>',
                url, obj.organization_id, obj.pk
            )
        return "Save first"
    view_graph_link.short_description = 'Actions'
    
    def get_queryset(self, request):
        """Optimize queries by selecting related fields."""
        return super().get_queryset(request).select_related('created_by')


