"""
CSV Mapping Execution Views - Simple SmartBulkUpdaterPolars Integration

This module executes CSV mappings created through the GUI by applying them
to datasets using SmartBulkUpdaterPolars for efficient processing.

HOW CSV MAPPING CONFIGURATIONS ARE APPLIED:
==========================================

1. DATASET → ENTITY MAPPING:
   - Each CSV dataset represents one entity type
   - Dataset name becomes the entity class (e.g., "researchers.csv" → "Researcher" entities)
   - Each row in the dataset becomes one entity instance

2. ANCHOR COLUMN DETERMINATION:
   - DEFAULT: First column is used as entity anchor (primary key)
   - EXPLICIT: If mapping specifies anchor columns, those are used instead
   - The anchor column(s) determine the entity URI: 
     http://arkumu.org/entities/{dataset_name}/{anchor_value}

3. COLUMN TYPE MAPPING:
   - Regular columns → Properties of the entity
   - Multi-value columns → Multiple property triples (comma-separated values)
   - FK columns → Relationships to other entities
   - External ontology columns → Links to external URIs (ORCID, Wikidata, etc.)
   - Anchor columns → Entity identity (not properties)

4. PROPERTY URI GENERATION:
   - Regular columns: column name + arkumu_type → Property URI
     Example: "name" column with arkumu_type "full_name" → 
     http://arkumu.org/properties/full_name
   - External ontology columns: Use external ontology URI template
     Example: ORCID column with identifier "0000-0002-1825-0097" → 
     https://orcid.org/0000-0002-1825-0097

5. EXTERNAL ONTOLOGY & VOCABULARY HANDLING:
   - Columns marked as external ontology use ontology-specific URI templates
   - Supported authority files: ORCID, Wikidata, GND, VIAF, Library of Congress, ISNI
   - Supported vocabularies: Dublin Core, FOAF, SKOS, Schema.org, BIBFRAME, DCAT, PROV-O, VoID, ORG, OWL-Time
   - Custom ontologies supported with user-defined URI templates
   - Identifier/term validation using ontology-specific patterns
   - Examples:
     * Authority file: researcher_orcid → https://orcid.org/0000-0002-1825-0097
     * Vocabulary term: title_column → http://purl.org/dc/terms/title

6. RELATIONSHIP HANDLING:
   - FK columns create relationships to referenced entities
   - Target entity URI generated from FK value
   - Relationship type determined by column's arkumu_type

EXAMPLE MAPPING APPLICATION:
===========================

CSV Data:
researcher_id,name,email,orcid_id,institution_id,specializations
R001,Dr. Smith,smith@uni.edu,0000-0002-1825-0097,MIT,"AI,ML,Ethics"

Mapping Configuration:
{
  "workspace_columns": {
    "org::researchers.csv::researcher_id": {"arkumu_type": "identifier", "is_anchor": true},
    "org::researchers.csv::name": {"arkumu_type": "full_name"},
    "org::researchers.csv::email": {"arkumu_type": "email_address"},
    "org::researchers.csv::orcid_id": {
      "arkumu_type": "orcid_identifier", 
      "is_external_ontology": true,
      "external_ontology": {
        "ontology_type": "orcid",
        "uri_template": "https://orcid.org/{identifier}",
        "identifier_pattern": "^\\d{4}-\\d{4}-\\d{4}-\\d{3}[\\dX]$"
      }
    },
    "org::researchers.csv::institution_id": {"arkumu_type": "affiliated_with", "is_fk": true},
    "org::researchers.csv::specializations": {"arkumu_type": "specializes_in", "is_multi_value": true}
  }
}

Generated RDF:
<http://arkumu.org/entities/researchers/R001>
  a <http://arkumu.org/classes/Researcher> ;
  <http://arkumu.org/properties/full_name> "Dr. Smith" ;
  <http://arkumu.org/properties/email_address> "smith@uni.edu" ;
  <http://arkumu.org/properties/orcid_identifier> <https://orcid.org/0000-0002-1825-0097> ;
  <http://arkumu.org/relationships/affiliated_with> <http://arkumu.org/entities/institutions/MIT> ;
  <http://arkumu.org/properties/specializes_in> "AI", "ML", "Ethics" .

PROCESSING FLOW:
===============
1. Load mapping configuration from GUI
2. Initialize SmartBulkUpdaterPolars with organization settings
3. Analyze external ontology configurations (ORCID, Wikidata, etc.)
4. For each selected dataset:
   - Stream data from S3
   - Apply mapping rules row-by-row (currently without external ontology support)
   - Create complete entities with properties and relationships
   - Use first column as anchor unless mapping specifies otherwise
5. Aggregate statistics and return results

FUTURE ENHANCEMENTS:
==================
- Pass workspace_columns mapping to SmartBulkUpdaterPolars
- Implement external ontology URI generation in SmartBulkUpdaterPolars
- Support custom anchor column selection from GUI mapping
- Add validation for external ontology identifiers during processing
"""

import logging
import json
from django.http import JsonResponse
from django.views import View
from django.utils import timezone
from django.shortcuts import render
from typing import Dict, List, Any

from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.services.data_analysis.s3_direct_data_analyzer import S3DirectDataAnalyzer
from arkumu.importer.services.importer.smart_bulk_updater_polars import SmartBulkUpdaterPolars
from arkumu.importer.services.importer.smart_bulk_updater import UpdateStrategy
from arkumu.metadata.views.csv_mapping.mixins.coordinator import CSVMappingCoordinatorMixin
from arkumu.metadata.views.csv_mapping.mixins.base import OrganizationMixin

logger = logging.getLogger(__name__)


class ExecuteGUIMappingView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """Execute CSV mapping using SmartBulkUpdaterPolars directly."""
    
    def post(self, request):
        """Execute a saved GUI mapping configuration."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            
            # Get execution parameters
            mapping_id = request.POST.get('mapping_id')
            dataset_name = request.POST.get('dataset_name')
            strategy = request.POST.get('strategy', 'SKIP_EXISTING')
            
            if not mapping_id and not dataset_name:
                return JsonResponse({
                    'error': 'Either mapping_id or dataset_name is required'
                }, status=400)
            
            # Load mapping configuration
            if mapping_id:
                try:
                    mapping = Mapping.objects.get(id=mapping_id, organization_id=organization_id)
                    mapping_config = mapping.mapping_config
                    execution_name = f"Saved Mapping: {mapping.name}"
                except Mapping.DoesNotExist:
                    return JsonResponse({
                        'error': f'Mapping with ID {mapping_id} not found'
                    }, status=404)
            else:
                # Use current session state
                mapping_config = self.serialize_current_mapping_state(request, organization_id, dataset_name)
                execution_name = f"Current Session: {dataset_name}"
            
            # Execute with SmartBulkUpdaterPolars
            execution_results = self._execute_with_smart_bulk_updater_polars(
                mapping_config, organization_id, dataset_name or f"mapping_{mapping_id}", strategy
            )
            
            # Update mapping timestamp
            if mapping_id:
                mapping.last_executed = timezone.now()
                mapping.save(update_fields=['last_executed'])
            
            # Return response
            if request.headers.get('HX-Request'):
                return render(request, 'partials/service_execution_results.html', {
                    'execution_name': execution_name,
                    'execution_results': execution_results,
                    'success': True
                })
            else:
                return JsonResponse({
                    'status': 'success',
                    'execution_name': execution_name,
                    'execution_summary': execution_results,
                    'engine_used': 'SmartBulkUpdaterPolars'
                })
            
        except Exception as e:
            logger.error(f"Error executing GUI mapping: {e}", exc_info=True)
            
            if request.headers.get('HX-Request'):
                return render(request, 'partials/service_execution_results.html', {
                    'error': f'Execution failed: {str(e)}'
                })
            else:
                return JsonResponse({
                    'error': f'Execution failed: {str(e)}'
                }, status=500)
    
    def _execute_with_smart_bulk_updater_polars(self, mapping_config, organization_id, dataset_name, strategy):
        """
        Execute mapping using SmartBulkUpdaterPolars directly.
        
        This method applies GUI mapping configurations to CSV datasets by:
        1. Converting GUI mapping config to SmartBulkUpdaterPolars parameters
        2. Processing each dataset as entity instances
        3. Using first column as anchor unless mapping specifies otherwise
        
        Args:
            mapping_config: GUI mapping configuration with workspace_columns
            organization_id: Organization identifier for URI generation
            dataset_name: Name of dataset being processed  
            strategy: Update strategy (SKIP_EXISTING, UPDATE_EXISTING, REPLACE_EXISTING)
        """
        
        logger.info(f"Executing mapping with SmartBulkUpdaterPolars for dataset: {dataset_name}")
        
        # STEP 1: Convert update strategy from GUI format to SmartBulkUpdaterPolars format
        strategy_map = {
            'SKIP_EXISTING': UpdateStrategy.SKIP_EXISTING,
            'UPDATE_EXISTING': UpdateStrategy.UPDATE_VALUES,
            'REPLACE_EXISTING': UpdateStrategy.REPLACE_ALL
        }
        update_strategy = strategy_map.get(strategy, UpdateStrategy.SKIP_EXISTING)
        
        # STEP 2: Initialize SmartBulkUpdaterPolars with mapping-aware configuration
        # This determines how CSV data is converted to RDF entities:
        smart_updater = SmartBulkUpdaterPolars(
            default_strategy=update_strategy,
            institution=organization_id,                    # Organization becomes URI namespace
            base_uri="http://arkumu.org/data",              # Base URI for all generated entities
            link_row_cells=True,                            # Create row-level provenance links
            link_topology="first_column",                   # DEFAULT: First column is anchor (primary key)
            multi_value_threshold=0.2                       # Auto-detect comma-separated values
        )
        
        # STEP 3: Extract mapping configuration details
        workspace_columns = mapping_config.get('workspace_columns', {})
        logger.info(f"Applying mapping with {len(workspace_columns)} configured columns")
        
        # STEP 3.1: Analyze external ontology configurations
        external_ontology_columns = []
        for column_id, column_config in workspace_columns.items():
            if column_config.get('is_external_ontology'):
                external_ontology_columns.append(column_id)
                ontology_info = column_config.get('external_ontology', {})
                logger.info(f"External ontology column '{column_id}': {ontology_info.get('ontology_type', 'unknown')}")
        
        if external_ontology_columns:
            logger.info(f"Processing {len(external_ontology_columns)} external ontology columns: {external_ontology_columns}")
        
        # NOTE: Current SmartBulkUpdaterPolars implementation does not yet support external ontology
        # configurations directly. This is a future enhancement that would require:
        # 1. Passing workspace_columns mapping to SmartBulkUpdaterPolars
        # 2. Modifying SmartBulkUpdaterPolars to check for external_ontology configurations
        # 3. Using uri_template to generate external URIs instead of local arkumu.org properties
        # 
        # For now, external ontology columns are processed as regular properties
        # TODO: Implement external ontology support in SmartBulkUpdaterPolars
        
        # STEP 4: Get datasets to process from mapping configuration
        selected_datasets = mapping_config.get('selected_datasets', [])
        analyzer = S3DirectDataAnalyzer()
        
        combined_stats = None
        total_datasets_processed = 0
        
        # STEP 5: Process each dataset as entity instances
        # Each dataset represents one entity type (e.g., "researchers.csv" → Researcher entities)
        for dataset in selected_datasets:
            try:
                # Find S3 source for this dataset
                available_sources = analyzer.discover_s3_data_sources(organization_id)
                source_info = None
                
                for source in available_sources:
                    datasets = analyzer.get_dataset_names_from_s3_source(source)
                    if dataset in datasets:
                        source_info = source
                        break
                
                if not source_info:
                    logger.error(f"No S3 source found for dataset: {dataset}")
                    continue
                
                logger.info(f"Processing dataset {dataset} with SmartBulkUpdaterPolars")
                
                # STEP 5.1: Apply dataset → entity mapping
                # Dataset name (e.g., "researchers.csv") becomes entity type
                # Each row becomes an entity instance with URI:
                # http://arkumu.org/entities/{dataset_name}/{anchor_value}
                
                # STEP 5.2: Stream process the dataset with SmartBulkUpdaterPolars
                # Currently this processes data without GUI mapping configuration
                # TODO: Pass workspace_columns to enable external ontology handling
                stats = analyzer.stream_process_s3_source_with_smart_updater(
                    source_info=source_info,
                    smart_updater=smart_updater,
                    dataset_name=dataset,
                    batch_size=1000,
                    organization_id=organization_id
                    # TODO: Add mapping_config parameter for ontology support
                    # mapping_config=workspace_columns  # Future enhancement
                )
                
                if combined_stats is None:
                    combined_stats = stats
                else:
                    # Merge stats
                    combined_stats.rows_processed += stats.rows_processed
                    combined_stats.resources_created += stats.resources_created
                    combined_stats.triples_created += stats.triples_created
                    combined_stats.total_values_created += stats.total_values_created
                    combined_stats.resources_updated += stats.resources_updated
                    combined_stats.resources_skipped += stats.resources_skipped
                    combined_stats.errors += stats.errors
                    combined_stats.cells_processed += stats.cells_processed
                
                total_datasets_processed += 1
                logger.info(f"Successfully processed dataset {dataset}: {stats.rows_processed} rows")
                
            except Exception as e:
                logger.error(f"Error processing dataset {dataset}: {str(e)}")
                if combined_stats is None:
                    from arkumu.importer.services.importer.smart_bulk_updater import BulkUpdateStats
                    combined_stats = BulkUpdateStats()
                combined_stats.errors += 1
        
        if not combined_stats or combined_stats.rows_processed == 0:
            raise Exception("No data was successfully processed")
        
        # Return results
        return {
            'total_rows_processed': combined_stats.rows_processed,
            'total_resources_created': combined_stats.resources_created,
            'total_triples_created': combined_stats.triples_created,
            'total_values_created': combined_stats.total_values_created,
            'resources_updated': combined_stats.resources_updated,
            'resources_skipped': combined_stats.resources_skipped,
            'errors': [f"{combined_stats.errors} error(s) occurred"] if combined_stats.errors > 0 else [],
            'cells_processed': combined_stats.cells_processed,
            'engine_used': "SmartBulkUpdaterPolars",
            'datasets_processed': total_datasets_processed,
            'processing_method': 'direct_polars'
        }


class GetMappingExecutionStatusView(OrganizationMixin, CSVMappingCoordinatorMixin, View):
    """Get execution status preview."""
    
    def get(self, request):
        """Get execution status and preview for a mapping."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            mapping_id = request.GET.get('mapping_id')
            dataset_name = request.GET.get('dataset_name')
            
            if not mapping_id and not dataset_name:
                return JsonResponse({
                    'error': 'Either mapping_id or dataset_name is required'
                }, status=400)
            
            # Load mapping configuration
            if mapping_id:
                try:
                    mapping = Mapping.objects.get(id=mapping_id, organization_id=organization_id)
                    mapping_config = mapping.mapping_config
                    analysis_name = f"Saved Mapping: {mapping.name}"
                except Mapping.DoesNotExist:
                    return JsonResponse({
                        'error': f'Mapping with ID {mapping_id} not found'
                    }, status=404)
            else:
                mapping_config = self.serialize_current_mapping_state(request, organization_id, dataset_name)
                analysis_name = f"Current Session: {dataset_name}"
            
            # Simple analysis
            selected_datasets = mapping_config.get('selected_datasets', [])
            workspace_columns = mapping_config.get('workspace_columns', {})
            
            return JsonResponse({
                'status': 'analysis_complete',
                'analysis_name': analysis_name,
                'ready_to_execute': len(selected_datasets) > 0 and len(workspace_columns) > 0,
                'datasets': selected_datasets,
                'total_columns': len(workspace_columns),
                'engine': 'SmartBulkUpdaterPolars',
                'mapping_id': mapping_id,
                'dataset_name': dataset_name
            })
            
        except Exception as e:
            logger.error(f"Error analyzing mapping execution status: {e}", exc_info=True)
            return JsonResponse({
                'error': f'Analysis failed: {str(e)}'
            }, status=500)


class ValidateMappingExecutionView(OrganizationMixin, View):
    """Validate mapping for execution."""
    
    def post(self, request):
        """Validate mapping for execution readiness."""
        try:
            organization_id = self.get_organization_id_from_request(request)
            mapping_id = request.POST.get('mapping_id')
            
            if not mapping_id:
                return JsonResponse({
                    'error': 'mapping_id is required'
                }, status=400)
            
            # Load and validate mapping
            try:
                mapping = Mapping.objects.get(id=mapping_id, organization_id=organization_id)
                mapping_config = mapping.mapping_config
            except Mapping.DoesNotExist:
                return JsonResponse({
                    'error': f'Mapping with ID {mapping_id} not found'
                }, status=404)
            
            # Simple validation
            errors = []
            warnings = []
            
            selected_datasets = mapping_config.get('selected_datasets', [])
            workspace_columns = mapping_config.get('workspace_columns', {})
            
            if not selected_datasets:
                errors.append("No datasets selected")
            if not workspace_columns:
                errors.append("No columns configured")
            
            is_valid = len(errors) == 0
            
            return JsonResponse({
                'validation_target': f"Mapping: {mapping.name}",
                'is_valid': is_valid,
                'is_executable': is_valid,
                'errors': errors,
                'warnings': warnings,
                'mapping_id': mapping_id
            })
            
        except Exception as e:
            logger.error(f"Error validating mapping execution: {e}", exc_info=True)
            return JsonResponse({
                'error': f'Validation failed: {str(e)}'
            }, status=500) 