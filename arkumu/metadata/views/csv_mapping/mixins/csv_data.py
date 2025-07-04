"""
CSV Data Mixins for CSV Mapping

Contains mixins for handling CSV dataset discovery, loading, and preview:
- CSVDataMixin: CSV dataset loading and preview functionality
"""

import logging
from django.core.serializers.json import DjangoJSONEncoder
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer

logger = logging.getLogger(__name__)


class CSVDataMixin:
    """
    Mixin for handling CSV dataset discovery, loading, and preview functionality.
    Provides methods for working with CSV files from S3 sources.
    """
    
    def get_csv_datasets_for_organization(self, organization_id):
        """
        Discover and return all CSV datasets for a given organization.
        
        OPTIMIZATION: Cache the dataset list to avoid repeated S3 scans.
        
        Args:
            organization_id (str): Organization ID to discover datasets for
            
        Returns:
            list: List of CSV dataset dictionaries with name, source, format
        """
        # Check cache first
        from django.core.cache import cache
        cache_key = f"csv_datasets:{organization_id}"
        cached_datasets = cache.get(cache_key)
        
        if cached_datasets is not None:
            logger.info(f"CSV_DATA_MIXIN: Using cached dataset list for organization '{organization_id}' ({len(cached_datasets)} datasets)")
            return cached_datasets
        
        logger.info(f"CSV_DATA_MIXIN: Discovering CSV datasets for organization '{organization_id}'")
        
        try:
            analyzer = S3DirectDataAnalyzer()
            sources = analyzer.discover_s3_data_sources(organization_id)
            
            csv_datasets = []
            for source in sources:
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                for dataset_name in dataset_names:
                    if self._is_csv_dataset(dataset_name, source):
                        csv_datasets.append({
                            'name': dataset_name,
                            'source': source.name,
                            'format': source.format or 'csv'
                        })
            
            logger.info(f"CSV_DATA_MIXIN: Found {len(csv_datasets)} CSV datasets")
            
            # Cache for 5 minutes
            cache.set(cache_key, csv_datasets, 300)
            
            return csv_datasets
            
        except Exception as e:
            logger.error(f"CSV_DATA_MIXIN: Error discovering CSV datasets: {e}")
            return []
    
    def _is_csv_dataset(self, dataset_name, source):
        """
        Check if a dataset is a CSV/parseable format.
        
        Args:
            dataset_name (str): Name of the dataset
            source: Source object with format information
            
        Returns:
            bool: True if dataset is CSV-compatible
        """
        dataset_lower = dataset_name.lower()
        return (dataset_lower.endswith(('.csv', '.tsv', '.txt')) or 
                'csv' in dataset_lower or 
                (source.format and source.format.lower() in ['csv', 'tsv', 'text']))
    
    def get_dataset_preview(self, source, dataset_name, limit=50):
        """
        Load preview data for a specific dataset.
        
        Args:
            source (str): Source name
            dataset_name (str): Dataset name
            limit (int): Number of rows to preview
            
        Returns:
            dict: Dataset preview data or None if error
        """
        logger.info(f"CSV_DATA_MIXIN: Loading preview for dataset='{dataset_name}', source='{source}'")
        
        try:
            analyzer = S3DirectDataAnalyzer()
            dataset_preview = analyzer.get_dataset_preview(source, dataset_name, limit=limit)
            logger.info(f"CSV_DATA_MIXIN: Successfully loaded preview for {dataset_name}")
            return dataset_preview
            
        except Exception as e:
            logger.error(f"CSV_DATA_MIXIN: Error loading dataset preview: {e}")
            return None
    
    def get_dataset_info_with_preview(self, source, dataset_name, organization_id, limit=50):
        """
        Get complete dataset information including preview and metadata.
        
        Args:
            source (str): Source name
            dataset_name (str): Dataset name
            organization_id (str): Organization ID
            limit (int): Number of rows to preview
            
        Returns:
            dict: Complete dataset information
        """
        dataset_preview = self.get_dataset_preview(source, dataset_name, limit)
        
        if dataset_preview is None:
            return None
            
        return {
            'name': dataset_name,
            'source': source,
            'preview': dataset_preview,
            'organization_id': organization_id,
        }
    
    def get_selected_datasets_with_details(self, request, organization_id, csv_datasets):
        """
        Get selected datasets with their detailed information.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            csv_datasets (list): List of available CSV datasets
            
        Returns:
            tuple: (selected_datasets, selected_datasets_with_details)
        """
        # Get selected datasets from session
        selected_datasets_key = f"selected_datasets_{organization_id}"
        selected_datasets = request.session.get(selected_datasets_key, [])
        
        # Get selected datasets with details, preserving selection order (newest first)
        selected_datasets_with_details = []
        for selected_name in selected_datasets:  # Iterate in selection order
            for dataset in csv_datasets:
                if dataset['name'] == selected_name:
                    selected_datasets_with_details.append(dataset)
                    break
        
        return selected_datasets, selected_datasets_with_details
    
    def update_selected_datasets(self, request, organization_id, selected_datasets):
        """
        Update selected datasets in session.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            selected_datasets (list): List of selected dataset names
        """
        selected_datasets_key = f"selected_datasets_{organization_id}"
        request.session[selected_datasets_key] = selected_datasets
        request.session.modified = True
        logger.info(f"CSV_DATA_MIXIN: Updated selected datasets for org={organization_id}: {selected_datasets}")
    
    def toggle_dataset_selection(self, request, organization_id, dataset_name):
        """
        Toggle selection of a dataset.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
            dataset_name (str): Dataset name to toggle
            
        Returns:
            tuple: (updated_selected_datasets, was_added)
        """
        selected_datasets_key = f"selected_datasets_{organization_id}"
        selected_datasets = request.session.get(selected_datasets_key, [])
        
        if dataset_name in selected_datasets:
            selected_datasets.remove(dataset_name)
            was_added = False
            logger.info(f"CSV_DATA_MIXIN: Removed {dataset_name} from selection")
        else:
            # Remove if already exists (move to front) and add to beginning for recency
            if dataset_name in selected_datasets:
                selected_datasets.remove(dataset_name)
            selected_datasets.insert(0, dataset_name)  # Add to front for most recent
            was_added = True
            logger.info(f"CSV_DATA_MIXIN: Added {dataset_name} to selection (moved to front)")
        
        self.update_selected_datasets(request, organization_id, selected_datasets)
        return selected_datasets, was_added
    
    def clear_selected_datasets(self, request, organization_id):
        """
        Clear all selected datasets.
        
        Args:
            request: Django request object
            organization_id (str): Organization ID
        """
        self.update_selected_datasets(request, organization_id, [])
        logger.info(f"CSV_DATA_MIXIN: Cleared all selected datasets for org={organization_id}") 