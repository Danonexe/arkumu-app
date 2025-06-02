import boto3
import logging
from typing import List, Tuple, Dict, Any
from django.contrib.auth import get_user_model
from django.db import transaction

from arkumu.storage.models import S3FileObject, UploadSession
from arkumu.storage.services.bucket_service import BucketService
from arkumu.storage.services.base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)


class S3SyncService:
    """Service for synchronizing S3 files with database records."""

    def __init__(self):
        self.bucket_service = BucketService()
        # Use BaseStorageService singleton for properly configured S3 client
        self.base_storage_service = BaseStorageService()
        logger.info(f"S3SyncService initialized using BaseStorageService with endpoint: {self.base_storage_service.endpoint_url}")

    def sync_bucket(self, bucket_name: str, prefix: str = 'data/', dry_run: bool = False) -> Dict[str, int]:
        """
        Sync a single bucket with database records.
        
        Args:
            bucket_name: Name of the S3 bucket to sync
            prefix: S3 key prefix to filter files (default: 'data/')
            dry_run: If True, only return what would be created without creating records
            
        Returns:
            Dict with sync statistics: {'found_in_s3', 'existing_in_db', 'missing', 'created'}
        """
        logger.info(f"Starting sync for bucket: {bucket_name}, prefix: {prefix}")
        
        try:
            # Get S3 files
            s3_files = self._get_s3_files(bucket_name, prefix)
            logger.info(f"Found {len(s3_files)} files in S3")
            
            # Get existing database records
            existing_keys = set(
                S3FileObject.objects.filter(
                    session__s3_bucket=bucket_name,
                    s3_key__startswith=prefix
                ).values_list('s3_key', flat=True)
            )
            logger.info(f"Found {len(existing_keys)} existing database records")
            
            # Find missing files
            missing_files = [
                file_info for file_info in s3_files 
                if file_info['Key'] not in existing_keys
            ]
            
            logger.info(f"Found {len(missing_files)} missing database records")
            
            created_count = 0
            if not dry_run and missing_files:
                created_count = self._create_missing_records(bucket_name, missing_files)
                logger.info(f"Created {created_count} new S3FileObject records")
            
            return {
                'found_in_s3': len(s3_files),
                'existing_in_db': len(existing_keys),
                'missing': len(missing_files),
                'created': created_count
            }
            
        except Exception as e:
            logger.error(f"Error syncing bucket {bucket_name}: {str(e)}")
            raise

    def sync_all_buckets(self, prefix: str = 'data/', dry_run: bool = False) -> Dict[str, Dict[str, int]]:
        """
        Sync all predefined organization buckets.
        
        Args:
            prefix: S3 key prefix to filter files (default: 'data/')
            dry_run: If True, only return what would be created without creating records
            
        Returns:
            Dict with bucket names as keys and sync statistics as values
        """
        buckets = self.bucket_service.get_predefined_organizations()
        results = {}
        
        for bucket_name in buckets:
            try:
                results[bucket_name] = self.sync_bucket(bucket_name, prefix, dry_run)
            except Exception as e:
                logger.error(f"Failed to sync bucket {bucket_name}: {str(e)}")
                results[bucket_name] = {
                    'error': str(e),
                    'found_in_s3': 0,
                    'existing_in_db': 0,
                    'missing': 0,
                    'created': 0
                }
        
        return results

    def get_orphaned_files_count(self, bucket_name: str = None, prefix: str = 'data/') -> int:
        """
        Get count of files that exist in S3 but not in database.
        
        Args:
            bucket_name: Specific bucket to check (if None, checks all buckets)
            prefix: S3 key prefix to filter files
            
        Returns:
            Number of orphaned files
        """
        if bucket_name:
            buckets = [bucket_name]
        else:
            buckets = self.bucket_service.get_predefined_organizations()
        
        total_orphaned = 0
        
        for bucket in buckets:
            try:
                sync_result = self.sync_bucket(bucket, prefix, dry_run=True)
                total_orphaned += sync_result['missing']
            except Exception as e:
                logger.error(f"Error checking orphaned files in bucket {bucket}: {str(e)}")
        
        return total_orphaned

    def _get_s3_files(self, bucket_name: str, prefix: str) -> List[Dict[str, Any]]:
        """Get list of files from S3 bucket with given prefix."""
        files = []
        # Use the properly configured S3 client from BaseStorageService
        paginator = self.base_storage_service.s3_client.get_paginator('list_objects_v2')
        
        try:
            for page in paginator.paginate(Bucket=bucket_name, Prefix=prefix):
                if 'Contents' in page:
                    files.extend(page['Contents'])
        except Exception as e:
            logger.error(f"Error listing S3 objects in bucket {bucket_name}: {str(e)}")
            raise
        
        return files

    @transaction.atomic
    def _create_missing_records(self, bucket_name: str, missing_files: List[Dict[str, Any]]) -> int:
        """Create S3FileObject records for missing files."""
        placeholder_session = self._get_or_create_placeholder_session(bucket_name)
        
        created_count = 0
        batch_size = 100  # Process in batches for better performance
        
        for i in range(0, len(missing_files), batch_size):
            batch = missing_files[i:i + batch_size]
            objects_to_create = []
            
            for file_info in batch:
                try:
                    obj = S3FileObject(
                        s3_key=file_info['Key'],
                        file_name=file_info['Key'].split('/')[-1],
                        file_size_bytes=file_info['Size'],
                        session=placeholder_session,
                        status='completed',  # Assume existing files are completed
                    )
                    objects_to_create.append(obj)
                except Exception as e:
                    logger.error(f"Failed to prepare record for {file_info['Key']}: {str(e)}")
            
            # Bulk create this batch
            if objects_to_create:
                try:
                    S3FileObject.objects.bulk_create(objects_to_create, ignore_conflicts=True)
                    created_count += len(objects_to_create)
                except Exception as e:
                    logger.error(f"Failed to bulk create batch: {str(e)}")
                    # Fall back to individual creation
                    for obj in objects_to_create:
                        try:
                            obj.save()
                            created_count += 1
                        except Exception as e:
                            logger.error(f"Failed to create record for {obj.s3_key}: {str(e)}")
        
        # Update the placeholder session's file count
        if created_count > 0:
            placeholder_session.total_files += created_count
            placeholder_session.total_size_bytes += sum(f['Size'] for f in missing_files)
            placeholder_session.save()
        
        return created_count

    def _get_or_create_placeholder_session(self, bucket_name: str) -> UploadSession:
        """Get or create a placeholder upload session for orphaned files."""
        User = get_user_model()
        
        # Get or create system user
        system_user, created = User.objects.get_or_create(
            username='system_sync',
            defaults={
                'email': 'system@arkumu.local',
                'name': 'System Sync',
                'is_active': True
            }
        )
        
        if created:
            logger.info("Created system sync user")
        
        # Get or create placeholder session
        session, created = UploadSession.objects.get_or_create(
            user=system_user,
            folder_name=f'sync_orphaned_{bucket_name}',
            s3_bucket=bucket_name,
            defaults={
                'status': 'completed',
                'total_files': 0,
                'total_size_bytes': 0
            }
        )
        
        if created:
            logger.info(f"Created placeholder session for bucket {bucket_name}")
        
        return session 