"""
Direct Data Views

Views that use S3DirectDataAnalyzer to provide fast table previews and analysis
directly from S3 source files, without requiring data to be imported into the database first.

This approach is more memory-efficient and faster than the traditional database-based approach.
"""

import logging
import json
import tempfile
import os
import re
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseBadRequest, HttpResponse
from django.conf import settings
from django.core.cache import cache

from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.metadata.services.relationship_discovery.service import RelationshipDiscoveryService

logger = logging.getLogger(__name__)


def get_organization_id_from_request(request):
    """Get the organization ID from the request (following the same pattern as other views)."""
    # Extract organization from GET or POST parameters, following the same pattern as other views
    organization = request.GET.get('organization') or request.POST.get('organization')
    
    # Handle both cases where organization might be passed
    if organization:
        return organization.strip()
    
    # Fallback: try to get from user if available (for future authentication integration)
    if hasattr(request, 'user') and hasattr(request.user, 'organization_id'):
        return getattr(request.user, 'organization_id', None)
    
    # Default fallback - you may want to raise an exception here instead
    return 'default-org'


@login_required
def direct_split_table_graph_view(request):
    """
    Split view showing datasets directly from S3 source files with table previews and graph visualization.
    Uses S3DirectDataAnalyzer for efficient S3-based analysis.
    """
    try:
        organization_id = get_organization_id_from_request(request)
        
        # Discover available organizations from S3 buckets (like archivist dashboard)
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        
        # If no organization is provided, show helpful instructions with available orgs
        if not organization_id or organization_id == 'default-org':
            context = {
                'sources': [],
                'selected_source': '',
                'is_direct_mode': True,
                'organizations': available_organizations,
                'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL (e.g., ?organization=rsh)',
                'show_organization_help': True
            }
            return render(request, 'direct_split_table_graph.html', context)
        
        # Check if the selected organization actually exists in S3
        org_exists = any(org['id'] == organization_id for org in available_organizations)
        if not org_exists:
            context = {
                'sources': [],
                'selected_source': '',
                'is_direct_mode': True,
                'organizations': available_organizations,
                'organization_id': organization_id,
                'error': f'Organization "{organization_id}" not found in S3. Available organizations: {", ".join([org["id"] for org in available_organizations])}'
            }
            return render(request, 'direct_split_table_graph.html', context)
        
        # Discover available data sources from S3 for this organization
        sources = analyzer.discover_s3_data_sources(organization_id)
        
        # Format sources for dropdown and collect CSV datasets
        sources_info = []
        csv_datasets = []
        
        for source in sources:
            dataset_names = analyzer.get_dataset_names_from_s3_source(source)
            logger.info(f"Source: {source.name}, Format: {source.format}, Datasets: {dataset_names}")
            
            # Collect CSV/parseable datasets from this source
            source_csv_datasets = []
            for dataset_name in dataset_names:
                dataset_lower = dataset_name.lower()
                if (dataset_lower.endswith(('.csv', '.tsv', '.txt')) or 
                    'csv' in dataset_lower or 
                    (source.format and source.format.lower() in ['csv', 'tsv', 'text'])):
                    csv_dataset = {
                        'name': dataset_name,
                        'source': source.name,
                        'format': source.format or 'csv'
                    }
                    csv_datasets.append(csv_dataset)
                    source_csv_datasets.append(csv_dataset)
                    logger.info(f"Added CSV dataset: {dataset_name} from source {source.name} (format: {source.format})")
            
            # Only add source to dropdown if it has CSV datasets
            if source_csv_datasets:
                sources_info.append({
                    'name': source.name,
                    'dataset_count': len(source_csv_datasets),
                    'display_name': source.name,
                    'format': source.format,
                    'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                    'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                })
        
        logger.info(f"Found {len(csv_datasets)} CSV datasets total: {[d['name'] for d in csv_datasets]}")
        
        context = {
            'sources': sources_info,
            'datasets': csv_datasets,  # Add CSV datasets to context
            'selected_source': request.GET.get('source', ''),
            'is_direct_mode': True,  # Flag to indicate we're using direct mode
            'organizations': available_organizations,
            'organization_id': organization_id,  # Include organization in context
        }
        
        return render(request, 'direct_split_table_graph.html', context)
        
    except Exception as e:
        logger.error(f"Error in direct_split_table_graph_view: {e}")
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        context = {
            'sources': [],
            'selected_source': '',
            'error': f"Error loading data sources: {str(e)}",
            'is_direct_mode': True,
            'organizations': available_organizations,
        }
        return render(request, 'direct_split_table_graph.html', context)


@login_required
def direct_load_source_data(request):
    """
    HTMX endpoint to load source data directly from S3 files using S3DirectDataAnalyzer.
    Provides fast previews without database import.
    """
    source_name = request.GET.get('source', '')
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"DIRECT LOAD: Loading data for source={source_name}, org={organization_id}")
    
    if not source_name:
        empty_response = render(request, 'partials/empty_state.html')
        empty_response['HX-Trigger'] = 'sourceDataLoaded'
        return empty_response
    
    if not organization_id or organization_id == 'default-org':
        error_response = render(request, 'partials/empty_state.html', {
            'error': "Organization parameter required. Please add ?organization=YOUR_ORG to the URL."
        })
        return error_response
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Get source summary with all datasets from S3
        logger.info(f"DIRECT LOAD: Getting source summary for {source_name}")
        source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
        logger.info(f"DIRECT LOAD: Source summary: {len(source_summary.get('datasets', []))} datasets found")
        
        # Build datasets information for table display
        datasets_data = []
        for dataset_info in source_summary['datasets']:
            if 'error' not in dataset_info:
                logger.info(f"DIRECT LOAD: Processing dataset {dataset_info['name']}: {dataset_info['row_count']} rows, {dataset_info['column_count']} cols")
                datasets_data.append({
                    'name': dataset_info['name'],
                    'source': source_name,
                    'cell_count': dataset_info['row_count'] * dataset_info['column_count'],
                    'row_count': dataset_info['row_count'],
                    'column_count': dataset_info['column_count'],
                    'preview': {
                        'colHeaders': dataset_info['columns'],
                        'data': dataset_info['sample_data'],
                        'showing_rows': len(dataset_info['sample_data']),
                        'total_rows': dataset_info['row_count'],
                        'has_more': dataset_info['row_count'] > len(dataset_info['sample_data']),
                        'offset': 0
                    },
                    'multi_value_columns': dataset_info.get('multi_value_columns', [])
                })
            else:
                logger.error(f"DIRECT LOAD: Dataset {dataset_info.get('name', 'unknown')} has error: {dataset_info.get('error')}")
        
        logger.info(f"DIRECT LOAD: Built {len(datasets_data)} dataset entries for display")
        
        # Generate simplified graph data for direct mode
        # Note: Full relationship analysis is expensive, so we provide basic structure
        graph_data = _build_direct_graph_data(source_summary)
        
        cached_data = {
            'source': source_name,
            'datasets': datasets_data,
            'graph_data': graph_data,
            'is_direct_mode': True,
            'source_info': source_summary['source_info'],
            'organization_id': organization_id  # Add organization to context
        }
        
        response = render(request, 'partials/source_data.html', cached_data)
        response['HX-Trigger'] = 'sourceDataLoaded'
        return response
        
    except Exception as e:
        logger.error(f"DIRECT LOAD: Error loading source data: {e}", exc_info=True)
        
        error_response = render(request, 'partials/empty_state.html', {
            'error': f"Error loading source data: {str(e)}"
        })
        return error_response


@login_required
def direct_load_all_datasets(request):
    """
    HTMX endpoint to load all available datasets from S3 for the dataset browser.
    Provides lazy loading of dataset cards for browsing.
    """
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"DIRECT LOAD ALL DATASETS: Loading all datasets for org={organization_id}")
    
    if not organization_id or organization_id == 'default-org':
        return render(request, 'partials/datasets_grid.html', {
            'error': "Organization parameter required. Please add ?organization=YOUR_ORG to the URL.",
            'datasets': []
        })
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Discover all data sources from S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        logger.info(f"DIRECT LOAD ALL DATASETS: Found {len(sources)} sources")
        
        # Build datasets information from all sources
        all_datasets = []
        
        for source in sources:
            try:
                # Get dataset names for this source
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                logger.info(f"DIRECT LOAD ALL DATASETS: Source {source.name} has {len(dataset_names)} datasets")
                
                for dataset_name in dataset_names:
                    try:
                        # Get basic preview for each dataset (limited for performance)
                        preview = analyzer.get_s3_table_preview(source, dataset_name, limit=3)
                        
                        dataset_info = {
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'row_count': preview.total_rows,
                            'column_count': len(preview.column_headers),
                            'cell_count': preview.total_rows * len(preview.column_headers),
                            'preview': {
                                'colHeaders': preview.column_headers[:5],  # Show first 5 columns
                                'data': preview.data_rows,
                                'showing_rows': preview.showing_rows,
                                'total_rows': preview.total_rows,
                                'has_more': preview.has_more,
                                'offset': 0
                            },
                            'file_info': {
                                'format': source.format,
                                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                            },
                            'multi_value_columns': preview.multi_value_columns[:3],  # Show first 3
                            'column_types': getattr(preview, 'column_types', {})
                        }
                        
                        all_datasets.append(dataset_info)
                        
                    except Exception as dataset_error:
                        logger.warning(f"DIRECT LOAD ALL DATASETS: Error loading dataset {dataset_name} from {source.name}: {dataset_error}")
                        # Add error entry
                        all_datasets.append({
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'error': str(dataset_error),
                            'row_count': 0,
                            'column_count': 0,
                            'cell_count': 0
                        })
                        continue
                        
            except Exception as source_error:
                logger.error(f"DIRECT LOAD ALL DATASETS: Error processing source {source.name}: {source_error}")
                continue
        
        logger.info(f"DIRECT LOAD ALL DATASETS: Built {len(all_datasets)} dataset entries")
        
        return render(request, 'partials/datasets_grid.html', {
            'datasets': all_datasets,
            'organization_id': organization_id,
            'total_datasets': len(all_datasets),
            'sources_count': len(sources)
        })
        
    except Exception as e:
        logger.error(f"DIRECT LOAD ALL DATASETS: Error loading all datasets: {e}", exc_info=True)
        
        return render(request, 'partials/datasets_grid.html', {
            'error': f"Error loading datasets: {str(e)}",
            'datasets': []
        })


@login_required
def direct_get_dataset_card(request):
    """Get a dataset card with preview using direct S3 file analysis."""
    source_name = request.GET.get('source', '')
    dataset_name = request.GET.get('dataset_name', '')
    organization_id = get_organization_id_from_request(request)

    logger.info(f"🎯 DATASET CARD REQUEST: source={source_name}, dataset={dataset_name}, org={organization_id}")
    logger.info(f"🎯 DATASET CARD REQUEST: All GET params: {dict(request.GET)}")

    if not source_name or not dataset_name:
        logger.error(f"🎯 DATASET CARD ERROR: Missing parameters - source={source_name}, dataset={dataset_name}")
        return HttpResponseBadRequest("Missing source or dataset_name")

    if not organization_id or organization_id == 'default-org':
        logger.error(f"🎯 DATASET CARD ERROR: Invalid organization - {organization_id}")
        return HttpResponseBadRequest("Organization parameter required")

    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        logger.info(f"🎯 DATASET CARD: Discovering sources for org {organization_id}")
        sources = analyzer.discover_s3_data_sources(organization_id)
        logger.info(f"🎯 DATASET CARD: Found {len(sources)} sources: {[s.name for s in sources]}")
        
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            logger.error(f"🎯 DATASET CARD ERROR: Source '{source_name}' not found in available sources: {[s.name for s in sources]}")
            return HttpResponseBadRequest(f"Source '{source_name}' not found")
        
        # Get detailed preview for this dataset from S3
        logger.info(f"🎯 DATASET CARD: Getting preview for {dataset_name} from source {source_name}")
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=10)
        logger.info(f"🎯 DATASET CARD: Preview loaded - {preview.total_rows} rows, {len(preview.column_headers)} columns")
        
        dataset = {
            'name': dataset_name,
            'source': source_name,
            'cell_count': preview.total_rows * len(preview.column_headers),
            'row_count': preview.total_rows,
            'column_count': len(preview.column_headers),
            'preview': {
                'colHeaders': preview.column_headers,
                'data': preview.data_rows,
                'showing_rows': preview.showing_rows,
                'total_rows': preview.total_rows,
                'has_more': preview.has_more,
                'offset': preview.offset
            },
            'column_types': preview.column_types,
            'multi_value_columns': preview.multi_value_columns
        }

        logger.info(f"🎯 DATASET CARD: Rendering template with dataset {dataset_name}")
        response = render(request, 'partials/dataset_card.html', {
            'dataset': dataset,
            'colHeaders': preview.column_headers,
            'rowIds': [f"row_{i}" for i in range(len(preview.data_rows))],  # Generate row IDs
            'source': source_name,
            'is_direct_mode': True,
            'organization_id': organization_id  # Add organization to context
        })
        logger.info(f"🎯 DATASET CARD SUCCESS: Template rendered for {dataset_name}")
        return response
        
    except Exception as e:
        logger.error(f"🎯 DATASET CARD ERROR: Exception getting dataset card: {e}", exc_info=True)
        return HttpResponseBadRequest(f"Error: {str(e)}")


@login_required
def direct_load_more_dataset_rows(request):
    """Load more rows using S3DirectDataAnalyzer pagination."""
    logger.info("=== LOAD MORE ROWS VIEW CALLED ===")
    logger.info(f"Request method: {request.method}")
    logger.info(f"Request path: {request.path}")
    logger.info(f"Request GET params: {dict(request.GET)}")
    logger.info(f"Request headers: {dict(request.headers)}")
    
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    offset = int(request.GET.get('offset', 0))
    limit = int(request.GET.get('limit', 20))
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"Parsed params - source: {source_name}, dataset: {dataset_name}, offset: {offset}, limit: {limit}, org: {organization_id}")
    
    if not source_name or not dataset_name:
        return render(request, 'partials/table_rows.html', {'data': []})
    
    if not organization_id or organization_id == 'default-org':
        return render(request, 'partials/table_rows.html', {'data': []})
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return render(request, 'partials/table_rows.html', {'data': []})
        
        # Get the requested slice from S3
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, offset=offset, limit=limit)
        
        return render(request, 'partials/load_more_response.html', {
            'data': preview.data_rows,
            'colHeaders': preview.column_headers,
            'rowIds': [f"row_{offset + i}" for i in range(len(preview.data_rows))],
            'source': source_name,
            'dataset': dataset_name,
            'preview': {
                'showing_rows': offset + len(preview.data_rows),  # Total rows shown so far
                'total_rows': preview.total_rows,
                'has_more': preview.has_more,
                'offset': offset + len(preview.data_rows)  # Next offset
            },
            'is_direct_mode': True,
            'organization_id': organization_id  # Add organization to context
        })
        
    except Exception as e:
        logger.error(f"Error loading more rows: {e}")
        return render(request, 'partials/table_rows.html', {'data': []})


@login_required
def direct_analyze_dataset_relationships(request):
    """
    Analyze relationships in a dataset using direct S3 file analysis.
    More expensive operation that includes full relationship discovery.
    """
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    organization_id = get_organization_id_from_request(request)
    
    if not source_name or not dataset_name:
        return JsonResponse({'error': 'Missing source or dataset parameters'}, status=400)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return JsonResponse({'error': f"Source '{source_name}' not found"}, status=404)
        
        # Perform complete analysis including relationships
        analysis = analyzer.analyze_s3_dataset_completely(
            source_info, 
            dataset_name, 
            include_relationships=True
        )
        
        # Format for JSON response
        result = {
            'dataset_name': dataset_name,
            'source_name': source_name,
            'analysis': {
                'row_count': analysis.row_count,
                'column_count': analysis.column_count,
                'column_types': analysis.column_types,
                'data_quality': analysis.data_quality_metrics,
                'suggested_strategy': analysis.suggested_import_strategy,
                'multi_value_analysis': analysis.multi_value_analysis
            }
        }
        
        # Include relationship analysis if available
        if analysis.relationship_analysis:
            result['relationships'] = analysis.relationship_analysis
        
        return JsonResponse(result)
        
    except Exception as e:
        logger.error(f"Error analyzing dataset relationships: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def direct_get_import_preview(request):
    """
    Get a preview of what would happen if we imported this S3 dataset.
    Uses SmartBulkUpdater's analysis capabilities.
    """
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    organization_id = get_organization_id_from_request(request)
    
    if not source_name or not dataset_name:
        return JsonResponse({'error': 'Missing parameters'}, status=400)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Use the S3 import preview method
        import_preview = analyzer.get_s3_import_preview(organization_id, source_name, dataset_name)
        
        return JsonResponse(import_preview)
        
    except Exception as e:
        logger.error(f"Error getting import preview: {e}")
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def direct_analyze_column(request):
    """
    Analyze a specific column from a dataset using direct S3 file analysis.
    Provides data profiling, pattern detection, and linking suggestions.
    """
    source_name = request.GET.get('source')
    dataset_name = request.GET.get('dataset')
    column_name = request.GET.get('column')
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"Column analysis request: source={source_name}, dataset={dataset_name}, column={column_name}, org={organization_id}")
    
    if not source_name or not dataset_name or not column_name:
        return HttpResponseBadRequest("Missing required parameters: source, dataset, and column")
    
    if not organization_id or organization_id == 'default-org':
        return HttpResponseBadRequest("Organization parameter required")
    
    try:
        analyzer = S3DirectDataAnalyzer()
        
        # Find the source in S3
        sources = analyzer.discover_s3_data_sources(organization_id)
        source_info = next((s for s in sources if s.name == source_name), None)
        
        if not source_info:
            return HttpResponseBadRequest(f"Source '{source_name}' not found")
        
        # Get column data and analysis
        preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=100)
        
        # Find column index
        try:
            column_index = preview.column_headers.index(column_name)
        except ValueError:
            return HttpResponseBadRequest(f"Column '{column_name}' not found in dataset")
        
        # Get full dataset for relationship analysis
        full_preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=1000)  # Larger sample for better analysis
        
        # Create temporary CSV file for relationship analysis
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
            # Write headers
            temp_file.write(','.join(full_preview.column_headers) + '\n')
            # Write data rows
            for row in full_preview.data_rows:
                # Ensure all rows have the same number of columns
                padded_row = row + [None] * (len(full_preview.column_headers) - len(row))
                row_str = ','.join([f'"{str(cell).replace('"', '""')}"' if cell is not None else '' for cell in padded_row])
                temp_file.write(row_str + '\n')
            temp_csv_path = temp_file.name
        
        try:
            # Use relationship discovery service for sophisticated analysis
            relationship_service = RelationshipDiscoveryService()
            dataset_analysis = relationship_service.analyze_dataset_relationships(temp_csv_path, sample_size=1000)
            
            # Extract column values for basic analysis
            column_values = [row[column_index] if column_index < len(row) else None for row in preview.data_rows]
            
            # Combine basic analysis with relationship insights
            basic_analysis = _analyze_column_data(column_name, column_values, preview.total_rows)
            relationship_insights = _extract_column_relationship_insights(column_name, dataset_analysis)
            
            # Merge analyses
            analysis = {**basic_analysis, **relationship_insights}
            
            # Add dataset context
            analysis['dataset_info'] = {
                'name': dataset_name,
                'source': source_name,
                'total_rows': preview.total_rows,
                'total_columns': len(preview.column_headers),
                'column_index': column_index
            }
            
        finally:
            # Clean up temporary file
            try:
                os.unlink(temp_csv_path)
            except Exception as cleanup_error:
                logger.warning(f"Could not clean up temp file: {cleanup_error}")
        
        # Render the analysis partial
        return render(request, 'partials/column_analysis.html', {
            'analysis': analysis,
            'column_name': column_name,
            'dataset_name': dataset_name,
            'source_name': source_name,
            'organization_id': organization_id
        })
        
    except Exception as e:
        logger.error(f"Error analyzing column: {e}", exc_info=True)
        return render(request, 'partials/column_analysis.html', {
            'error': f"Error analyzing column: {str(e)}",
            'column_name': column_name,
            'dataset_name': dataset_name,
            'source_name': source_name
        })


def _discover_available_organizations(analyzer):
    """
    Discover available organizations by checking S3 buckets.
    Similar to how archivist dashboard works.
    """
    try:
        # Standard organization list (same as archivist dashboard)
        standard_orgs = [
            {'id': 'rsh', 'name': 'Robert Schumann Hochschule Düsseldorf', 'status': 'unknown'},
            {'id': 'khm', 'name': 'Kunsthochschule für Medien Köln', 'status': 'unknown'},
            {'id': 'fuk', 'name': 'Folkwang Universität der Künste', 'status': 'unknown'},
            {'id': 'hmt', 'name': 'Hochschule für Musik und Tanz Köln', 'status': 'unknown'},
            {'id': 'det', 'name': 'Hochschule für Musik Detmold', 'status': 'unknown'},
        ]
        
        # Check which organizations actually have S3 data
        for org in standard_orgs:
            try:
                # Try to discover sources for this organization
                sources = analyzer.discover_s3_data_sources(org['id'])
                if sources:  # If sources found, mark as active
                    org['status'] = 'active'
                else:
                    org['status'] = 'inactive'
            except Exception as e:
                logger.debug(f"Organization {org['id']} check failed: {e}")
                org['status'] = 'inactive'
        
        return standard_orgs
        
    except Exception as e:
        logger.error(f"Error discovering organizations: {e}")
        # Return standard list with unknown status if discovery fails
        return [
            {'id': 'rsh', 'name': 'Robert Schumann Hochschule Düsseldorf', 'status': 'unknown'},
            {'id': 'khm', 'name': 'Kunsthochschule für Medien Köln', 'status': 'unknown'},
            {'id': 'fuk', 'name': 'Folkwang Universität der Künste', 'status': 'unknown'},
            {'id': 'hmt', 'name': 'Hochschule für Musik und Tanz Köln', 'status': 'unknown'},
            {'id': 'det', 'name': 'Hochschule für Musik Detmold', 'status': 'unknown'},
        ]


def _load_all_csv_datasets_data(analyzer, organization_id, sources, csv_datasets):
    """
    Load table data for all CSV datasets from all sources.
    Similar to direct_load_source_data but for all sources at once.
    """
    all_datasets_data = []
    
    # Group datasets by source for efficient loading
    datasets_by_source = {}
    for dataset in csv_datasets:
        source_name = dataset['source']
        if source_name not in datasets_by_source:
            datasets_by_source[source_name] = []
        datasets_by_source[source_name].append(dataset)
    
    # Load data for each source
    for source_name, source_datasets in datasets_by_source.items():
        try:
            logger.info(f"Loading data for source: {source_name} with {len(source_datasets)} datasets")
            
            # Get source summary for this source
            source_summary = analyzer.get_s3_source_summary(organization_id, source_name)
            
            # Build datasets information for table display
            for dataset_info in source_summary['datasets']:
                if 'error' not in dataset_info:
                    # Check if this dataset is in our CSV list
                    if any(d['name'] == dataset_info['name'] for d in source_datasets):
                        logger.info(f"Adding dataset {dataset_info['name']}: {dataset_info['row_count']} rows, {dataset_info['column_count']} cols")
                        all_datasets_data.append({
                            'name': dataset_info['name'],
                            'source': source_name,
                            'cell_count': dataset_info['row_count'] * dataset_info['column_count'],
                            'row_count': dataset_info['row_count'],
                            'column_count': dataset_info['column_count'],
                            'preview': {
                                'colHeaders': dataset_info['columns'],
                                'data': dataset_info['sample_data'],
                                'showing_rows': len(dataset_info['sample_data']),
                                'total_rows': dataset_info['row_count'],
                                'has_more': dataset_info['row_count'] > len(dataset_info['sample_data']),
                                'offset': 0
                            },
                            'multi_value_columns': dataset_info.get('multi_value_columns', [])
                        })
                else:
                    logger.error(f"Dataset {dataset_info.get('name', 'unknown')} has error: {dataset_info.get('error')}")
        
        except Exception as source_error:
            logger.error(f"Error loading source {source_name}: {source_error}")
            continue
    
    logger.info(f"Loaded {len(all_datasets_data)} datasets total for table display")
    return all_datasets_data


def _build_direct_graph_data(source_summary):
    """
    Build basic graph data from source summary for visualization.
    This provides structural information without expensive relationship analysis.
    """
    nodes = []
    links = []
    
    # Add source node
    source_info = source_summary['source_info']
    nodes.append({
        'id': f"source_{source_info.name}",
        'label': source_info.name,
        'type': 'source',
        'level': 0,
        'color': '#3B82F6',  # Blue for sources
        'size': 30
    })
    
    # Add dataset nodes and basic column nodes
    for i, dataset in enumerate(source_summary['datasets']):
        if 'error' in dataset:
            continue
            
        # Dataset node
        dataset_id = f"dataset_{dataset['name']}"
        nodes.append({
            'id': dataset_id,
            'label': dataset['name'],
            'type': 'dataset',
            'level': 1,
            'color': '#10B981',  # Green for datasets
            'size': 25,
            'row_count': dataset['row_count'],
            'column_count': dataset['column_count']
        })
        
        # Link source to dataset
        links.append({
            'from': f"source_{source_info.name}",
            'to': dataset_id,
            'type': 'contains'
        })
        
        # Add some column nodes (limit to avoid overwhelming the graph)
        for j, column in enumerate(dataset['columns'][:10]):  # Max 10 columns per dataset
            column_id = f"column_{dataset['name']}_{column}"
            nodes.append({
                'id': column_id,
                'label': column,
                'type': 'column',
                'level': 2,
                'color': '#F59E0B',  # Orange for columns
                'size': 15,
                'is_multi_value': column in dataset.get('multi_value_columns', [])
            })
            
            # Link dataset to column
            links.append({
                'from': dataset_id,
                'to': column_id,
                'type': 'has_column'
            })
    
    return {
        'nodes': json.dumps(nodes),
        'links': json.dumps(links),
        'source': source_info.name,
        'dataset_count': len([d for d in source_summary['datasets'] if 'error' not in d]),
        'total_nodes': len(nodes),
        'total_links': len(links),
        'is_direct_mode': True
    }


def _analyze_column_data(column_name, column_values, total_rows):
    """
    Analyze column data to provide insights for linking and preprocessing.
    """
    import re
    from collections import Counter, defaultdict
    
    # Filter out None/empty values
    non_empty_values = [str(v).strip() for v in column_values if v is not None and str(v).strip()]
    
    # Basic statistics
    total_values = len(column_values)
    non_empty_count = len(non_empty_values)
    empty_count = total_values - non_empty_count
    fill_rate = (non_empty_count / total_values) * 100 if total_values > 0 else 0
    
    # Value frequency analysis
    value_counts = Counter(non_empty_values)
    unique_count = len(value_counts)
    most_common = value_counts.most_common(10)
    
    # Data type detection
    data_type = _detect_data_type(non_empty_values)
    
    # Pattern analysis
    patterns = _analyze_patterns(non_empty_values)
    
    # Multi-value detection (values that might need splitting)
    multi_value_analysis = _analyze_multi_values(non_empty_values)
    
    # Linking suggestions
    linking_suggestions = _generate_linking_suggestions(column_name, non_empty_values, data_type)
    
    # Data quality issues
    quality_issues = _detect_quality_issues(non_empty_values, patterns)
    
    return {
        'basic_stats': {
            'total_values': total_values,
            'non_empty_count': non_empty_count,
            'empty_count': empty_count,
            'fill_rate': round(fill_rate, 1),
            'unique_count': unique_count,
            'duplicate_rate': round(((non_empty_count - unique_count) / non_empty_count) * 100, 1) if non_empty_count > 0 else 0
        },
        'data_type': data_type,
        'value_distribution': {
            'most_common': most_common[:5],
            'sample_values': non_empty_values[:10] if non_empty_values else []
        },
        'patterns': patterns,
        'multi_value_analysis': multi_value_analysis,
        'linking_suggestions': linking_suggestions,
        'quality_issues': quality_issues,
        'preprocessing_recommendations': _generate_preprocessing_recommendations(patterns, multi_value_analysis, quality_issues)
    }


def _detect_data_type(values):
    """Detect the primary data type of the column values."""
    if not values:
        return {'type': 'empty', 'confidence': 100}
    
    type_counts = {'integer': 0, 'float': 0, 'date': 0, 'url': 0, 'email': 0, 'text': 0}
    
    for value in values[:50]:  # Sample first 50 values for performance
        # Integer check
        if re.match(r'^-?\d+$', value):
            type_counts['integer'] += 1
        # Float check
        elif re.match(r'^-?\d+\.\d+$', value):
            type_counts['float'] += 1
        # Date check (basic patterns)
        elif re.match(r'\d{4}-\d{2}-\d{2}', value) or re.match(r'\d{2}/\d{2}/\d{4}', value):
            type_counts['date'] += 1
        # URL check
        elif re.match(r'https?://', value):
            type_counts['url'] += 1
        # Email check
        elif re.match(r'\S+@\S+\.\S+', value):
            type_counts['email'] += 1
        else:
            type_counts['text'] += 1
    
    # Determine primary type
    total_checked = sum(type_counts.values())
    if total_checked == 0:
        return {'type': 'empty', 'confidence': 100}
    
    primary_type = max(type_counts.keys(), key=lambda k: type_counts[k])
    confidence = round((type_counts[primary_type] / total_checked) * 100, 1)
    
    return {'type': primary_type, 'confidence': confidence, 'distribution': type_counts}


def _analyze_patterns(values):
    """Analyze common patterns in the values."""
    if not values:
        return {}
    
    # Length analysis
    lengths = [len(v) for v in values]
    
    # Common separators
    separators = {';': 0, ',': 0, '|': 0, '/': 0, '-': 0, ':': 0}
    for value in values:
        for sep in separators:
            if sep in value:
                separators[sep] += 1
    
    # Character patterns
    has_numbers = sum(1 for v in values if re.search(r'\d', v))
    has_special_chars = sum(1 for v in values if re.search(r'[^a-zA-Z0-9\s]', v))
    
    return {
        'length_stats': {
            'min': min(lengths) if lengths else 0,
            'max': max(lengths) if lengths else 0,
            'avg': round(sum(lengths) / len(lengths), 1) if lengths else 0
        },
        'common_separators': {k: v for k, v in separators.items() if v > 0},
        'character_analysis': {
            'has_numbers': has_numbers,
            'has_special_chars': has_special_chars,
            'numeric_percentage': round((has_numbers / len(values)) * 100, 1),
            'special_char_percentage': round((has_special_chars / len(values)) * 100, 1)
        }
    }


def _analyze_multi_values(values):
    """Detect if values contain multiple sub-values that might need splitting."""
    if not values:
        return {'needs_splitting': False}
    
    separators = [';', ',', '|', '/', ' and ', ' & ', ' + ']
    separator_analysis = {}
    
    for sep in separators:
        split_counts = []
        for value in values[:20]:  # Sample for performance
            if sep in value:
                parts = value.split(sep)
                if len(parts) > 1:
                    split_counts.append(len(parts))
        
        if split_counts:
            separator_analysis[sep] = {
                'occurrence_count': len(split_counts),
                'avg_splits': round(sum(split_counts) / len(split_counts), 1),
                'max_splits': max(split_counts)
            }
    
    # Determine if splitting is recommended
    needs_splitting = False
    recommended_separator = None
    
    for sep, analysis in separator_analysis.items():
        if analysis['occurrence_count'] > len(values) * 0.1:  # 10% threshold
            needs_splitting = True
            if not recommended_separator or analysis['occurrence_count'] > separator_analysis[recommended_separator]['occurrence_count']:
                recommended_separator = sep
    
    return {
        'needs_splitting': needs_splitting,
        'recommended_separator': recommended_separator,
        'separator_analysis': separator_analysis
    }


def _generate_linking_suggestions(column_name, values, data_type):
    """Generate suggestions for linking this column to other datasets."""
    suggestions = []
    
    # Name-based suggestions
    name_lower = column_name.lower()
    
    if 'id' in name_lower:
        suggestions.append({
            'type': 'identifier',
            'confidence': 'high',
            'description': 'This appears to be an identifier column - good for linking records',
            'action': 'Use as primary key for joins'
        })
    
    if any(term in name_lower for term in ['name', 'title', 'label']):
        suggestions.append({
            'type': 'text_match',
            'confidence': 'medium',
            'description': 'Text column that might match names/titles in other datasets',
            'action': 'Consider fuzzy matching with similar columns'
        })
    
    if any(term in name_lower for term in ['date', 'time', 'created', 'modified']):
        suggestions.append({
            'type': 'temporal',
            'confidence': 'medium',
            'description': 'Temporal column useful for time-based joins',
            'action': 'Link records within time ranges'
        })
    
    # Data type-based suggestions
    if data_type['type'] == 'url':
        suggestions.append({
            'type': 'url_reference',
            'confidence': 'high',
            'description': 'URLs can be matched exactly across datasets',
            'action': 'Direct URL matching'
        })
    
    if data_type['type'] == 'email':
        suggestions.append({
            'type': 'email_reference',
            'confidence': 'high',
            'description': 'Email addresses are unique identifiers',
            'action': 'Use for person/contact linking'
        })
    
    # Value pattern-based suggestions
    if not suggestions:
        suggestions.append({
            'type': 'general',
            'confidence': 'low',
            'description': 'General text column - may need preprocessing before linking',
            'action': 'Clean and standardize values first'
        })
    
    return suggestions


def _detect_quality_issues(values, patterns):
    """Detect potential data quality issues."""
    issues = []
    
    if not values:
        return [{'type': 'empty_column', 'severity': 'high', 'description': 'Column is completely empty'}]
    
    # Check for inconsistent formatting
    if patterns.get('length_stats', {}).get('max', 0) - patterns.get('length_stats', {}).get('min', 0) > 50:
        issues.append({
            'type': 'inconsistent_length',
            'severity': 'medium',
            'description': 'Values have very different lengths - possible formatting issues'
        })
    
    # Check for mixed separators
    separators = patterns.get('common_separators', {})
    if len([s for s in separators.values() if s > 0]) > 1:
        issues.append({
            'type': 'mixed_separators',
            'severity': 'medium',
            'description': 'Multiple separators used - standardization needed'
        })
    
    # Check for potential encoding issues
    encoding_issues = sum(1 for v in values if any(char in v for char in ['�', '\ufffd']))
    if encoding_issues > 0:
        issues.append({
            'type': 'encoding_issues',
            'severity': 'high',
            'description': f'{encoding_issues} values may have encoding problems'
        })
    
    return issues


def _generate_preprocessing_recommendations(patterns, multi_value_analysis, quality_issues):
    """Generate recommendations for preprocessing this column."""
    recommendations = []
    
    # Multi-value splitting
    if multi_value_analysis.get('needs_splitting'):
        sep = multi_value_analysis.get('recommended_separator', ';')
        recommendations.append({
            'type': 'split_values',
            'priority': 'high',
            'description': f'Split values using "{sep}" separator to create multiple records',
            'action': f'Apply split transformation with separator "{sep}"'
        })
    
    # Quality issue fixes
    for issue in quality_issues:
        if issue['type'] == 'mixed_separators':
            recommendations.append({
                'type': 'standardize_separators',
                'priority': 'medium',
                'description': 'Standardize all separators to a single type',
                'action': 'Replace all separators with semicolons'
            })
        elif issue['type'] == 'encoding_issues':
            recommendations.append({
                'type': 'fix_encoding',
                'priority': 'high',
                'description': 'Fix character encoding issues',
                'action': 'Re-encode data with UTF-8'
            })
    
    # Length normalization
    length_stats = patterns.get('length_stats', {})
    if length_stats.get('max', 0) - length_stats.get('min', 0) > 100:
        recommendations.append({
            'type': 'normalize_length',
            'priority': 'low',
            'description': 'Consider truncating very long values',
            'action': 'Limit values to reasonable length (e.g., 255 characters)'
        })
    
    return recommendations


def _extract_column_relationship_insights(column_name, dataset_analysis):
    """
    Extract relationship insights for a specific column from the dataset analysis.
    Uses the sophisticated RelationshipDiscoveryService results.
    """
    insights = {
        'relationships': [],
        'semantic_clusters': [],
        'foreign_key_potential': False,
        'relationship_strength': 0.0,
        'suggested_predicates': []
    }
    
    # Find relationships involving this column
    column_relationships = []
    for relationship in dataset_analysis.relationships:
        if relationship.source_column == column_name or relationship.target_column == column_name:
            column_relationships.append({
                'partner_column': relationship.target_column if relationship.source_column == column_name else relationship.source_column,
                'type': relationship.relationship_type,
                'confidence': relationship.confidence,
                'evidence': relationship.evidence,
                'bidirectional': relationship.bidirectional,
                'suggested_predicate': relationship.suggested_predicate
            })
    
    insights['relationships'] = column_relationships
    
    # Check if column is in any semantic clusters
    for cluster in dataset_analysis.semantic_clusters:
        if column_name in cluster:
            insights['semantic_clusters'].append({
                'members': [col for col in cluster if col != column_name],
                'cluster_size': len(cluster)
            })
    
    # Check foreign key potential
    insights['foreign_key_potential'] = column_name in dataset_analysis.foreign_key_candidates
    
    # Calculate overall relationship strength (average confidence of relationships)
    if column_relationships:
        insights['relationship_strength'] = sum(rel['confidence'] for rel in column_relationships) / len(column_relationships)
    
    # Extract unique suggested predicates
    predicates = set()
    for rel in column_relationships:
        if rel['suggested_predicate']:
            predicates.add(rel['suggested_predicate'])
    insights['suggested_predicates'] = list(predicates)
    
    # Add quality metrics for this column if available
    quality_metrics = dataset_analysis.quality_metrics
    insights['quality_score'] = quality_metrics.get('overall_quality', 0.0)
    
    return insights


@login_required
def direct_dataset_linking_view(request):
    """
    View for manually linking columns between different datasets.
    Allows users to select multiple datasets and define relationships between their columns.
    Can be used as a partial view for HTMX requests.
    """
    organization_id = get_organization_id_from_request(request)
    
    logger.info(f"DATASET LINKING: Initializing view for org={organization_id}")
    
    # Check if this is a partial request (HTMX)
    is_partial = 'HX-Request' in request.headers
    
    if not organization_id or organization_id == 'default-org':
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        context = {
            'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL.',
            'organizations': available_organizations,
            'show_organization_help': True
        }
        template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
        return render(request, template, context)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        
        # Check if the selected organization exists in S3
        org_exists = any(org['id'] == organization_id for org in available_organizations)
        if not org_exists:
            context = {
                'organizations': available_organizations,
                'organization_id': organization_id,
                'error': f'Organization "{organization_id}" not found in S3. Available organizations: {", ".join([org["id"] for org in available_organizations])}'
            }
            template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
            return render(request, template, context)
        
        # Discover available data sources from S3 for this organization
        sources = analyzer.discover_s3_data_sources(organization_id)
        
        # Build a list of all datasets with their columns for selection
        all_datasets = []
        
        for source in sources:
            try:
                # Get dataset names for this source
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                
                for dataset_name in dataset_names:
                    try:
                        # Get preview to get column information
                        preview = analyzer.get_s3_table_preview(source, dataset_name, limit=3)
                        
                        dataset_info = {
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'row_count': preview.total_rows,
                            'column_count': len(preview.column_headers),
                            'columns': preview.column_headers,
                            'source_info': {
                                'format': source.format,
                                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                            }
                        }
                        
                        all_datasets.append(dataset_info)
                        
                    except Exception as dataset_error:
                        logger.warning(f"DATASET LINKING: Error loading dataset {dataset_name} from {source.name}: {dataset_error}")
                        continue
                        
            except Exception as source_error:
                logger.error(f"DATASET LINKING: Error processing source {source.name}: {source_error}")
                continue
        
        logger.info(f"DATASET LINKING: Found {len(all_datasets)} datasets for linking")
        
        context = {
            'datasets': all_datasets,
            'organizations': available_organizations,
            'organization_id': organization_id,
            'total_datasets': len(all_datasets)
        }
        
        template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
        return render(request, template, context)
        
    except Exception as e:
        logger.error(f"DATASET LINKING: Error setting up linking view: {e}", exc_info=True)
        
        context = {
            'error': f"Error loading datasets: {str(e)}",
            'organizations': available_organizations,
            'organization_id': organization_id
        }
        template = 'partials/dataset_linking_panel.html' if is_partial else 'direct_dataset_linking.html'
        return render(request, template, context)


@login_required
def save_dataset_links(request):
    """
    AJAX endpoint to save manually created links between datasets.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        data = json.loads(request.body)
        links = data.get('links', [])
        organization_id = data.get('organization_id') or get_organization_id_from_request(request)
        
        logger.info(f"SAVE LINKS: Received {len(links)} dataset links for org={organization_id}")
        
        # Validate links format
        for link in links:
            if not all(k in link for k in ['source_dataset', 'source_column', 'target_dataset', 'target_column', 'relationship_type']):
                return JsonResponse({'error': 'Invalid link format'}, status=400)
        
        # Save links to cache for now (in production, this would go to a database)
        cache_key = f"manual_dataset_links_{organization_id}"
        existing_links = cache.get(cache_key, [])
        
        # Add new links, avoiding duplicates
        for link in links:
            if link not in existing_links:
                existing_links.append(link)
        
        # Save back to cache
        cache.set(cache_key, existing_links, timeout=60*60*24*30)  # 30 days
        
        return JsonResponse({
            'success': True,
            'message': f'Saved {len(links)} dataset links',
            'total_links': len(existing_links)
        })
        
    except Exception as e:
        logger.error(f"SAVE LINKS: Error saving dataset links: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_saved_dataset_links(request):
    """
    AJAX endpoint to retrieve saved links between datasets.
    """
    organization_id = request.GET.get('organization_id') or get_organization_id_from_request(request)
    
    logger.info(f"GET LINKS: Retrieving saved dataset links for org={organization_id}")
    
    try:
        # Get links from cache
        cache_key = f"manual_dataset_links_{organization_id}"
        links = cache.get(cache_key, [])
        
        return JsonResponse({
            'links': links,
            'count': len(links),
            'organization_id': organization_id
        })
        
    except Exception as e:
        logger.error(f"GET LINKS: Error retrieving dataset links: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def direct_relationship_discovery_view(request):
    """
    View for automated cross-dataset relationship discovery.
    Allows users to select datasets for automated relationship analysis.
    Can be used as a partial view for HTMX requests.
    """
    organization_id = get_organization_id_from_request(request)
    auto_discover = request.GET.get('auto_discover', False)
    
    logger.info(f"RELATIONSHIP DISCOVERY: Initializing view for org={organization_id}, auto_discover={auto_discover}")
    
    # Check if this is a partial request (HTMX)
    is_partial = 'HX-Request' in request.headers
    
    if not organization_id or organization_id == 'default-org':
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        context = {
            'error': 'Organization parameter required. Please add ?organization=YOUR_ORG_ID to the URL.',
            'organizations': available_organizations,
            'show_organization_help': True
        }
        template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
        return render(request, template, context)
    
    try:
        analyzer = S3DirectDataAnalyzer()
        available_organizations = _discover_available_organizations(analyzer)
        
        # Check if the selected organization exists in S3
        org_exists = any(org['id'] == organization_id for org in available_organizations)
        if not org_exists:
            context = {
                'organizations': available_organizations,
                'organization_id': organization_id,
                'error': f'Organization "{organization_id}" not found in S3. Available organizations: {", ".join([org["id"] for org in available_organizations])}'
            }
            template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
            return render(request, template, context)
        
        # Discover available data sources from S3 for this organization
        sources = analyzer.discover_s3_data_sources(organization_id)
        
        # Build a list of all datasets for selection
        all_datasets = []
        
        for source in sources:
            try:
                # Get dataset names for this source
                dataset_names = analyzer.get_dataset_names_from_s3_source(source)
                
                for dataset_name in dataset_names:
                    try:
                        # Get basic preview for each dataset
                        preview = analyzer.get_s3_table_preview(source, dataset_name, limit=3)
                        
                        dataset_info = {
                            'name': dataset_name,
                            'source_name': source.name,
                            'source_display_name': f"{source.name} ({source.format})",
                            'row_count': preview.total_rows,
                            'column_count': len(preview.column_headers),
                            'columns': preview.column_headers,
                            'source_info': {
                                'format': source.format,
                                'size_mb': round(source.size_bytes / (1024 * 1024), 2) if source.size_bytes else 0,
                                'modified_date': source.modified_date.strftime('%Y-%m-%d %H:%M') if source.modified_date else None
                            }
                        }
                        
                        all_datasets.append(dataset_info)
                        
                    except Exception as dataset_error:
                        logger.warning(f"RELATIONSHIP DISCOVERY: Error loading dataset {dataset_name} from {source.name}: {dataset_error}")
                        continue
                        
            except Exception as source_error:
                logger.error(f"RELATIONSHIP DISCOVERY: Error processing source {source.name}: {source_error}")
                continue
        
        logger.info(f"RELATIONSHIP DISCOVERY: Found {len(all_datasets)} datasets for analysis")
        
        # If auto_discover is requested, automatically run discovery on all datasets
        discovery_results = None
        if auto_discover and all_datasets:
            try:
                logger.info("RELATIONSHIP DISCOVERY: Running auto-discovery")
                discovery_results = _run_auto_discovery(analyzer, organization_id, all_datasets[:5])  # Limit to first 5 for performance
            except Exception as discovery_error:
                logger.error(f"RELATIONSHIP DISCOVERY: Auto-discovery failed: {discovery_error}")
        
        context = {
            'datasets': all_datasets,
            'organizations': available_organizations,
            'organization_id': organization_id,
            'total_datasets': len(all_datasets),
            'discovery_results': discovery_results,
            'auto_discover': auto_discover
        }
        
        template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
        return render(request, template, context)
        
    except Exception as e:
        logger.error(f"RELATIONSHIP DISCOVERY: Error setting up discovery view: {e}", exc_info=True)
        
        context = {
            'error': f"Error loading datasets: {str(e)}",
            'organizations': available_organizations,
            'organization_id': organization_id
        }
        template = 'partials/relationship_discovery_panel.html' if is_partial else 'direct_relationship_discovery.html'
        return render(request, template, context)


def _run_auto_discovery(analyzer, organization_id, datasets, sample_size=500):
    """
    Helper function to run automated relationship discovery on selected datasets.
    """
    from arkumu.semantic_graph.services import RelationshipDiscoveryService
    import tempfile
    import os
    
    temp_files = []
    
    try:
        # Create temporary CSV files for analysis
        for dataset_info in datasets:
            source_name = dataset_info.get('source_name')
            dataset_name = dataset_info.get('name')
            
            if not source_name or not dataset_name:
                continue
            
            try:
                # Find the source in S3
                sources = analyzer.discover_s3_data_sources(organization_id)
                source_info = next((s for s in sources if s.name == source_name), None)
                
                if not source_info:
                    continue
                
                # Get dataset preview for analysis
                preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=sample_size)
                
                # Create temporary CSV file for relationship analysis
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                    # Write headers
                    temp_file.write(','.join(preview.column_headers) + '\n')
                    
                    # Write data rows
                    for row in preview.data_rows:
                        # Ensure all rows have the same number of columns
                        padded_row = row + [''] * (len(preview.column_headers) - len(row))
                        row_str = ','.join([f'"{str(cell).replace('"', '""')}"' if cell else '' for cell in padded_row])
                        temp_file.write(row_str + '\n')
                    
                    # Add to list of temporary files with dataset info
                    temp_files.append({
                        'path': temp_file.name,
                        'dataset_name': dataset_name,
                        'source_name': source_name
                    })
            
            except Exception as dataset_error:
                logger.warning(f"Auto-discovery: Error processing dataset {dataset_name} from {source_name}: {dataset_error}")
                continue
        
        if not temp_files:
            return {'error': 'Could not process any datasets for discovery'}
        
        # Run relationship discovery across datasets
        relationship_service = RelationshipDiscoveryService()
        dataset_paths = [temp_file['path'] for temp_file in temp_files]
        
        analysis_results = relationship_service.compare_datasets_relationships(dataset_paths, sample_size)
        
        # Format results for UI display
        cross_relationships = analysis_results.get('cross_dataset_relationships', [])
        
        # Format for visualization
        formatted_relationships = []
        for rel in cross_relationships:
            # Extract dataset and column names
            source_parts = rel['source_column'].split('.')
            target_parts = rel['target_column'].split('.')
            
            source_dataset = source_parts[0]
            source_column = '.'.join(source_parts[1:])
            target_dataset = target_parts[0]
            target_column = '.'.join(target_parts[1:])
            
            formatted_rel = {
                'source_dataset': source_dataset,
                'source_column': source_column,
                'target_dataset': target_dataset,
                'target_column': target_column,
                'relationship_type': rel['relationship_type'],
                'confidence_score': rel['confidence_score'],
                'relationship_description': rel.get('relationship_description', ''),
                'sample_values': rel.get('sample_values', [])
            }
            
            formatted_relationships.append(formatted_rel)
        
        return {
            'relationships': formatted_relationships,
            'total_relationships': len(formatted_relationships),
            'datasets_analyzed': len(temp_files)
        }
        
    finally:
        # Clean up temporary files
        for temp_file in temp_files:
            try:
                os.unlink(temp_file['path'])
            except Exception:
                pass


@login_required
def run_relationship_discovery(request):
    """
    AJAX endpoint to run automated relationship discovery across selected datasets.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Only POST method allowed'}, status=400)
    
    try:
        data = json.loads(request.body)
        selected_datasets = data.get('datasets', [])
        organization_id = data.get('organization_id') or get_organization_id_from_request(request)
        sample_size = int(data.get('sample_size', 500))
        
        logger.info(f"RUN DISCOVERY: Analyzing {len(selected_datasets)} datasets for org={organization_id}")
        
        if not selected_datasets:
            return JsonResponse({'error': 'No datasets selected'}, status=400)
        
        # Create temporary CSV files for analysis
        analyzer = S3DirectDataAnalyzer()
        temp_files = []
        
        for dataset_info in selected_datasets:
            source_name = dataset_info.get('source_name')
            dataset_name = dataset_info.get('name')
            
            if not source_name or not dataset_name:
                continue
            
            try:
                # Find the source in S3
                sources = analyzer.discover_s3_data_sources(organization_id)
                source_info = next((s for s in sources if s.name == source_name), None)
                
                if not source_info:
                    logger.warning(f"RUN DISCOVERY: Source '{source_name}' not found")
                    continue
                
                # Get dataset preview for analysis
                preview = analyzer.get_s3_table_preview(source_info, dataset_name, limit=sample_size)
                
                # Create temporary CSV file for relationship analysis
                with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as temp_file:
                    # Write headers
                    temp_file.write(','.join(preview.column_headers) + '\n')
                    
                    # Write data rows
                    for row in preview.data_rows:
                        # Ensure all rows have the same number of columns
                        padded_row = row + [''] * (len(preview.column_headers) - len(row))
                        row_str = ','.join([f'"{str(cell).replace('"', '""')}"' if cell else '' for cell in padded_row])
                        temp_file.write(row_str + '\n')
                    
                    # Add to list of temporary files with dataset info
                    temp_files.append({
                        'path': temp_file.name,
                        'dataset_name': dataset_name,
                        'source_name': source_name
                    })
                    
                    logger.info(f"RUN DISCOVERY: Created temp file for {dataset_name} from {source_name}")
            
            except Exception as dataset_error:
                logger.warning(f"RUN DISCOVERY: Error processing dataset {dataset_name} from {source_name}: {dataset_error}")
                continue
        
        if not temp_files:
            return JsonResponse({'error': 'Could not process any of the selected datasets'}, status=400)
        
        try:
            # Run relationship discovery across datasets
            relationship_service = RelationshipDiscoveryService()
            dataset_paths = [temp_file['path'] for temp_file in temp_files]
            
            logger.info(f"RUN DISCOVERY: Running relationship discovery on {len(dataset_paths)} datasets")
            analysis_results = relationship_service.compare_datasets_relationships(dataset_paths, sample_size)
            
            # Create a lookup map from path to dataset name
            dataset_name_lookup = {temp_file['path']: temp_file['dataset_name'] for temp_file in temp_files}
            source_name_lookup = {temp_file['path']: temp_file['source_name'] for temp_file in temp_files}
            
            # Format results for UI display - focus on cross-dataset relationships
            cross_relationships = analysis_results.get('cross_dataset_relationships', [])
            
            # Format for visualization
            formatted_relationships = []
            for rel in cross_relationships:
                # Extract dataset and column names
                source_parts = rel['source_column'].split('.')
                target_parts = rel['target_column'].split('.')
                
                source_dataset = source_parts[0]
                source_column = '.'.join(source_parts[1:])
                target_dataset = target_parts[0]
                target_column = '.'.join(target_parts[1:])
                
                # Format for visualization
                formatted_rel = {
                    'source_dataset': source_dataset,
                    'source_column': source_column,
                    'target_dataset': target_dataset,
                    'target_column': target_column,
                    'relationship_type': rel['relationship_type'],
                    'confidence': rel['confidence'],
                    'evidence': rel.get('evidence', {}),
                    'source': {
                        'dataset': source_dataset,
                        'source_name': next((source_name_lookup.get(path) for path, name in dataset_name_lookup.items() if name == source_dataset), ""),
                    },
                    'target': {
                        'dataset': target_dataset,
                        'source_name': next((source_name_lookup.get(path) for path, name in dataset_name_lookup.items() if name == target_dataset), ""),
                    }
                }
                
                formatted_relationships.append(formatted_rel)
            
            # Filter to only reasonably confident relationships
            confident_relationships = [r for r in formatted_relationships if r['confidence'] >= 0.3]
            
            # Store results in cache
            cache_key = f"discovery_results_{organization_id}"
            cache.set(cache_key, {
                'relationships': formatted_relationships,
                'confident_relationships': confident_relationships,
                'analysis_timestamp': analysis_results.get('analysis_timestamp'),
                'total_datasets': len(dataset_paths),
                'sample_size': sample_size
            }, timeout=60*60*24)  # 24 hours
            
            # Return partial template for HTMX or JSON for regular requests
            if request.headers.get('HX-Request'):
                return render(request, 'partials/relationship_discovery_results.html', {
                    'relationships': confident_relationships[:20],  # Limit initial response size
                    'total_relationships': len(formatted_relationships),
                    'confident_relationships': len(confident_relationships),
                    'total_datasets': len(dataset_paths),
                    'organization_id': organization_id,
                    'analysis_timestamp': analysis_results.get('analysis_timestamp')
                })
            else:
                return JsonResponse({
                    'success': True,
                    'relationships': confident_relationships[:20],  # Limit initial response size
                    'total_relationships': len(formatted_relationships),
                    'confident_relationships': len(confident_relationships),
                    'analysis_timestamp': analysis_results.get('analysis_timestamp')
                })
            
        finally:
            # Clean up temporary files
            for temp_file in temp_files:
                try:
                    os.unlink(temp_file['path'])
                except Exception as cleanup_error:
                    logger.warning(f"RUN DISCOVERY: Could not clean up temp file: {cleanup_error}")
        
    except Exception as e:
        logger.error(f"RUN DISCOVERY: Error in relationship discovery: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_discovery_results(request):
    """
    AJAX endpoint to retrieve the results of a previous relationship discovery run.
    """
    organization_id = request.GET.get('organization_id') or get_organization_id_from_request(request)
    include_all = request.GET.get('include_all', 'false').lower() == 'true'
    
    logger.info(f"GET DISCOVERY: Retrieving relationship discovery results for org={organization_id}")
    
    try:
        # Get results from cache
        cache_key = f"discovery_results_{organization_id}"
        results = cache.get(cache_key, {})
        
        if not results:
            return JsonResponse({'error': 'No discovery results found. Please run a new analysis.'}, status=404)
        
        # Return either all relationships or just confident ones
        if include_all:
            relationships = results.get('relationships', [])
        else:
            relationships = results.get('confident_relationships', [])
        
        # Return partial template for HTMX or JSON for regular requests
        if request.headers.get('HX-Request'):
            # Use relationships list partial for toggle updates
            return render(request, 'partials/relationships_list.html', {
                'relationships': relationships,
                'organization_id': organization_id
            })
        else:
            return JsonResponse({
                'relationships': relationships,
                'total_relationships': len(results.get('relationships', [])),
                'confident_relationships': len(results.get('confident_relationships', [])),
                'analysis_timestamp': results.get('analysis_timestamp'),
                'sample_size': results.get('sample_size', 500),
                'total_datasets': results.get('total_datasets', 0)
            })
        
    except Exception as e:
        logger.error(f"GET DISCOVERY: Error retrieving discovery results: {e}", exc_info=True)
        return JsonResponse({'error': str(e)}, status=500) 