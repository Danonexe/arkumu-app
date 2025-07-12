import json
import logging
from typing import List, Dict, Any, Tuple, Optional
from django.contrib.auth import get_user_model
from arkumu.metadata.models.mappings import Mapping
from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService

logger = logging.getLogger(__name__)
User = get_user_model()


class MappingImportService:
    """
    Service for importing mapping definitions from JSON files stored in S3 metadata/ folder.
    """
    
    def __init__(self, s3_service: Optional[S3UploadService] = None):
        """
        Initialize the mapping import service.
        
        Args:
            s3_service: Optional S3 service instance. If None, creates a new one.
        """
        self.s3_service = s3_service or S3UploadService()
    
    def list_available_mapping_files(self, organization_id: str) -> List[Dict[str, Any]]:
        """
        List JSON files in S3 metadata/ folder for the given organization.
        
        Args:
            organization_id: Organization identifier
            
        Returns:
            List of file metadata dictionaries
        """
        try:
            # List objects in the metadata/ folder for this organization
            prefix = f"{organization_id}/metadata/"
            
            response = self.s3_service.s3_client.list_objects_v2(
                Bucket=self.s3_service.bucket_name,
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
        
        Args:
            file_content: Raw JSON file content as string
            
        Returns:
            Tuple of (is_valid, error_message, parsed_data)
        """
        try:
            # Parse JSON
            data = json.loads(file_content)
            
            # Check required fields
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
            config_str = json.dumps(data['mapping_config'])
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
            mapping = Mapping.objects.create(
                name=json_data['name'],
                description=json_data.get('description', ''),
                organization_id=organization_id,
                source_datasets=json_data.get('source_datasets', []),
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
                # Download file content from S3
                response = self.s3_service.s3_client.get_object(
                    Bucket=self.s3_service.bucket_name,
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
                    results['imported_mappings'].append(mapping)
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
    
    def download_file_content(self, file_key: str) -> Tuple[bool, str]:
        """
        Download file content from S3.
        
        Args:
            file_key: S3 object key
            
        Returns:
            Tuple of (success, content_or_error_message)
        """
        try:
            response = self.s3_service.s3_client.get_object(
                Bucket=self.s3_service.bucket_name,
                Key=file_key
            )
            content = response['Body'].read().decode('utf-8')
            return True, content
        except Exception as e:
            error_msg = f"Error downloading file {file_key}: {str(e)}"
            logger.error(error_msg)
            return False, error_msg