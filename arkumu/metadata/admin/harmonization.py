"""
Django Admin interface for Harmonization models.
"""

from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.db.models import Count
from arkumu.metadata.models.harmonization import (
    HarmonizationRule,
    HarmonizationExecution,
    HarmonizationConflict
)


@admin.register(HarmonizationRule)
class HarmonizationRuleAdmin(admin.ModelAdmin):
    list_display = [
        'catalog_property_label',
        'source_organization',
        'source_property_pattern',
        'mapping_type',
        'priority',
        'is_active',
        'validated_status',
        'created_at'
    ]
    list_filter = [
        'source_organization',
        'mapping_type',
        'is_active',
        'validated_by',
        'created_at'
    ]
    search_fields = [
        'catalog_property_label',
        'source_property_pattern',
        'catalog_property_uri',
        'notes'
    ]
    ordering = ['-priority', 'catalog_property_label']
    
    fieldsets = [
        ('Basic Information', {
            'fields': [
                'source_organization',
                'catalog_property_label',
                'catalog_property_uri'
            ]
        }),
        ('Mapping Configuration', {
            'fields': [
                'source_property_pattern',
                'mapping_type',
                'priority'
            ]
        }),
        ('Status & Validation', {
            'fields': [
                'is_active',
                'validated_by',
                'validated_at',
                'notes'
            ]
        }),
        ('Metadata', {
            'fields': [
                'created_at',
                'updated_at',
                'created_by',
                'updated_by'
            ],
            'classes': ['collapse']
        })
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'created_by',
        'updated_by',
        'validated_at'
    ]
    
    def validated_status(self, obj):
        """Display validation status with color coding."""
        if obj.validated_by:
            return format_html(
                '<span style="color: green;">✓ Validated</span>'
            )
        else:
            return format_html(
                '<span style="color: orange;">⚠ Pending</span>'
            )
    validated_status.short_description = 'Validation Status'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'source_organization',
            'validated_by',
            'created_by'
        )
    
    def save_model(self, request, obj, form, change):
        if not change:  # Creating new object
            obj.created_by = request.user
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(HarmonizationExecution)
class HarmonizationExecutionAdmin(admin.ModelAdmin):
    list_display = [
        'id',
        'status',
        'execution_mode',
        'organizations_list',
        'resources_processed',
        'triples_created',
        'conflicts_resolved',
        'duration_display',
        'started_at'
    ]
    list_filter = [
        'status',
        'execution_mode',
        'started_at',
        'organizations'
    ]
    search_fields = [
        'id',
        'organizations__name'
    ]
    ordering = ['-started_at']
    
    fieldsets = [
        ('Execution Details', {
            'fields': [
                'status',
                'execution_mode',
                'started_at',
                'completed_at',
                'duration_seconds'
            ]
        }),
        ('Scope', {
            'fields': [
                'organizations',
                'rules_applied'
            ]
        }),
        ('Results', {
            'fields': [
                'resources_processed',
                'triples_created',
                'conflicts_resolved',
                'errors_display'
            ]
        }),
        ('Metadata', {
            'fields': [
                'created_at',
                'updated_at',
                'created_by'
            ],
            'classes': ['collapse']
        })
    ]
    
    readonly_fields = [
        'started_at',
        'completed_at',
        'duration_seconds',
        'created_at',
        'updated_at',
        'errors_display'
    ]
    
    filter_horizontal = ['organizations', 'rules_applied']
    
    def organizations_list(self, obj):
        """Display list of organizations."""
        orgs = obj.organizations.all()[:3]  # Show first 3
        if len(orgs) == 0:
            return "None"
        
        org_names = [org.name for org in orgs]
        if obj.organizations.count() > 3:
            org_names.append(f"... +{obj.organizations.count() - 3} more")
        
        return ", ".join(org_names)
    organizations_list.short_description = 'Organizations'
    
    def duration_display(self, obj):
        """Display execution duration in human-readable format."""
        if not obj.duration_seconds:
            return "N/A"
        
        duration = obj.duration_seconds
        if duration < 60:
            return f"{duration}s"
        elif duration < 3600:
            return f"{duration // 60}m {duration % 60}s"
        else:
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            return f"{hours}h {minutes}m"
    duration_display.short_description = 'Duration'
    
    def errors_display(self, obj):
        """Display errors in a readable format."""
        if not obj.errors:
            return "No errors"
        
        error_count = len(obj.errors)
        if error_count == 1:
            return format_html(
                '<span style="color: red;">{} error</span>',
                error_count
            )
        else:
            return format_html(
                '<span style="color: red;">{} errors</span>',
                error_count
            )
    errors_display.short_description = 'Errors'
    
    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related(
            'organizations',
            'rules_applied'
        ).select_related('created_by')


@admin.register(HarmonizationConflict)
class HarmonizationConflictAdmin(admin.ModelAdmin):
    list_display = [
        'source_resource_uri',
        'execution',
        'resolution',
        'conflicting_rules_count',
        'selected_rule',
        'resolved_by',
        'created_at'
    ]
    list_filter = [
        'resolution',
        'resolved_by',
        'created_at',
        'execution__status'
    ]
    search_fields = [
        'source_resource_uri',
        'resolution_notes',
        'execution__id'
    ]
    ordering = ['-created_at']
    
    fieldsets = [
        ('Conflict Details', {
            'fields': [
                'execution',
                'source_resource_uri',
                'conflicting_rules'
            ]
        }),
        ('Resolution', {
            'fields': [
                'resolution',
                'selected_rule',
                'resolved_by',
                'resolved_at',
                'resolution_notes'
            ]
        }),
        ('Metadata', {
            'fields': [
                'created_at',
                'updated_at'
            ],
            'classes': ['collapse']
        })
    ]
    
    readonly_fields = [
        'created_at',
        'updated_at',
        'resolved_at'
    ]
    
    filter_horizontal = ['conflicting_rules']
    
    def conflicting_rules_count(self, obj):
        """Display number of conflicting rules."""
        count = obj.conflicting_rules.count()
        if count > 1:
            return format_html(
                '<span style="color: red;">{} rules</span>',
                count
            )
        else:
            return f"{count} rule"
    conflicting_rules_count.short_description = 'Conflicting Rules'
    
    def get_queryset(self, request):
        return super().get_queryset(request).select_related(
            'execution',
            'selected_rule',
            'resolved_by'
        ).prefetch_related('conflicting_rules')
    
    actions = ['resolve_by_priority', 'mark_as_skipped']
    
    def resolve_by_priority(self, request, queryset):
        """Admin action to resolve conflicts by priority."""
        from arkumu.metadata.services.harmonization import ConflictResolver
        
        resolver = ConflictResolver()
        resolved_count = 0
        
        for conflict in queryset.filter(resolution='pending'):
            if resolver.resolve_conflict(conflict, 'priority', request.user):
                resolved_count += 1
        
        self.message_user(
            request,
            f"Resolved {resolved_count} conflicts by priority."
        )
    resolve_by_priority.short_description = "Resolve selected conflicts by priority"
    
    def mark_as_skipped(self, request, queryset):
        """Admin action to mark conflicts as skipped."""
        from django.utils import timezone
        
        updated_count = queryset.filter(resolution='pending').update(
            resolution='skipped',
            resolved_by=request.user,
            resolved_at=timezone.now(),
            resolution_notes='Marked as skipped via admin action'
        )
        
        self.message_user(
            request,
            f"Marked {updated_count} conflicts as skipped."
        )
    mark_as_skipped.short_description = "Mark selected conflicts as skipped"