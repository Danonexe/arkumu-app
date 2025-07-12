import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from django.contrib.auth import get_user_model
from arkumu.metadata.models.mappings import Mapping
from arkumu.storage.services.base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)
User = get_user_model()


class MappingImportService:
    """
    Service for importing mapping definitions from JSON files stored in S3 metadata/ folder.
    """
    
    def __init__(self, storage_service: Optional[BaseStorageService] = None):
        """
        Initialize the mapping import service.
        
        Args:
            storage_service: Optional storage service instance. If None, creates a new one.
        """
        self.storage_service = storage_service or BaseStorageService()
    
    def list_available_mapping_files(self, organization_id: str) -> List[Dict[str, Any]]:
        """
        List JSON files in S3 metadata/ folder for the given organization.
        
        Args:
            organization_id: Organization identifier (organization code)
            
        Returns:
            List of file metadata dictionaries
        """
        try:
            # List objects in the metadata/ folder in the organization's production bucket
            # The bucket name is the organization code, and files are in metadata/ directory
            bucket_name = organization_id  # Use organization code as bucket name
            prefix = "metadata/"
            
            response = self.storage_service.s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=prefix
            )
            
            files = []
            if 'Contents' in response:
                for obj in response['Contents']:
                    key = obj['Key']
                    # Only include .json files
                    if key.endswith('.json'):
                        file_info = {
                            'key': key,
                            'name': key.split('/')[-1],  # Just the filename
                            'size': obj['Size'],
                            'last_modified': obj['LastModified'].isoformat(),
                            'display_name': key.split('/')[-1].replace('.json', '').replace('_', ' ').title()
                        }
                        files.append(file_info)
            
            # Sort by last modified (newest first)
            files.sort(key=lambda x: x['last_modified'], reverse=True)
            
            logger.info(f"Found {len(files)} mapping files for organization {organization_id}")
            return files
            
        except Exception as e:
            logger.error(f"Error listing mapping files for organization {organization_id}: {str(e)}")
            return []
    
    def validate_mapping_file(self, file_content: str) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        """
        Validate JSON structure and required fields for a mapping file.
        Supports both new format and existing workspace export format.
        
        Args:
            file_content: Raw JSON file content as string
            
        Returns:
            Tuple of (is_valid, error_message, parsed_data)
        """
        try:
            # Parse JSON
            data = json.loads(file_content)
            
            # Detect format type
            is_workspace_export = ('entity_mappings' in data and 'workspace_datasets' in data 
                                 and 'version' in data and 'metadata' in data)
            
            if is_workspace_export:
                # Validate workspace export format
                if not isinstance(data.get('metadata'), dict):
                    return False, "Workspace export must have metadata object", None
                
                # Generate name from metadata or fallback
                mapping_name = None
                if isinstance(data['metadata'], dict):
                    mapping_name = data['metadata'].get('mapping_name')
                
                if not mapping_name:
                    # Generate name from creation date
                    created_at = data.get('created_at', 'unknown')
                    org_id = data.get('organization_id', 'unknown')
                    mapping_name = f"{org_id.upper()} Mapping ({created_at[:10]})"
                
                # Normalize to expected format
                # Note: source_datasets is derived from mapping_config['workspace_datasets'] - don't set it independently
                normalized_data = {
                    'name': mapping_name,
                    'description': f"Imported workspace mapping with {data['metadata'].get('total_datasets', 0)} datasets",
                    'mapping_config': {
                        'entity_mappings': data.get('entity_mappings', {}),
                        'workspace_datasets': data.get('workspace_datasets', []),
                        'workspace_columns': data.get('workspace_columns', {}),
                        'fk_relationships': data.get('fk_relationships', {}),
                        'relationship_contexts': data.get('relationship_contexts', {}),
                        'external_ontologies': data.get('external_ontologies', {}),
                        'version': data.get('version'),
                        'original_metadata': data.get('metadata', {})
                    },
                    # Don't set source_datasets - it will be computed from mapping_config
                    'metadata': {
                        'imported_from': 'workspace_export',
                        'original_created_at': data.get('created_at'),
                        'original_exported_by': data.get('exported_by'),
                        'export_timestamp': data.get('export_timestamp')
                    }
                }
                
                return True, "Valid workspace export file", normalized_data
                
            else:
                # Validate new format
                required_fields = ['name', 'mapping_config']
                missing_fields = [field for field in required_fields if field not in data]
                
                if missing_fields:
                    return False, f"Missing required fields: {', '.join(missing_fields)}", None
                
                # Validate data types
                if not isinstance(data['name'], str) or not data['name'].strip():
                    return False, "Field 'name' must be a non-empty string", None
                
                if not isinstance(data['mapping_config'], dict):
                    return False, "Field 'mapping_config' must be a dictionary", None
                
                # Optional field validation
                if 'description' in data and not isinstance(data['description'], str):
                    return False, "Field 'description' must be a string", None
                
                if 'source_datasets' in data and not isinstance(data['source_datasets'], list):
                    return False, "Field 'source_datasets' must be a list", None
                
                # Check file size (mapping_config shouldn't be too large)
                config_str = json.dumps(data.get('mapping_config', {}))
                if len(config_str) > 1024 * 1024:  # 1MB limit
                    return False, "Mapping configuration is too large (>1MB)", None
                
                return True, "Valid mapping file", data
            
        except json.JSONDecodeError as e:
            return False, f"Invalid JSON format: {str(e)}", None
        except Exception as e:
            return False, f"Validation error: {str(e)}", None
    
    def import_mapping_from_json(self, json_data: Dict[str, Any], organization_id: str, created_by: User) -> Tuple[bool, str, Optional[Mapping]]:
        """
        Create a Mapping object from validated JSON data.
        
        Args:
            json_data: Validated JSON data
            organization_id: Organization identifier
            created_by: User who is importing the mapping
            
        Returns:
            Tuple of (success, message, mapping_object)
        """
        try:
            # Check for name conflicts within organization
            existing_mapping = Mapping.objects.filter(
                organization_id=organization_id,
                name=json_data['name']
            ).first()
            
            if existing_mapping:
                # Generate a unique name
                base_name = json_data['name']
                counter = 1
                while existing_mapping:
                    new_name = f"{base_name} (Imported {counter})"
                    existing_mapping = Mapping.objects.filter(
                        organization_id=organization_id,
                        name=new_name
                    ).first()
                    if not existing_mapping:
                        json_data['name'] = new_name
                        break
                    counter += 1
            
            # Create the mapping object
            # Note: During transition, populate source_datasets from mapping_config['workspace_datasets']
            workspace_datasets = json_data['mapping_config'].get('workspace_datasets', [])
            mapping = Mapping.objects.create(
                name=json_data['name'],
                description=json_data.get('description', ''),
                organization_id=organization_id,
                source_datasets=workspace_datasets,  # Populate from mapping_config during transition
                mapping_config=json_data['mapping_config'],
                created_by=created_by,
                validation_status='draft'  # Always import as draft
            )
            
            logger.info(f"Successfully imported mapping '{mapping.name}' for organization {organization_id}")
            return True, f"Successfully imported mapping '{mapping.name}'", mapping
            
        except Exception as e:
            error_msg = f"Error creating mapping: {str(e)}"
            logger.error(error_msg)
            return False, error_msg, None
    
    def batch_import_mappings(self, file_keys: List[str], organization_id: str, created_by: User) -> Dict[str, Any]:
        """
        Import multiple mapping files.
        
        Args:
            file_keys: List of S3 object keys to import
            organization_id: Organization identifier
            created_by: User who is importing the mappings
            
        Returns:
            Dictionary with import results
        """
        results = {
            'total_files': len(file_keys),
            'successful_imports': [],
            'failed_imports': [],
            'imported_mappings': []
        }
        
        for file_key in file_keys:
            try:
                # Extract bucket name from file key (organization/path format)
                bucket_name = organization_id  # Use organization code as bucket name
                
                # Download file content from S3
                response = self.storage_service.s3_client.get_object(
                    Bucket=bucket_name,
                    Key=file_key
                )
                file_content = response['Body'].read().decode('utf-8')
                
                # Validate the file
                is_valid, validation_message, json_data = self.validate_mapping_file(file_content)
                
                if not is_valid:
                    results['failed_imports'].append({
                        'file': file_key,
                        'error': validation_message
                    })
                    continue
                
                # Import the mapping
                success, import_message, mapping = self.import_mapping_from_json(
                    json_data, organization_id, created_by
                )
                
                if success and mapping:
                    results['successful_imports'].append({
                        'file': file_key,
                        'mapping_name': mapping.name,
                        'mapping_id': str(mapping.id)
                    })
                    # Store just the mapping metadata, not the actual object for JSON serialization
                    results['imported_mappings'].append({
                        'id': str(mapping.id),
                        'name': mapping.name,
                        'description': mapping.description or '',
                        'created_at': mapping.created_at.isoformat() if mapping.created_at else None
                    })
                else:
                    results['failed_imports'].append({
                        'file': file_key,
                        'error': import_message
                    })
                    
            except Exception as e:
                error_msg = f"Error processing file {file_key}: {str(e)}"
                logger.error(error_msg)
                results['failed_imports'].append({
                    'file': file_key,
                    'error': error_msg
                })
        
        # Log summary
        logger.info(f"Batch import completed: {len(results['successful_imports'])} successful, "
                   f"{len(results['failed_imports'])} failed out of {results['total_files']} total files")
        
        return results
    
    def download_file_content(self, file_key: str, organization_id: str) -> Tuple[bool, str]:
        """
        Download file content from S3.
        
        Args:
            file_key: S3 object key
            organization_id: Organization identifier for bucket name
            
        Returns:
            Tuple of (success, content_or_error_message)
        """
        try:
            bucket_name = organization_id  # Use organization code as bucket name
            response = self.storage_service.s3_client.get_object(
                Bucket=bucket_name,
                Key=file_key
            )
            content = response['Body'].read().decode('utf-8')
            return True, content
        except Exception as e:
            error_msg = f"Error downloading file {file_key}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg