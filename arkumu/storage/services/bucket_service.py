import logging
import os
import time
import threading
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

# List of predefined organizations (can be moved to settings if dynamic)
PREDEFINED_ORGANIZATIONS = [
    "rsh",
    "khm", 
    "fuk",
    "hmt",
    "det",
]

class BucketService:
    """
    Service for managing organization-specific S3 buckets.
    This service is NOT a singleton. It uses the BaseStorageService singleton for S3 interactions.
    """
    # Remove _instance and _lock, as this is no longer a singleton
    # _instance = None
    # _lock = threading.Lock() # Temporarily commented out lock as part of deadlock diagnosis
    
    # No __new__ method needed anymore

    def __init__(self):
        logger.info("-----> BucketService.__init__ ENTERED")
        # Get the singleton instance of BaseStorageService
        self.base_s3_service = BaseStorageService()
        
        # No longer call super().__init__ as BaseStorageService manages its own initialization.
        # The S3 client and essential bucket info (ingest/production) are available via self.base_s3_service.
        
        # If BucketService needs its own specific initialization that runs only once,
        # an instance flag like self._initialized could be used here.
        # For now, assume most of its state comes from BaseStorageService or is per-method.

        # Initialize UploadService here if it's a direct dependency, passing the base_s3_service instance
        # or letting UploadService get it itself. For now, let's assume UploadService gets it.
        # self.upload_service = UploadService() # Example if needed
        
        # Removed the old complex initialization logic that duplicated BaseStorageService concerns.
        logger.info("-----> BucketService.__init__ COMPLETED. Using BaseStorageService for S3 operations.")

    def _get_organization_bucket_name(self, organization_id: str) -> str:
        return organization_id

    def get_organization_bucket(self, organization_id: str) -> str:
        """Public method to get organization bucket name."""
        return self._get_organization_bucket_name(organization_id)

    def get_predefined_organizations(self) -> List[str]:
        """Get the list of predefined organization IDs."""
        return PREDEFINED_ORGANIZATIONS.copy()

    def get_predefined_organizations_data(self) -> List[Dict[str, str]]:
        """Get predefined organizations with additional data like names."""
        org_names = {
            "rsh": "Robert Schumann Hochschule Düsseldorf",
            "khm": "Kunsthochschule für Medien Köln",
            "fuk": "Folkwang Universität der Künste",
            "hmt": "Hochschule für Musik und Tanz Köln",
            "det": "Hochschule für Musik Detmold",
        }
        
        return [
            {
                "id": org_id,
                "slug": org_id,  # For backwards compatibility
                "name": org_names.get(org_id, f"Organization {org_id.capitalize()}")
            }
            for org_id in PREDEFINED_ORGANIZATIONS
        ]

    def ensure_organization_bucket_exists(self, organization_id: str, check_only: bool = False) -> Dict[str, Any]:
        """
        Ensures an organization-specific bucket exists. 
        Now uses BaseStorageService's ensure_bucket_exists for creation if not check_only.
        If check_only is True, it only checks existence using head_bucket and does not create.
        """
        bucket_name = self._get_organization_bucket_name(organization_id)
        logger.info(f"Ensuring organization bucket: {bucket_name}, check_only={check_only}")
        
        try:
            self.base_s3_service.s3_client.head_bucket(Bucket=bucket_name)
            logger.info(f"✅ Organization bucket '{bucket_name}' already exists.")
            return {"success": True, "bucket_name": bucket_name, "status": "exists"}
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404' or error_code == 'NoSuchBucket':
                logger.info(f"Organization bucket '{bucket_name}' does not exist.")
                if check_only:
                    return {"success": False, "bucket_name": bucket_name, "status": "does_not_exist", "error": "Bucket not found and check_only is True"}
                
                # Attempt to create using BaseStorageService's method
                logger.info(f"Attempting to create organization bucket '{bucket_name}' via BaseStorageService.")
                if self.base_s3_service.ensure_bucket_exists(bucket_name):
                    logger.info(f"✅ Organization bucket '{bucket_name}' created successfully.")
                    return {"success": True, "bucket_name": bucket_name, "status": "created"}
                else:
                    logger.error(f"❌ Failed to create organization bucket '{bucket_name}' via BaseStorageService.")
                    return {"success": False, "bucket_name": bucket_name, "status": "creation_failed", "error": "Failed to create bucket"}
            else:
                logger.error(f"❌ Error checking organization bucket '{bucket_name}': {e.response.get('Error', {})}")
                return {"success": False, "bucket_name": bucket_name, "status": "error", "error": str(e.response.get('Error', {}))}

    def get_available_organizations(self, include_counts: bool = False) -> List[Dict[str, Any]]:
        """
        List available organizations by checking their predefined buckets.
        Uses the check_only=True variant of ensure_organization_bucket_exists.
        Optionally includes item counts (can be slow).
        """
        logger.info(f"Getting available organizations. Include counts: {include_counts}")
        
        # Map organization IDs to proper names
        org_names = {
            "rsh": "Robert Schumann Hochschule Düsseldorf",
            "khm": "Kunsthochschule für Medien Köln",
            "fuk": "Folkwang Universität der Künste",
            "hmt": "Hochschule für Musik und Tanz Köln",
            "det": "Hochschule für Musik Detmold",
        }
        
        organizations_data = []
        for org_id in PREDEFINED_ORGANIZATIONS:
            bucket_name = self._get_organization_bucket_name(org_id)
            org_info = {
                "id": org_id,
                "bucket_name": bucket_name,
                "status": "unknown",
                "name": org_names.get(org_id, f"Organization {org_id.capitalize()}"),
                "file_count": 0, # Initialize counts
                "folder_count": 0,
                "total_size_formatted": "0 B"
            }
            
            # Use check_only=True to only verify existence without attempting creation here.
            # Creation should be an explicit admin action or handled elsewhere if needed.
            check_result = self.ensure_organization_bucket_exists(org_id, check_only=True)
            
            if check_result["success"] or check_result.get("status") == "exists": # Bucket exists
                org_info["status"] = "active"
                if include_counts:
                    logger.info(f"Fetching counts for organization '{org_id}' bucket '{bucket_name}'...")
                    items_data = self.get_root_level_items(org_id, bucket_name)
                    org_info.update(items_data) # file_count, folder_count, total_size_formatted
            elif check_result.get("status") == "does_not_exist":
                org_info["status"] = "inactive_bucket_not_found"
            else: # error or creation_failed (though creation isn't attempted with check_only=True)
                org_info["status"] = "error_checking_bucket"
                org_info["error_details"] = check_result.get("error", "Unknown error")

            organizations_data.append(org_info)
        
        logger.info(f"Found {len(organizations_data)} organizations data.")
        return organizations_data

    def get_root_level_items(self, organization_id: str, bucket_name: str = None) -> Dict[str, Any]:
        """
        Get root level items (files and folders) for an organization's bucket.
        Uses BaseStorageService.s3_client for listing objects.
        """
        if not bucket_name:
            bucket_name = self._get_organization_bucket_name(organization_id)
        
        logger.info(f"Fetching root level items for bucket: {bucket_name}")
        root_items = {"files": [], "folders": [], "file_count": 0, "folder_count": 0, "total_size": 0}
        
        try:
            paginator = self.base_s3_service.s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket_name, Delimiter='/'):
                # Add folders (CommonPrefixes)
                for prefix in page.get('CommonPrefixes', []):
                    folder_name = prefix.get('Prefix')
                    root_items["folders"].append({"name": folder_name, "path": folder_name})
                    root_items["folder_count"] += 1
                
                # Add files (Contents)
                for obj in page.get('Contents', []):
                    if not obj['Key'].endswith('/'): # Ensure it's not a folder object
                        file_size = obj.get('Size', 0)
                        root_items["files"].append({
                            "name": os.path.basename(obj['Key']),
                            "path": obj['Key'],
                            "size": file_size,
                            "size_formatted": self.base_s3_service._format_size(file_size),
                            "last_modified": obj.get('LastModified')
                        })
                        root_items["file_count"] += 1
                        root_items["total_size"] += file_size
            
            root_items["total_size_formatted"] = self.base_s3_service._format_size(root_items["total_size"])
            logger.info(f"Found {root_items['file_count']} files and {root_items['folder_count']} folders in {bucket_name}.")

        except ClientError as e:
            logger.error(f"Error listing root items for bucket {bucket_name}: {e.response.get('Error', {})}")
            # Return empty/zeroed data but log the error
            root_items["error"] = str(e.response.get('Error', {}))
        
        return root_items
    
    # Add other BucketService specific methods here, using self.base_s3_service for S3 ops.
    # For example, methods to manage files within an organization's bucket, etc.

    def delete_organization_bucket_and_contents(self, organization_id: str) -> Dict[str, Any]:
        """Deletes all objects within an organization's bucket and then the bucket itself."""
        bucket_name = self._get_organization_bucket_name(organization_id)
        logger.info(f"Attempting to delete all contents and bucket for organization: {organization_id}, bucket: {bucket_name}")

        # First, delete all objects in the bucket using BaseStorageService
        # The delete_object method in BaseStorageService can handle directory deletion.
        # We list all objects and delete them. A more robust way would be to use list_objects_v2 and DeleteObjects.
        # For simplicity, let's assume BaseStorageService might need a more direct "empty_bucket" or we iterate here.
        
        # Iteratively delete objects (safer for services without direct batch delete)
        try:
            logger.info(f"Listing all objects in bucket {bucket_name} for deletion...")
            paginator = self.base_s3_service.s3_client.get_paginator('list_objects_v2')
            objects_to_delete = []
            for page in paginator.paginate(Bucket=bucket_name):
                if 'Contents' in page:
                    for obj in page['Contents']:
                        objects_to_delete.append({'Key': obj['Key']})
            
            if objects_to_delete:
                logger.info(f"Found {len(objects_to_delete)} objects to delete from {bucket_name}.")
                # S3 DeleteObjects can handle up to 1000 keys at a time
                for i in range(0, len(objects_to_delete), 1000):
                    chunk = objects_to_delete[i:i + 1000]
                    delete_payload = {'Objects': chunk}
                    response = self.base_s3_service.s3_client.delete_objects(
                        Bucket=bucket_name,
                        Delete=delete_payload
                    )
                    deleted_count = len(response.get('Deleted', []))
                    logger.info(f"Batch delete: {deleted_count} objects deleted from {bucket_name}.")
                    errors = response.get('Errors', [])
                    if errors:
                        logger.error(f"Errors during batch delete from {bucket_name}: {errors}")
                        return {"success": False, "error": f"Errors deleting objects: {errors}"}
            else:
                logger.info(f"Bucket {bucket_name} is already empty.")

            # After emptying, delete the bucket itself
            logger.info(f"Attempting to delete bucket: {bucket_name}")
            self.base_s3_service.s3_client.delete_bucket(Bucket=bucket_name)
            logger.info(f"✅ Successfully deleted bucket {bucket_name}.")
            return {"success": True, "message": f"Bucket {bucket_name} and all its contents deleted."}

        except ClientError as e:
            logger.error(f"Error during deletion of bucket {bucket_name} or its contents: {e.response.get('Error', {})}")
            return {"success": False, "error": str(e.response.get('Error', {}))}
        except Exception as e:
            logger.error(f"Unexpected error during deletion of bucket {bucket_name}: {str(e)}")
            return {"success": False, "error": str(e)}

    def list_bucket_contents(self, bucket_name: str, prefix: str = "") -> List[Dict[str, Any]]:
        """
        List contents of a bucket with optional prefix.
        Returns a list of file/folder items compatible with the views.
        """
        logger.info(f"Listing contents for bucket: {bucket_name}, prefix: {prefix}")
        
        try:
            contents = []
            paginator = self.base_s3_service.s3_client.get_paginator('list_objects_v2')
            
            # Set up pagination parameters
            paginate_kwargs = {'Bucket': bucket_name, 'Delimiter': '/'}
            if prefix:
                paginate_kwargs['Prefix'] = prefix
            
            for page in paginator.paginate(**paginate_kwargs):
                # Add folders (CommonPrefixes)
                for prefix_obj in page.get('CommonPrefixes', []):
                    folder_path = prefix_obj.get('Prefix', '')
                    folder_name = folder_path.rstrip('/').split('/')[-1]
                    contents.append({
                        "name": folder_name,
                        "path": folder_path,
                        "is_dir": True,
                        "type": "folder"
                    })
                
                # Add files (Contents)
                for obj in page.get('Contents', []):
                    if not obj['Key'].endswith('/'):  # Ensure it's not a folder object
                        file_name = obj['Key'].split('/')[-1]
                        file_size = obj.get('Size', 0)
                        contents.append({
                            "name": file_name,
                            "path": obj['Key'],
                            "is_dir": False,
                            "type": "file",
                            "size": file_size,
                            "size_formatted": self.base_s3_service._format_size(file_size),
                            "last_modified": obj.get('LastModified')
                        })
            
            logger.info(f"Found {len(contents)} items in bucket {bucket_name} with prefix '{prefix}'")
            return contents
            
        except ClientError as e:
            logger.error(f"Error listing bucket contents for {bucket_name}: {e.response.get('Error', {})}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error listing bucket contents for {bucket_name}: {str(e)}")
            return []

