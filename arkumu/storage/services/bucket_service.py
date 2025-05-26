import logging
import os
from typing import Any, Dict, List
import tempfile
from pathlib import Path

from botocore.exceptions import ClientError
from django.conf import settings
import boto3

from .base_storage_service import BaseStorageService
from .upload_service import UploadService

# Import metadata models for direct access
from arkumu.metadata.models.resource import Resource
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)


class BucketService(BaseStorageService):
    """
    Primary service for interacting with S3/MinIO buckets in Arkumu.
    
    This service provides a simplified approach for institution-based file organization
    and basic metadata management.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(BucketService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the BucketService with all required sub-services.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done
        if hasattr(self, 'initialized'):
            return
            
        super().__init__(skip_bucket_check=skip_bucket_check)
        
        # Initialize the upload service with skip_bucket_check=True
        self.upload_service = UploadService(skip_bucket_check=True)
        
        # Configure child services with consistent settings
        self.set_client_and_buckets(self.upload_service)
        
        logger.info("BucketService initialized")
        self.initialized = True
    
    def get_institutions(self) -> List[str]:
        """
        Get a list of all institution folders in the production bucket.
        
        Returns:
            List[str]: A list of institution names
        """
        try:
            # List all objects with delimiter to identify top-level prefixes
            response = self.s3_client.list_objects_v2(
                Bucket=self.production_bucket,
                Delimiter='/'
            )
            
            institutions = []
            
            # Process CommonPrefixes (folders)
            for prefix in response.get('CommonPrefixes', []):
                # Extract institution name by removing the trailing slash
                institution_name = prefix.get('Prefix', '').rstrip('/')
                if institution_name:
                    institutions.append(institution_name)
            
            return institutions
        except Exception as e:
            logger.error(f"Error getting institutions: {str(e)}")
            return []
    
    def list_institution_contents(self, institution: str, prefix: str = "") -> List[Dict[str, Any]]:
        """
        List contents within an institution folder.
        
        Args:
            institution (str): The institution name
            prefix (str): Additional path prefix within the institution
            
        Returns:
            List[Dict[str, Any]]: List of files and folders
        """
        try:
            # Ensure institution path ends with slash
            institution_path = f"{institution}/"
            
            # Combine with additional prefix if provided
            if prefix:
                # Remove leading slash if present
                clean_prefix = prefix.lstrip('/')
                full_prefix = f"{institution_path}{clean_prefix}"
                
                # Ensure full prefix ends with slash
                if not full_prefix.endswith('/'):
                    full_prefix += '/'
            else:
                full_prefix = institution_path
            
            logger.info(f"Listing contents for institution '{institution}' with prefix '{full_prefix}'")
            
            # List objects with the full prefix
            response = self.s3_client.list_objects_v2(
                Bucket=self.production_bucket,
                Prefix=full_prefix,
                Delimiter='/'
            )
            
            results = []
            
            # Process CommonPrefixes (folders)
            for prefix_obj in response.get('CommonPrefixes', []):
                folder_path = prefix_obj.get('Prefix', '')
                folder_name = folder_path.rstrip('/').split('/')[-1]
                
                results.append({
                    "type": "folder",
                    "name": folder_name,
                    "path": folder_path,
                })
            
            # Process Contents (files)
            for content in response.get('Contents', []):
                file_path = content.get('Key', '')
                
                # Skip if this is just the directory marker
                if file_path == full_prefix:
                    continue
                    
                file_name = file_path.split('/')[-1]
                file_size = content.get('Size', 0)
                last_modified = content.get('LastModified', '')
                
                results.append({
                    "type": "file",
                    "name": file_name,
                    "path": file_path,
                    "size": file_size,
                    "last_modified": last_modified,
                })
            
            return results
        except Exception as e:
            logger.error(f"Error listing institution contents: {str(e)}")
            return []
    
    def create_institution(self, institution_name: str) -> Dict[str, Any]:
        """
        Create a new institution folder in the production bucket.
        
        Args:
            institution_name (str): The name of the institution to create
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        try:
            # Sanitize institution name (remove spaces, special chars, etc.)
            clean_name = institution_name.strip().replace(' ', '_')
            
            # Ensure the institution name is valid
            if not clean_name:
                return {
                    "success": False,
                    "error": "Institution name cannot be empty"
                }
            
            # Check if institution already exists
            existing_institutions = self.get_institutions()
            if clean_name in existing_institutions:
                return {
                    "success": False,
                    "error": f"Institution '{clean_name}' already exists"
                }
            
            # Create an empty directory marker for the institution
            institution_path = f"{clean_name}/"
            self.s3_client.put_object(
                Bucket=self.production_bucket,
                Key=institution_path,
                Body=''
            )
            
            logger.info(f"Created institution folder: {institution_path}")
            
            return {
                "success": True,
                "message": f"Institution '{clean_name}' created successfully",
                "institution_name": clean_name,
                "path": institution_path
            }
        except Exception as e:
            logger.error(f"Error creating institution: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_root_level_items(self, bucket_name: str) -> Dict[str, Any]:
        """
        Get only the root level items (files and folders) from a bucket.
        This is optimized for the initial dashboard load.
        
        Args:
            bucket_name (str): The name of the bucket to list
            
        Returns:
            Dict[str, Any]: Dictionary containing root level items
        """
        try:
            # List objects with delimiter to get root-level items
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name,
                Delimiter='/'
            )
            
            children = []
            
            # Process CommonPrefixes (folders)
            for prefix in response.get('CommonPrefixes', []):
                folder_path = prefix.get('Prefix', '')
                folder_name = folder_path.rstrip('/').split('/')[-1]
                
                children.append({
                    "type": "folder",
                    "name": folder_name,
                    "path": folder_path,
                })
            
            # Process Contents (files)
            for content in response.get('Contents', []):
                file_path = content.get('Key', '')
                
                # Skip folder markers
                if file_path.endswith('/'):
                    continue
                    
                # Only include root-level files (no slashes in path)
                if '/' not in file_path:
                    file_name = file_path
                    file_size = content.get('Size', 0)
                    last_modified = content.get('LastModified', '')
                    
                    children.append({
                        "type": "file",
                        "name": file_name,
                        "path": file_path,
                        "size": file_size,
                        "last_modified": last_modified,
                    })
            
            return {
                "type": "folder",
                "name": bucket_name,
                "path": "",
                "children": children
            }
        except Exception as e:
            logger.error(f"Error getting root level items for bucket '{bucket_name}': {str(e)}")
            return {"type": "folder", "name": bucket_name, "path": "", "children": []}
    
    def get_folder_contents(self, bucket_name: str, folder_path: str) -> List[Dict[str, Any]]:
        """
        Get the contents of a specific folder.
        This is used for lazy loading folder contents.
        
        Args:
            bucket_name (str): The name of the bucket
            folder_path (str): The path to the folder
            
        Returns:
            List[Dict[str, Any]]: List of items in the folder
        """
        try:
            # Ensure folder_path ends with a slash
            if folder_path and not folder_path.endswith('/'):
                folder_path = folder_path + '/'
            
            # List objects with the folder prefix
            response = self.s3_client.list_objects_v2(
                Bucket=bucket_name,
                Prefix=folder_path,
                Delimiter='/'
            )
            
            results = []
            
            # Process CommonPrefixes (folders)
            for prefix_obj in response.get('CommonPrefixes', []):
                sub_folder_path = prefix_obj.get('Prefix', '')
                folder_name = sub_folder_path.rstrip('/').split('/')[-1]
                
                results.append({
                    "type": "folder",
                    "name": folder_name,
                    "path": sub_folder_path,
                })
            
            # Process Contents (files)
            for content in response.get('Contents', []):
                file_path = content.get('Key', '')
                
                # Skip if this is just the directory marker
                if file_path == folder_path:
                    continue
                    
                file_name = file_path.split('/')[-1]
                file_size = content.get('Size', 0)
                last_modified = content.get('LastModified', '')
                
                results.append({
                    "type": "file",
                    "name": file_name,
                    "path": file_path,
                    "size": file_size,
                    "last_modified": last_modified,
                })
            
            return results
        except Exception as e:
            logger.error(f"Error getting folder contents for '{folder_path}' in bucket '{bucket_name}': {str(e)}")
            return []
    
    def move_to_production(self, institution: str, source_prefix: str) -> Dict[str, Any]:
        """
        Move a folder from the ingest bucket to the production bucket.
        
        Args:
            institution (str): The institution name to place files under
            source_prefix (str): The path in the ingest bucket to move
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        logger.info(f"Starting move to production for {source_prefix} under institution {institution}")
        
        try:
            # Verify ingest and production buckets are different
            if self.ingest_bucket == self.production_bucket:
                error_message = "Error: Ingest and production buckets must be different"
                logger.error(error_message)
                return {
                    "success": False,
                    "error": error_message
                }
            
            # Ensure source_prefix ends with a slash for proper prefix matching
            if not source_prefix.endswith('/'):
                source_prefix = source_prefix + '/'
                logger.info(f"Added trailing slash for proper prefix matching: {source_prefix}")
            
            # Create destination prefix with institution
            dest_prefix = f"{institution}/{source_prefix}"
            
            # List all objects in the source
            paginator = self.s3_client.get_paginator("list_objects_v2")
            copied_files = 0
            
            for page in paginator.paginate(Bucket=self.ingest_bucket, Prefix=source_prefix):
                for obj in page.get("Contents", []):
                    source_key = obj["Key"]
                    
                    # Skip if this is just the folder marker object
                    if source_key == source_prefix:
                        logger.info(f"Skipping folder marker object: {source_key}")
                        continue
                    
                    # Create destination key, preserving the subfolder structure
                    # but placing it under the institution folder
                    relative_path = source_key[len(source_prefix):]
                    dest_key = f"{institution}/{relative_path}"
                    
                    # Copy the object to the production bucket
                    self.s3_client.copy_object(
                        CopySource={"Bucket": self.ingest_bucket, "Key": source_key},
                        Bucket=self.production_bucket,
                        Key=dest_key
                    )
                    
                    copied_files += 1
                    
                    if copied_files % 10 == 0:
                        logger.info(f"Copied {copied_files} files so far...")
            
            # Add an empty directory marker if no files were found
            if copied_files == 0:
                logger.warning(f"No files found to copy, creating an empty directory marker: {dest_prefix}")
                self.s3_client.put_object(
                    Bucket=self.production_bucket,
                    Key=dest_prefix,
                    Body=''
                )
                copied_files = 1
            
            if copied_files > 0:
                logger.info(f"Successfully copied {copied_files} files to {dest_prefix}")
                return {
                    "success": True,
                    "message": f"Successfully moved {source_prefix} to {institution} in production bucket ({copied_files} files copied)"
                }
            else:
                # This should never happen now due to the empty directory marker
                logger.warning(f"No files found to copy at {source_prefix}")
                return {
                    "success": False,
                    "error": f"No files found to copy at {source_prefix}"
                }
                
        except Exception as e:
            logger.error(f"Error in move_to_production: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _format_size(self, size_bytes: int) -> str:
        """Format bytes to human-readable size"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"

    def delete_folder(self, bucket_name, folder_path):
        """
        Delete a folder and all its contents from the specified bucket.
        
        Args:
            bucket_name: The name of the bucket
            folder_path: Path to the folder to delete
        
        Returns:
            dict: Result of the operation with success flag and error message if applicable
        """
        return self.delete_object(bucket_name, folder_path, is_directory=True)
        
    def delete_file(self, bucket_name, file_path):
        """
        Delete a single file from the specified bucket.
        
        Args:
            bucket_name: The name of the bucket
            file_path: Path to the file to delete
        
        Returns:
            dict: Result of the operation with success flag and error message if applicable
        """
        return self.delete_object(bucket_name, file_path, is_directory=False)
        
    def update_file_metadata(self, institution: str, file_path: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Update or create metadata for a file.
        
        Args:
            institution (str): The institution name
            file_path (str): Path to the file
            metadata (Dict[str, Any]): Metadata to associate with the file
            
        Returns:
            Dict[str, Any]: Result of the operation
        """
        try:
            # Get or create a resource for the file
            full_path = f"{institution}/{file_path}"
            
            # Create a file resource URI using the full path
            file_uri = f"file://{full_path}"
            
            # Get or create the file resource
            file_resource, created = Resource.objects.get_or_create(
                uri=file_uri,
                defaults={
                    'resource_type': 'IRI',
                    'name': file_path.split('/')[-1],
                    'source': institution
                }
            )
            
            # Process metadata and create triples
            triples_created = 0
            for key, value in metadata.items():
                # Get or create predicate resource
                predicate, _ = Resource.objects.get_or_create(
                    uri=f"property:{key}",
                    defaults={
                        'resource_type': 'PROPERTY',
                        'name': key,
                        'source': 'system'
                    }
                )
                
                # Create object resource based on value type
                if isinstance(value, dict) and 'uri' in value:
                    # Handle IRI values
                    object_resource, _ = Resource.objects.get_or_create(
                        uri=value['uri'],
                        defaults={
                            'resource_type': 'IRI',
                            'name': value.get('name', ''),
                            'source': value.get('source', 'external')
                        }
                    )
                else:
                    # Handle literal values
                    object_resource, _ = Resource.objects.get_or_create(
                        value=str(value),
                        resource_type='LITERAL',
                        name=key,
                        source=institution,
                        defaults={
                            'datatype': metadata.get('datatype', None),
                            'language': metadata.get('language', None)
                        }
                    )
                
                # Create the triple
                triple, created = Triple.objects.get_or_create(
                    subject=file_resource,
                    predicate=predicate,
                    object=object_resource
                )
                
                if created:
                    triples_created += 1
            
            return {
                "success": True,
                "file_resource_id": str(file_resource.id),
                "triples_created": triples_created,
                "message": f"Metadata updated for {full_path}"
            }
            
        except Exception as e:
            logger.error(f"Error updating file metadata: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_file_metadata(self, institution: str, file_path: str) -> Dict[str, Any]:
        """
        Get metadata for a file.
        
        Args:
            institution (str): The institution name
            file_path (str): Path to the file
            
        Returns:
            Dict[str, Any]: File metadata
        """
        try:
            # Create the file URI
            full_path = f"{institution}/{file_path}"
            file_uri = f"file://{full_path}"
            
            # Try to find the file resource
            try:
                file_resource = Resource.objects.get(uri=file_uri)
            except Resource.DoesNotExist:
                return {
                    "success": False,
                    "error": f"No metadata found for {full_path}"
                }
            
            # Get all triples where this resource is the subject
            triples = Triple.objects.filter(subject=file_resource)
            
            metadata = {
                "id": str(file_resource.id),
                "uri": file_resource.uri,
                "name": file_resource.name,
                "source": file_resource.source,
                "properties": {}
            }
            
            # Process triples into a metadata dictionary
            for triple in triples:
                predicate_name = triple.predicate.name
                
                # Handle different object types
                if triple.object.resource_type == 'LITERAL':
                    # For literals, just use the value
                    value = triple.object.value
                    
                    # Add datatype or language if present
                    if triple.object.datatype:
                        # Store complex structure for typed literals
                        metadata["properties"][predicate_name] = {
                            "value": value,
                            "datatype": triple.object.datatype
                        }
                    elif triple.object.language:
                        # Store complex structure for language tagged literals
                        metadata["properties"][predicate_name] = {
                            "value": value,
                            "language": triple.object.language
                        }
                    else:
                        # Store simple value for plain literals
                        metadata["properties"][predicate_name] = value
                else:
                    # For IRIs, include the URI and other relevant info
                    metadata["properties"][predicate_name] = {
                        "uri": triple.object.uri,
                        "name": triple.object.name,
                        "type": triple.object.resource_type
                    }
            
            return {
                "success": True,
                "metadata": metadata
            }
            
        except Exception as e:
            logger.error(f"Error getting file metadata: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }

