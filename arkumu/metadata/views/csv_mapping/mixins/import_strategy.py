"""
Import Strategy Mixins for CSV Mapping

Contains mixins for handling import configuration and strategy management:
- ImportStrategyMixin: Import configuration and strategy management functionality
"""

import logging

logger = logging.getLogger(__name__)


class ImportStrategyMixin:
    """
    Mixin for handling import strategy configuration and management.
    Provides methods for managing SmartBulkUpdaterPolars import strategies.
    """
    
    DEFAULT_IMPORT_STRATEGY = {
        'update_strategy': 'SKIP_EXISTING',
        'link_row_cells': True,
        'multi_value_threshold': 0.2,
        'create_resources_for_unmapped': True,
        'bulk_size': 1000,
        'validate_before_import': True,
    }
    
    def get_import_strategy(self, request, organization_id):
        """
        Get import strategy configuration from session.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            dict: Import strategy configuration
        """
        import_strategy_key = f"import_strategy_{organization_id}"
        return request.session.get(import_strategy_key, self.DEFAULT_IMPORT_STRATEGY.copy())
    
    def update_import_strategy(self, request, organization_id, strategy_updates):
        """
        Update import strategy configuration in session.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            strategy_updates (dict): Strategy configuration updates
        """
        import_strategy_key = f"import_strategy_{organization_id}"
        current_strategy = self.get_import_strategy(request, organization_id)
        current_strategy.update(strategy_updates)
        request.session[import_strategy_key] = current_strategy
        request.session.modified = True
        logger.info(f"IMPORT_STRATEGY_MIXIN: Updated import strategy for org={organization_id}: {strategy_updates}")
    
    def reset_import_strategy(self, request, organization_id):
        """
        Reset import strategy to defaults.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
        """
        import_strategy_key = f"import_strategy_{organization_id}"
        request.session[import_strategy_key] = self.DEFAULT_IMPORT_STRATEGY.copy()
        request.session.modified = True
        logger.info(f"IMPORT_STRATEGY_MIXIN: Reset import strategy to defaults for org={organization_id}")
    
    def validate_import_strategy(self, strategy):
        """
        Validate import strategy configuration.
        
        Args:
            strategy (dict): Import strategy configuration
            
        Returns:
            tuple: (is_valid, error_messages)
        """
        errors = []
        
        # Validate update strategy
        valid_update_strategies = ['SKIP_EXISTING', 'UPDATE_EXISTING', 'REPLACE_ALL']
        if strategy.get('update_strategy') not in valid_update_strategies:
            errors.append(f"Invalid update_strategy. Must be one of: {valid_update_strategies}")
        
        # Validate multi-value threshold
        threshold = strategy.get('multi_value_threshold')
        if threshold is not None:
            try:
                threshold_float = float(threshold)
                if not 0.0 <= threshold_float <= 1.0:
                    errors.append("multi_value_threshold must be between 0.0 and 1.0")
            except (ValueError, TypeError):
                errors.append("multi_value_threshold must be a number")
        
        # Validate bulk size
        bulk_size = strategy.get('bulk_size')
        if bulk_size is not None:
            try:
                bulk_size_int = int(bulk_size)
                if bulk_size_int <= 0:
                    errors.append("bulk_size must be a positive integer")
            except (ValueError, TypeError):
                errors.append("bulk_size must be an integer")
        
        return len(errors) == 0, errors
    
    def get_import_strategy_summary(self, request, organization_id):
        """
        Get a human-readable summary of the current import strategy.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            
        Returns:
            dict: Strategy summary with descriptions
        """
        strategy = self.get_import_strategy(request, organization_id)
        
        update_strategy_descriptions = {
            'SKIP_EXISTING': 'Skip rows that already exist',
            'UPDATE_EXISTING': 'Update existing rows with new data',
            'REPLACE_ALL': 'Replace all existing data'
        }
        
        return {
            'update_strategy': {
                'value': strategy.get('update_strategy'),
                'description': update_strategy_descriptions.get(strategy.get('update_strategy'), 'Unknown')
            },
            'link_row_cells': {
                'value': strategy.get('link_row_cells'),
                'description': 'Link cells within rows' if strategy.get('link_row_cells') else 'Do not link cells within rows'
            },
            'multi_value_threshold': {
                'value': strategy.get('multi_value_threshold'),
                'description': f"Treat as multi-value if >{strategy.get('multi_value_threshold', 0.2)*100}% of values contain separators"
            },
            'create_resources_for_unmapped': {
                'value': strategy.get('create_resources_for_unmapped'),
                'description': 'Create new resources for unmapped data' if strategy.get('create_resources_for_unmapped') else 'Skip unmapped data'
            },
            'bulk_size': {
                'value': strategy.get('bulk_size'),
                'description': f"Process in batches of {strategy.get('bulk_size', 1000)} rows"
            },
            'validate_before_import': {
                'value': strategy.get('validate_before_import'),
                'description': 'Validate data before importing' if strategy.get('validate_before_import') else 'Import without validation'
            }
        }
    
    def generate_smartbulkupdater_config(self, request, organization_id, selected_columns):
        """
        Generate configuration for SmartBulkUpdaterPolars based on current strategy and selected columns.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            selected_columns (list): List of selected column configurations
            
        Returns:
            dict: SmartBulkUpdaterPolars configuration
        """
        strategy = self.get_import_strategy(request, organization_id)
        
        # Extract column mappings
        column_mappings = []
        anchor_column = None
        
        for col in selected_columns:
            column_mapping = {
                'source_column': col['name'],
                'dataset': col['dataset'],
                'source': col['source'],
                'is_multi_value': col.get('is_multi_value', False),
                'data_type': col.get('type', 'string'),
            }
            
            if col.get('is_anchor', False):
                anchor_column = column_mapping
            
            if col.get('is_fk', False):
                column_mapping['is_foreign_key'] = True
                column_mapping['fk_config'] = col.get('fk_config', {})
            
            column_mappings.append(column_mapping)
        
        # Build SmartBulkUpdater configuration
        config = {
            'update_strategy': strategy['update_strategy'],
            'link_row_cells': strategy['link_row_cells'],
            'multi_value_threshold': strategy['multi_value_threshold'],
            'create_resources_for_unmapped': strategy['create_resources_for_unmapped'],
            'bulk_size': strategy['bulk_size'],
            'validate_before_import': strategy['validate_before_import'],
            'column_mappings': column_mappings,
            'anchor_column': anchor_column,
            'organization_id': organization_id,
        }
        
        return config 