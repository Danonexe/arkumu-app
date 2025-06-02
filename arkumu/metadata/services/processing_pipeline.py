"""
Processing Pipeline Service

Orchestrates multi-phase semantic transformations with configurable processing stages.
Handles entity creation, relationship mapping, and validation in a pipeline architecture.
"""

import polars as pl
from typing import Dict, List, Any, Optional, Tuple, Callable
from dataclasses import dataclass
from enum import Enum
import logging
from concurrent.futures import ThreadPoolExecutor
import time

logger = logging.getLogger(__name__)


class ProcessingPhase(Enum):
    ANALYSIS = "analysis"
    ENTITY_CREATION = "entity_creation"
    RELATIONSHIP_MAPPING = "relationship_mapping"
    VALIDATION = "validation"
    OUTPUT_GENERATION = "output_generation"


class ProcessingStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class ProcessingResult:
    """Result of a processing phase"""
    phase: ProcessingPhase
    status: ProcessingStatus
    start_time: float
    end_time: Optional[float]
    input_count: int
    output_count: int
    errors: List[str]
    warnings: List[str]
    metadata: Dict[str, Any]
    

@dataclass
class PipelineExecution:
    """Complete pipeline execution record"""
    id: str
    configuration_id: str
    start_time: float
    end_time: Optional[float]
    total_status: ProcessingStatus
    phase_results: List[ProcessingResult]
    input_datasets: List[str]
    output_location: Optional[str]
    summary: Dict[str, Any]


@dataclass
class ProcessingOptions:
    """Options for pipeline execution"""
    dry_run: bool = False
    parallel_processing: bool = True
    max_workers: int = 4
    chunk_size: int = 1000
    validate_during_processing: bool = True
    continue_on_errors: bool = False
    output_format: str = 'turtle'  # turtle, json-ld, ntriples
    create_backup: bool = True


class ProcessingPipelineService:
    """Service for orchestrating semantic transformation pipelines"""
    
    def __init__(self, table_analysis_service, mapping_config_service, 
                 reference_resolution_service, validation_service):
        """
        Initialize with required services
        
        Args:
            table_analysis_service: TableAnalysisService instance
            mapping_config_service: MappingConfigurationService instance  
            reference_resolution_service: ReferenceResolutionService instance
            validation_service: ValidationService instance
        """
        self.table_analysis = table_analysis_service
        self.mapping_config = mapping_config_service
        self.reference_resolution = reference_resolution_service
        self.validation = validation_service
        
        self._executions = {}
        self._phase_processors = {
            ProcessingPhase.ANALYSIS: self._process_analysis_phase,
            ProcessingPhase.ENTITY_CREATION: self._process_entity_creation_phase,
            ProcessingPhase.RELATIONSHIP_MAPPING: self._process_relationship_mapping_phase,
            ProcessingPhase.VALIDATION: self._process_validation_phase,
            ProcessingPhase.OUTPUT_GENERATION: self._process_output_generation_phase,
        }
    
    def execute_pipeline(self, dataset_paths: List[str], configuration_id: str, 
                        options: ProcessingOptions = None) -> str:
        """
        Execute a complete transformation pipeline
        
        Args:
            dataset_paths: List of CSV file paths to process
            configuration_id: ID of mapping configuration to use
            options: Processing options
            
        Returns:
            Execution ID for tracking progress
        """
        import uuid
        
        if options is None:
            options = ProcessingOptions()
        
        execution_id = str(uuid.uuid4())
        execution = PipelineExecution(
            id=execution_id,
            configuration_id=configuration_id,
            start_time=time.time(),
            end_time=None,
            total_status=ProcessingStatus.RUNNING,
            phase_results=[],
            input_datasets=dataset_paths,
            output_location=None,
            summary={}
        )
        
        self._executions[execution_id] = execution
        
        try:
            # Get configuration
            config = self.mapping_config.get_configuration(configuration_id)
            if not config:
                raise ValueError(f"Configuration {configuration_id} not found")
            
            # Define processing phases
            phases = [
                ProcessingPhase.ANALYSIS,
                ProcessingPhase.ENTITY_CREATION,
                ProcessingPhase.RELATIONSHIP_MAPPING,
                ProcessingPhase.VALIDATION,
                ProcessingPhase.OUTPUT_GENERATION,
            ]
            
            # Process each phase
            context = {
                'datasets': {},
                'entities': {},
                'relationships': [],
                'validation_errors': [],
                'output_triples': [],
            }
            
            for phase in phases:
                logger.info(f"Starting phase {phase.value} for execution {execution_id}")
                
                phase_result = self._execute_phase(
                    phase, context, dataset_paths, config, options
                )
                
                execution.phase_results.append(phase_result)
                
                if phase_result.status == ProcessingStatus.FAILED and not options.continue_on_errors:
                    execution.total_status = ProcessingStatus.FAILED
                    break
            
            # Complete execution
            if execution.total_status == ProcessingStatus.RUNNING:
                execution.total_status = ProcessingStatus.COMPLETED
            
            execution.end_time = time.time()
            execution.summary = self._generate_execution_summary(execution, context)
            
            logger.info(f"Pipeline execution {execution_id} completed with status {execution.total_status.value}")
            
        except Exception as e:
            logger.error(f"Pipeline execution {execution_id} failed: {str(e)}")
            execution.total_status = ProcessingStatus.FAILED
            execution.end_time = time.time()
            
            # Add error to last phase result or create one
            if execution.phase_results:
                execution.phase_results[-1].errors.append(str(e))
            else:
                error_result = ProcessingResult(
                    phase=ProcessingPhase.ANALYSIS,
                    status=ProcessingStatus.FAILED,
                    start_time=execution.start_time,
                    end_time=time.time(),
                    input_count=0,
                    output_count=0,
                    errors=[str(e)],
                    warnings=[],
                    metadata={}
                )
                execution.phase_results.append(error_result)
        
        return execution_id
    
    def _execute_phase(self, phase: ProcessingPhase, context: Dict[str, Any], 
                      dataset_paths: List[str], config, options: ProcessingOptions) -> ProcessingResult:
        """Execute a single processing phase"""
        start_time = time.time()
        
        try:
            processor = self._phase_processors[phase]
            result = processor(context, dataset_paths, config, options)
            result.start_time = start_time
            result.end_time = time.time()
            
            logger.info(f"Phase {phase.value} completed: {result.input_count} input, {result.output_count} output")
            
            return result
            
        except Exception as e:
            logger.error(f"Phase {phase.value} failed: {str(e)}")
            return ProcessingResult(
                phase=phase,
                status=ProcessingStatus.FAILED,
                start_time=start_time,
                end_time=time.time(),
                input_count=0,
                output_count=0,
                errors=[str(e)],
                warnings=[],
                metadata={}
            )
    
    def _process_analysis_phase(self, context: Dict[str, Any], dataset_paths: List[str], 
                              config, options: ProcessingOptions) -> ProcessingResult:
        """Process analysis phase - analyze all input datasets"""
        analysis_results = {}
        total_input = 0
        errors = []
        
        try:
            for dataset_path in dataset_paths:
                try:
                    analysis = self.table_analysis.analyze_csv(dataset_path)
                    analysis_results[dataset_path] = analysis
                    total_input += analysis.row_count
                    
                except Exception as e:
                    error_msg = f"Failed to analyze {dataset_path}: {str(e)}"
                    errors.append(error_msg)
                    logger.error(error_msg)
            
            context['datasets'] = analysis_results
            
            return ProcessingResult(
                phase=ProcessingPhase.ANALYSIS,
                status=ProcessingStatus.COMPLETED if not errors else ProcessingStatus.FAILED,
                start_time=0,  # Will be set by caller
                end_time=None,  # Will be set by caller
                input_count=len(dataset_paths),
                output_count=len(analysis_results),
                errors=errors,
                warnings=[],
                metadata={
                    'analyzed_datasets': list(analysis_results.keys()),
                    'total_rows': total_input
                }
            )
            
        except Exception as e:
            return ProcessingResult(
                phase=ProcessingPhase.ANALYSIS,
                status=ProcessingStatus.FAILED,
                start_time=0,
                end_time=None,
                input_count=len(dataset_paths),
                output_count=0,
                errors=[str(e)],
                warnings=[],
                metadata={}
            )
    
    def _process_entity_creation_phase(self, context: Dict[str, Any], dataset_paths: List[str], 
                                     config, options: ProcessingOptions) -> ProcessingResult:
        """Process entity creation phase"""
        created_entities = {}
        total_input = 0
        total_output = 0
        errors = []
        warnings = []
        
        try:
            for dataset_path in dataset_paths:
                if dataset_path not in context['datasets']:
                    warnings.append(f"No analysis found for {dataset_path}, skipping")
                    continue
                
                analysis = context['datasets'][dataset_path]
                
                # Read dataset with polars
                df = pl.read_csv(dataset_path)
                total_input += len(df)
                
                # Process each row to create entities
                dataset_entities = {}
                
                for row_data in df.iter_rows(named=True):
                    try:
                        if not options.dry_run:
                            entity_data = self._create_entities_from_row(row_data, analysis, config, options.dry_run)
                            if entity_data:
                                for entity_id, entity_info in entity_data.items():
                                    dataset_entities[entity_id] = entity_info
                                    total_output += 1
                        else:
                            # For dry run, just count potential entities
                            total_output += 1
                            
                    except Exception as e:
                        error_msg = f"Failed to create entity from row: {str(e)}"
                        errors.append(error_msg)
                        
                created_entities[dataset_path] = dataset_entities
            
            context['entities'] = created_entities
            
            return ProcessingResult(
                phase=ProcessingPhase.ENTITY_CREATION,
                status=ProcessingStatus.COMPLETED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=total_output,
                errors=errors,
                warnings=warnings,
                metadata={
                    'entities_per_dataset': {path: len(entities) for path, entities in created_entities.items()}
                }
            )
            
        except Exception as e:
            return ProcessingResult(
                phase=ProcessingPhase.ENTITY_CREATION,
                status=ProcessingStatus.FAILED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=0,
                errors=[str(e)],
                warnings=warnings,
                metadata={}
            )
    
    def _process_relationship_mapping_phase(self, context: Dict[str, Any], dataset_paths: List[str], 
                                          config, options: ProcessingOptions) -> ProcessingResult:
        """Process relationship mapping phase"""
        relationships = []
        total_input = sum(len(entities) for entities in context.get('entities', {}).values())
        total_output = 0
        errors = []
        warnings = []
        
        try:
            # Get relationship templates from configuration
            relationship_templates = config.get('relationship_templates', [])
            
            for dataset_path in dataset_paths:
                if dataset_path not in context['datasets']:
                    continue
                    
                analysis = context['datasets'][dataset_path]
                
                # Find applicable relationship templates
                applicable_templates = self._find_applicable_relationship_templates(analysis, relationship_templates)
                
                if not applicable_templates:
                    warnings.append(f"No relationship templates found for {dataset_path}")
                    continue
                
                # Read dataset again for relationship creation
                df = pl.read_csv(dataset_path)
                
                for row_data in df.iter_rows(named=True):
                    for template in applicable_templates:
                        try:
                            relationship = self._create_relationship_from_template(
                                row_data, template, context, options.dry_run
                            )
                            if relationship:
                                relationships.append(relationship)
                                total_output += 1
                                
                        except Exception as e:
                            error_msg = f"Failed to create relationship from template {template.get('name', 'unknown')}: {str(e)}"
                            errors.append(error_msg)
            
            context['relationships'] = relationships
            
            return ProcessingResult(
                phase=ProcessingPhase.RELATIONSHIP_MAPPING,
                status=ProcessingStatus.COMPLETED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=total_output,
                errors=errors,
                warnings=warnings,
                metadata={
                    'relationship_count': len(relationships),
                    'templates_used': len([t for t in relationship_templates if t])
                }
            )
            
        except Exception as e:
            return ProcessingResult(
                phase=ProcessingPhase.RELATIONSHIP_MAPPING,
                status=ProcessingStatus.FAILED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=0,
                errors=[str(e)],
                warnings=warnings,
                metadata={}
            )
    
    def _process_validation_phase(self, context: Dict[str, Any], dataset_paths: List[str], 
                                config, options: ProcessingOptions) -> ProcessingResult:
        """Process validation phase"""
        validation_errors = []
        total_entities = sum(len(entities) for entities in context.get('entities', {}).values())
        total_relationships = len(context.get('relationships', []))
        total_input = total_entities + total_relationships
        
        try:
            if options.validate_during_processing:
                # Validate entities
                for dataset_path, entities in context.get('entities', {}).items():
                    for entity_id, entity_data in entities.items():
                        validation_result = self.validation.validate_entity(entity_data)
                        if validation_result.get('errors'):
                            validation_errors.extend(validation_result['errors'])
                
                # Validate relationships
                for relationship in context.get('relationships', []):
                    validation_result = self.validation.validate_relationship(relationship)
                    if validation_result.get('errors'):
                        validation_errors.extend(validation_result['errors'])
            
            context['validation_errors'] = validation_errors
            
            return ProcessingResult(
                phase=ProcessingPhase.VALIDATION,
                status=ProcessingStatus.COMPLETED if not validation_errors else ProcessingStatus.FAILED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=total_input - len(validation_errors),
                errors=validation_errors,
                warnings=[],
                metadata={
                    'entities_validated': total_entities,
                    'relationships_validated': total_relationships,
                    'validation_errors_count': len(validation_errors)
                }
            )
            
        except Exception as e:
            return ProcessingResult(
                phase=ProcessingPhase.VALIDATION,
                status=ProcessingStatus.FAILED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=0,
                errors=[str(e)],
                warnings=[],
                metadata={}
            )
    
    def _process_output_generation_phase(self, context: Dict[str, Any], dataset_paths: List[str], 
                                       config, options: ProcessingOptions) -> ProcessingResult:
        """Process output generation phase"""
        output_triples = []
        total_input = 0
        errors = []
        
        try:
            # Generate triples from entities
            for dataset_path, entities in context.get('entities', {}).items():
                total_input += len(entities)
                for entity_id, entity_data in entities.items():
                    try:
                        entity_triples = self._generate_entity_triples(entity_data)
                        output_triples.extend(entity_triples)
                    except Exception as e:
                        errors.append(f"Failed to generate triples for entity {entity_id}: {str(e)}")
            
            # Generate triples from relationships
            relationships = context.get('relationships', [])
            total_input += len(relationships)
            for relationship in relationships:
                try:
                    relationship_triples = self._generate_relationship_triples(relationship)
                    output_triples.extend(relationship_triples)
                except Exception as e:
                    errors.append(f"Failed to generate relationship triples: {str(e)}")
            
            context['output_triples'] = output_triples
            
            return ProcessingResult(
                phase=ProcessingPhase.OUTPUT_GENERATION,
                status=ProcessingStatus.COMPLETED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=len(output_triples),
                errors=errors,
                warnings=[],
                metadata={
                    'triples_generated': len(output_triples),
                    'output_format': options.output_format
                }
            )
            
        except Exception as e:
            return ProcessingResult(
                phase=ProcessingPhase.OUTPUT_GENERATION,
                status=ProcessingStatus.FAILED,
                start_time=0,
                end_time=None,
                input_count=total_input,
                output_count=0,
                errors=[str(e)],
                warnings=[],
                metadata={}
            )
    
    def _create_entities_from_row(self, row_data: Dict[str, Any], analysis, config, dry_run: bool) -> Dict[str, Any]:
        """Create entities from a single row of data"""
        entities = {}
        
        # Get entity creation rules from config
        entity_rules = config.get('entity_rules', [])
        
        for rule in entity_rules:
            for col_name, value in row_data.items():
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue
                
                # Check if rule applies to this column/value
                if self._rule_matches_column(rule, col_name, str(value)):
                    entity_id = self._generate_entity_id(str(value), rule)
                    
                    if not dry_run:
                        entities[entity_id] = {
                            'id': entity_id,
                            'type': rule.get('target_type'),
                            'source_value': str(value),
                            'source_column': col_name,
                            'metadata': {
                                'rule_id': rule.get('id'),
                                'confidence': rule.get('confidence', 1.0)
                            }
                        }
        
        return entities
    
    def _rule_matches_column(self, rule: Dict[str, Any], col_name: str, value: str) -> bool:
        """Check if a rule matches a column name and/or value"""
        # For now, simple implementation - can be extended
        pattern_type = rule.get('pattern_type', 'contains')
        pattern_value = rule.get('pattern_value', '')
        
        if pattern_type == 'prefix':
            return value.startswith(pattern_value)
        elif pattern_type == 'suffix':
            return value.endswith(pattern_value)
        elif pattern_type == 'contains':
            return pattern_value in value
        elif pattern_type == 'column_name':
            return pattern_value in col_name
        
        return False
    
    def _find_applicable_relationship_templates(self, analysis, templates: List) -> List:
        """Find relationship templates that apply to the analyzed table"""
        applicable = []
        
        for template in templates:
            # Check if template conditions match the table
            if template.get('table_type') == analysis.table_type:
                applicable.append(template)
            elif analysis.table_type == 'junction' and template.get('handles_junction_tables', False):
                applicable.append(template)
        
        return applicable
    
    def _create_relationship_from_template(self, row_data: Dict[str, Any], template, context: Dict[str, Any], dry_run: bool) -> Optional[Dict[str, Any]]:
        """Create a relationship from a template and row data"""
        
        source_column = template.get('source_column')
        target_column = template.get('target_column')
        
        if not source_column or not target_column:
            return None
        
        source_value = row_data.get(source_column)
        target_value = row_data.get(target_column)
        
        if source_value is None or target_value is None:
            return None
        
        # Resolve entity IDs
        source_entity_id = self._resolve_entity_id(str(source_value), template.get('source_type'), context)
        target_entity_id = self._resolve_entity_id(str(target_value), template.get('target_type'), context)
        
        if not source_entity_id or not target_entity_id:
            return None
        
        if not dry_run:
            return {
                'source_entity': source_entity_id,
                'target_entity': target_entity_id,
                'predicate': template.get('predicate'),
                'metadata': {
                    'template_id': template.get('id'),
                    'source_value': str(source_value),
                    'target_value': str(target_value)
                }
            }
        
        return {'dry_run': True}
    
    def _generate_entity_id(self, value: str, rule) -> str:
        """Generate a unique entity ID based on value and rule"""
        prefix = rule.get('id_prefix', 'entity')
        # Simple implementation - could use UUID or more sophisticated schemes
        safe_value = value.replace(' ', '_').replace('/', '_')
        return f"{prefix}:{safe_value}"
    
    def _resolve_entity_id(self, value: str, entity_type: str, context: Dict[str, Any]) -> Optional[str]:
        """Resolve a value to an existing entity ID"""
        # Look through created entities
        for dataset_entities in context.get('entities', {}).values():
            for entity_id, entity_data in dataset_entities.items():
                if entity_data.get('source_value') == value and entity_data.get('type') == entity_type:
                    return entity_id
        
        return None
    
    def _generate_entity_triples(self, entity_data: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        """Generate RDF triples for an entity"""
        triples = []
        
        entity_id = entity_data['id']
        entity_type = entity_data.get('type')
        
        # Type triple
        if entity_type:
            triples.append((entity_id, 'rdf:type', entity_type))
        
        # Label triple
        source_value = entity_data.get('source_value')
        if source_value:
            triples.append((entity_id, 'rdfs:label', f'"{source_value}"'))
        
        return triples
    
    def _generate_relationship_triples(self, relationship: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        """Generate RDF triples for a relationship"""
        triples = []
        
        source = relationship.get('source_entity')
        predicate = relationship.get('predicate')
        target = relationship.get('target_entity')
        
        if source and predicate and target:
            triples.append((source, predicate, target))
        
        return triples
    
    def _serialize_output(self, triples: List[Tuple[str, str, str]], format: str) -> str:
        """Serialize triples to specified format"""
        if format == 'turtle':
            lines = []
            for s, p, o in triples:
                lines.append(f"{s} {p} {o} .")
            return '\n'.join(lines)
        elif format == 'ntriples':
            lines = []
            for s, p, o in triples:
                lines.append(f"<{s}> <{p}> <{o}> .")
            return '\n'.join(lines)
        else:
            # Default to simple format
            return str(triples)
    
    def _generate_execution_summary(self, execution: PipelineExecution, context: Dict[str, Any]) -> Dict[str, Any]:
        """Generate summary of execution results"""
        total_entities = sum(len(entities) for entities in context.get('entities', {}).values())
        total_relationships = len(context.get('relationships', []))
        total_triples = len(context.get('output_triples', []))
        total_errors = sum(len(result.errors) for result in execution.phase_results)
        
        return {
            'execution_time': execution.end_time - execution.start_time if execution.end_time else None,
            'total_phases': len(execution.phase_results),
            'successful_phases': len([r for r in execution.phase_results if r.status == ProcessingStatus.COMPLETED]),
            'total_entities_created': total_entities,
            'total_relationships_created': total_relationships,
            'total_triples_generated': total_triples,
            'total_errors': total_errors,
            'datasets_processed': len(execution.input_datasets),
            'final_status': execution.total_status.value
        }
    
    def get_execution_status(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Get current status of an execution"""
        execution = self._executions.get(execution_id)
        if not execution:
            return None
        
        return {
            'id': execution.id,
            'status': execution.total_status.value,
            'start_time': execution.start_time,
            'end_time': execution.end_time,
            'current_phase': execution.phase_results[-1].phase.value if execution.phase_results else None,
            'progress': len(execution.phase_results) / 5 * 100,  # 5 total phases
            'summary': execution.summary
        }
    
    def get_execution_details(self, execution_id: str) -> Optional[PipelineExecution]:
        """Get full details of an execution"""
        return self._executions.get(execution_id)
    
    def list_executions(self) -> List[Dict[str, Any]]:
        """List all executions with basic info"""
        return [
            {
                'id': execution.id,
                'status': execution.total_status.value,
                'start_time': execution.start_time,
                'end_time': execution.end_time,
                'datasets': len(execution.input_datasets)
            }
            for execution in self._executions.values()
        ] 