import json
import os
import logging
from typing import Dict, List

from arkumu.importer.services.importer.importer import JSONMappingImporter
from arkumu.importer.services.validation.validation import validate_mapping

# Setup logger
logger = logging.getLogger(__name__)


class ManifestError(Exception):
    """Exception for manifest validation errors"""
    pass


class ImportManifest:
    """Parser and validator for import manifest files"""
    
    REQUIRED_MANIFEST_FIELDS = ["imports"]
    REQUIRED_IMPORT_FIELDS = ["mapping", "data"]
    
    def __init__(self, manifest_file_path: str):
        """
        Initialize with the path to a manifest file
        
        Args:
            manifest_file_path: Path to the manifest JSON file
        """
        self.manifest_file_path = manifest_file_path
        self.manifest_dir = os.path.dirname(os.path.abspath(manifest_file_path))
        self.manifest_data = None
        self.imports = []
        
        self._load_and_validate()
    
    def _load_and_validate(self):
        """Load and validate the manifest file"""
        if not os.path.exists(self.manifest_file_path):
            raise ManifestError(f"Manifest file not found: {self.manifest_file_path}")
        
        try:
            with open(self.manifest_file_path, 'r') as f:
                self.manifest_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestError(f"Invalid JSON in manifest file: {e}")
        
        self._validate_structure()
        self._prepare_imports()
    
    def _validate_structure(self):
        """Validate the structure of the manifest file"""
        for field in self.REQUIRED_MANIFEST_FIELDS:
            if field not in self.manifest_data:
                raise ManifestError(f"Required field '{field}' missing from manifest")
        
        if not isinstance(self.manifest_data['imports'], list):
            raise ManifestError("'imports' must be a list")
        
        if len(self.manifest_data['imports']) == 0:
            raise ManifestError("Import list is empty")
        
        # Validate each import entry
        for i, import_def in enumerate(self.manifest_data['imports']):
            self._validate_import_entry(import_def, i)
    
    def _validate_import_entry(self, import_def: Dict, index: int):
        """Validate a single import entry"""
        for field in self.REQUIRED_IMPORT_FIELDS:
            if field not in import_def:
                raise ManifestError(f"Required field '{field}' missing from import #{index+1}")
        
        # Check that the files exist (resolve relative paths)
        mapping_path = self._resolve_path(import_def['mapping'])
        data_path = self._resolve_path(import_def['data'])
        
        if not os.path.exists(mapping_path):
            raise ManifestError(f"Mapping file not found: {mapping_path} in import #{index+1}")
        
        if not os.path.exists(data_path):
            raise ManifestError(f"Data file not found: {data_path} in import #{index+1}")
    
    def _resolve_path(self, file_path: str) -> str:
        """Resolve relative paths against the manifest directory"""
        if os.path.isabs(file_path):
            return file_path
        else:
            return os.path.join(self.manifest_dir, file_path)
    
    def _prepare_imports(self):
        """Prepare the imports list with resolved paths"""
        self.imports = []
        for import_def in self.manifest_data['imports']:
            import_item = import_def.copy()
            import_item['mapping'] = self._resolve_path(import_def['mapping'])
            import_item['data'] = self._resolve_path(import_def['data'])
            
            # Set default name if not provided
            if 'name' not in import_item:
                import_item['name'] = os.path.basename(import_item['mapping'])
            
            self.imports.append(import_item)
    
    def get_global_options(self) -> Dict:
        """Get global options from the manifest"""
        # Return empty dict if global_options not present
        return self.manifest_data.get('global_options', {})
    
    def get_imports(self) -> List[Dict]:
        """Get the list of imports with resolved paths"""
        return self.imports
    
    def get_import_count(self) -> int:
        """Get the number of imports in the manifest"""
        return len(self.imports)


class ImportOrchestrator:
    """
    Orchestrator for executing multiple imports based on a manifest
    
    The orchestrator coordinates the execution of multiple imports in a specified
    sequence, handling validation, pre-loading related data, and collecting results.
    """
    
    def __init__(self, manifest_file_path: str):
        """
        Initialize with a manifest file
        
        Args:
            manifest_file_path: Path to the manifest file
        """
        logger.info(f"Initializing ImportOrchestrator with manifest: {manifest_file_path}")
        self.manifest = ImportManifest(manifest_file_path)
        self.global_options = self.manifest.get_global_options()
        self.imports = self.manifest.get_imports()
        
        self.results = []
        self.current_index = 0
        self.total_count = self.manifest.get_import_count()
        
        logger.info(f"Loaded {self.total_count} imports from manifest")
    
    def validate_all(self) -> bool:
        """
        Pre-validate all imports in the manifest
        
        Returns:
            bool: True if all imports validated successfully, False otherwise
        """
        logger.info(f"Pre-validating all {self.total_count} imports...")
        all_valid = True
        validation_results = []
        
        for i, import_def in enumerate(self.imports):
            name = import_def['name']
            mapping_file = import_def['mapping']
            data_file = import_def['data']
            
            logger.info(f"[{i+1}/{self.total_count}] Validating '{name}'...")
            
            try:
                # Use the validation module directly for pre-validation
                # Default to strict_references=True unless explicitly set to False
                strict = import_def.get('options', {}).get('strict_references', 
                         self.global_options.get('strict_references', True))
                
                report = validate_mapping(
                    mapping_file=mapping_file,
                    csv_file=data_file,
                    strict=strict,
                    print_output=False
                )
                
                is_valid = report.is_valid
                if not is_valid:
                    all_valid = False
                    logger.error(f"Validation failed for '{name}': {report.summary()}")
                else:
                    logger.info(f"Validation passed for '{name}'")
                
                validation_results.append({
                    "name": name,
                    "valid": is_valid,
                    "report": report
                })
                
            except Exception as e:
                all_valid = False
                logger.error(f"Error validating '{name}': {str(e)}")
                validation_results.append({
                    "name": name,
                    "valid": False,
                    "error": str(e)
                })
        
        self.validation_results = validation_results
        return all_valid
    
    def execute(self) -> List[Dict]:
        """
        Execute all imports in sequence
        
        Returns:
            List[Dict]: Results of each import
        """
        self.results = []
        
        # Check if we should validate all first (default to True for safety)
        validate_all_first = self.global_options.get('validate_all_first', True)
        if validate_all_first:
            logger.info("Validating all imports before execution")
            all_valid = self.validate_all()
            if not all_valid:
                logger.error("Pre-validation failed, aborting all imports")
                return self.get_summary()
        
        # Execute each import in sequence
        for i, import_def in enumerate(self.imports):
            self.current_index = i
            
            name = import_def['name']
            mapping_file = import_def['mapping']
            data_file = import_def['data']
            options = import_def.get('options', {})
            
            logger.info(f"[{i+1}/{self.total_count}] Executing import '{name}'...")
            
            try:
                import_result = self._execute_single_import(name, mapping_file, data_file, options)
                self.results.append(import_result)
                
                # Check if import was successful
                if not import_result['success']:
                    logger.error(f"Import '{name}' failed")
                    
                    # Check if we should abort on failure (default to True for safety)
                    abort_on_failure = self.global_options.get('abort_on_failure', True)
                    if abort_on_failure:
                        logger.error("Aborting remaining imports due to failure")
                        break
                else:
                    logger.info(f"Import '{name}' completed successfully")
                    
            except Exception as e:
                logger.exception(f"Error executing import '{name}': {str(e)}")
                self.results.append({
                    "name": name,
                    "success": False,
                    "error": str(e),
                    "mapping_file": mapping_file,
                    "data_file": data_file
                })
                
                # Check if we should abort on failure (default to True for safety)
                abort_on_failure = self.global_options.get('abort_on_failure', True)
                if abort_on_failure:
                    logger.error("Aborting remaining imports due to exception")
                    break
        
        # Return summary results
        return self.get_summary()
    
    def _execute_single_import(self, name: str, mapping_file: str, data_file: str, 
                              options: Dict) -> Dict:
        """Execute a single import operation"""
        import_result = {
            "name": name,
            "mapping_file": mapping_file,
            "data_file": data_file
        }
        
        try:
            # Initialize the importer
            # Default to strict_references=True unless explicitly set to False
            strict_references = options.get('strict_references', 
                               self.global_options.get('strict_references', True))
            
            importer = JSONMappingImporter(
                mapping_file,
                institution_base_uri=options.get('institution_base_uri'),
                strict_references=strict_references
            )
            
            # Read the CSV data
            from arkumu.importer.services.data_utils import read_csv_with_nfc
            
            # Get delimiter from mapping (default to semicolon)
            with open(mapping_file, 'r') as f:
                mapping_data = json.load(f)
            
            # Check both new column_delimiter and legacy csv_settings
            delimiter = mapping_data.get('column_delimiter', ';')  # Default to semicolon
            if 'csv_settings' in mapping_data:
                delimiter = mapping_data['csv_settings'].get('delimiter', delimiter)
            
            csv_data = read_csv_with_nfc(data_file, delimiter=delimiter)
            
            # Perform the import
            validate_first = not self.global_options.get('validate_all_first', False)
            import_stats = importer.import_data(
                source_data_iterator=csv_data,
                primary_subject_class_short_name=mapping_data.get('domain'),
                strict_references=strict_references,
                validate_first=validate_first,
                csv_file_path=data_file,
                apply_nfc=options.get('apply_nfc', True)
            )
            
            # Process results
            success = import_stats.get('successful_rows', 0) > 0 and import_stats.get('failed_rows', 0) == 0
            import_result["success"] = success
            import_result["stats"] = import_stats
            
        except Exception as e:
            logger.exception(f"Exception during import execution: {e}")
            import_result["success"] = False
            import_result["error"] = str(e)
        
        return import_result
    
    def get_summary(self) -> Dict:
        """
        Get a summary of all import results
        
        Returns:
            Dict: Summary statistics
        """
        successful_imports = sum(1 for r in self.results if r.get('success', False))
        failed_imports = len(self.results) - successful_imports
        
        # Collect statistics from successful imports
        total_rows = 0
        successful_rows = 0
        failed_rows = 0
        
        for result in self.results:
            if result.get('success', False) and 'stats' in result:
                stats = result['stats']
                total_rows += stats.get('total_rows', 0)
                successful_rows += stats.get('successful_rows', 0)
                failed_rows += stats.get('failed_rows', 0)
        
        return {
            "total_imports": self.total_count,
            "executed_imports": len(self.results),
            "successful_imports": successful_imports,
            "failed_imports": failed_imports,
            "total_rows": total_rows,
            "successful_rows": successful_rows,
            "failed_rows": failed_rows,
            "detailed_results": self.results
        }


def orchestrate_imports(manifest_file_path: str, validate_only: bool = False) -> Dict:
    """
    Orchestrate multiple imports based on a manifest file
    
    Args:
        manifest_file_path: Path to the manifest file
        validate_only: If True, only perform validation without importing
        
    Returns:
        Dict: Summary of import results
    """
    logger.info(f"Orchestrating imports from manifest: {manifest_file_path}")
    
    try:
        orchestrator = ImportOrchestrator(manifest_file_path)
        
        if validate_only:
            logger.info("Validation-only mode")
            all_valid = orchestrator.validate_all()
            return {
                "validation_only": True,
                "validation_passed": all_valid,
                "detailed_results": getattr(orchestrator, 'validation_results', [])
            }
        else:
            # Execute imports and return the summary
            return orchestrator.execute()
            
    except ManifestError as e:
        logger.error(f"Manifest validation error: {str(e)}")
        return {
            "success": False,
            "error": f"Manifest validation error: {str(e)}",
            "error_type": "manifest_validation"
        }
    except Exception as e:
        logger.exception(f"Error orchestrating imports: {str(e)}")
        return {
            "success": False,
            "error": f"Orchestration error: {str(e)}",
            "error_type": "orchestration"
        }
