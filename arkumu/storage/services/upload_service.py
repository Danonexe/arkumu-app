import logging
import time
import os
import json
from typing import Dict, Any, List, Tuple, Set, Optional, IO, Union
from io import BytesIO
import concurrent.futures
from functools import partial

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

from .base_storage_service import BaseStorageService

logger = logging.getLogger(__name__)

class UploadService(BaseStorageService):
    """
    Service for handling file uploads to S3/MinIO buckets via streaming.
    
    This service focuses on streaming file uploads directly from Django to S3,
    avoiding the need for presigned URLs which may not be supported by all S3-compatible
    services. Files are streamed chunk by chunk to avoid memory issues.
    """
    
    _instance = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(UploadService, cls).__new__(cls)
        return cls._instance
    
    def __init__(self, skip_bucket_check=False):
        """
        Initialize the UploadService with base storage configuration.
        
        Args:
            skip_bucket_check (bool): If True, skip bucket existence check
        """
        # Skip initialization if already done (proper singleton pattern)
        if hasattr(self, 'initialized'):
            logger.info("Using cached UploadService instance")
            return
            
        logger.info("Initializing UploadService for the first time...")
        start_time = time.time()
        super().__init__(skip_bucket_check=skip_bucket_check)
        init_duration = time.time() - start_time
        logger.info(f"UploadService initialized for streaming uploads in {init_duration:.2f} seconds")
        self.initialized = True

    def _generate_file_key(self, file_name: str, path_prefix: Optional[str] = None) -> str:
        """
        Generate a clean S3 key (path) for a file.
        
        Args:
            file_name (str): The name of the file
            path_prefix (str, optional): Path prefix to prepend to the file name
            
        Returns:
            str: The generated S3 key
        """
        # Sanitize the file name to work with S3 (replace spaces with underscores)
        clean_file_name = file_name.replace(' ', '_')
        
        # Build the full S3 key (path)
        if path_prefix:
            # Ensure the path has no leading or trailing slashes
            clean_prefix = path_prefix.strip('/')
            if clean_prefix:
                return f"{clean_prefix}/{clean_file_name}"
        
        # Just return the clean file name if no prefix
        return clean_file_name

    def upload_file_stream(self, file_obj: Union[IO, bytes], file_name: str, 
                          content_type: str = 'application/octet-stream',
                          path_prefix: Optional[str] = None, 
                          file_size: Optional[int] = None) -> Dict[str, Any]:
        """
        Upload a file from a file-like object or bytes directly to S3.
        
        Args:
            file_obj: File-like object (Django UploadedFile, BytesIO, etc.) or bytes
            file_name: The name of the file
            content_type: MIME type of the file
            path_prefix: Optional prefix for the S3 key
            file_size: Optional file size (if known)
            
        Returns:
            Dictionary with upload result
        """
        try:
            # Generate S3 key
            s3_key = self._generate_file_key(file_name, path_prefix)
            
            logger.info(f"Uploading file stream {file_name} to {s3_key}")
            
            # Handle bytes input
            if isinstance(file_obj, bytes):
                file_obj = BytesIO(file_obj)
                if file_size is None:
                    file_size = len(file_obj.getvalue())
            
            # Prepare upload arguments
            upload_args = {
                'ContentType': content_type,
            }
            
            # Upload the file
            self.s3_client.upload_fileobj(
                file_obj,
                self.ingest_bucket,
                s3_key,
                ExtraArgs=upload_args
            )
            
            # Verify upload and get file info
            try:
                head_response = self.s3_client.head_object(
                    Bucket=self.ingest_bucket,
                    Key=s3_key
                )
                actual_file_size = head_response.get('ContentLength', 0)
                last_modified = head_response.get('LastModified', None)
                
                logger.info(f"Successfully uploaded {file_name} ({self._format_size(actual_file_size)})")
                
                return {
                    'success': True,
                    'file_name': file_name,
                    's3_key': s3_key,
                    'bucket': self.ingest_bucket,
                    'file_size': actual_file_size,
                    'file_size_formatted': self._format_size(actual_file_size),
                    'content_type': content_type,
                    'last_modified': last_modified.isoformat() if last_modified else None,
                }
            except Exception as verify_error:
                logger.warning(f"Upload succeeded but verification failed for {s3_key}: {verify_error}")
                return {
                    'success': True,
                    'file_name': file_name,
                    's3_key': s3_key,
                    'bucket': self.ingest_bucket,
                    'content_type': content_type,
                    'verification_warning': str(verify_error)
                }
                
        except Exception as e:
            logger.error(f"Error uploading file stream {file_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'file_name': file_name
            }

    def upload_multipart_stream(self, file_obj: Union[IO, bytes], file_name: str,
                               content_type: str = 'application/octet-stream',
                               path_prefix: Optional[str] = None,
                               chunk_size: int = 5 * 1024 * 1024) -> Dict[str, Any]:
        """
        Upload a large file using multipart upload for better reliability and performance.
        
        Args:
            file_obj: File-like object or bytes
            file_name: The name of the file
            content_type: MIME type of the file
            path_prefix: Optional prefix for the S3 key
            chunk_size: Size of each part in bytes (minimum 5MB for S3)
            
        Returns:
            Dictionary with upload result
        """
        try:
            # Generate S3 key
            s3_key = self._generate_file_key(file_name, path_prefix)
            
            logger.info(f"Starting multipart upload for {file_name} to {s3_key}")
            
            # Handle bytes input
            if isinstance(file_obj, bytes):
                file_obj = BytesIO(file_obj)
            
            # Initialize multipart upload
            create_response = self.s3_client.create_multipart_upload(
                Bucket=self.ingest_bucket,
                Key=s3_key,
                ContentType=content_type
            )
            
            upload_id = create_response['UploadId']
            logger.info(f"Multipart upload initialized with ID: {upload_id}")
            
            # Upload parts
            parts = []
            part_number = 1
            total_size = 0
            
            try:
                while True:
                    # Read chunk
                    chunk = file_obj.read(chunk_size)
                    if not chunk:
                        break
                    
                    chunk_size_actual = len(chunk)
                    total_size += chunk_size_actual
                    
                    logger.debug(f"Uploading part {part_number} ({self._format_size(chunk_size_actual)})")
                    
                    # Upload part
                    part_response = self.s3_client.upload_part(
                        Bucket=self.ingest_bucket,
                        Key=s3_key,
                        PartNumber=part_number,
                        UploadId=upload_id,
                        Body=chunk
                    )
                    
                    # Store part info
                    parts.append({
                        'PartNumber': part_number,
                        'ETag': part_response['ETag']
                    })
                    
                    part_number += 1
                
                # Complete multipart upload
                complete_response = self.s3_client.complete_multipart_upload(
                    Bucket=self.ingest_bucket,
                    Key=s3_key,
                    UploadId=upload_id,
                    MultipartUpload={'Parts': parts}
                )
                
                logger.info(f"Multipart upload completed for {file_name} ({self._format_size(total_size)}, {len(parts)} parts)")
                
                # Verify upload
                try:
                    head_response = self.s3_client.head_object(
                        Bucket=self.ingest_bucket,
                        Key=s3_key
                    )
                    actual_file_size = head_response.get('ContentLength', 0)
                    last_modified = head_response.get('LastModified', None)
                    
                    return {
                        'success': True,
                        'file_name': file_name,
                        's3_key': s3_key,
                        'bucket': self.ingest_bucket,
                        'file_size': actual_file_size,
                        'file_size_formatted': self._format_size(actual_file_size),
                        'content_type': content_type,
                        'upload_type': 'multipart',
                        'parts_count': len(parts),
                        'etag': complete_response.get('ETag', '').strip('"'),
                        'last_modified': last_modified.isoformat() if last_modified else None,
                    }
                except Exception as verify_error:
                    logger.warning(f"Multipart upload succeeded but verification failed for {s3_key}: {verify_error}")
                    return {
                        'success': True,
                        'file_name': file_name,
                        's3_key': s3_key,
                        'bucket': self.ingest_bucket,
                        'content_type': content_type,
                        'upload_type': 'multipart',
                        'parts_count': len(parts),
                        'etag': complete_response.get('ETag', '').strip('"'),
                        'verification_warning': str(verify_error)
                    }
                    
            except Exception as upload_error:
                # Abort multipart upload on error
                logger.error(f"Error during multipart upload, aborting: {upload_error}")
                try:
                    self.s3_client.abort_multipart_upload(
                        Bucket=self.ingest_bucket,
                        Key=s3_key,
                        UploadId=upload_id
                    )
                    logger.info(f"Multipart upload {upload_id} aborted")
                except Exception as abort_error:
                    logger.error(f"Failed to abort multipart upload {upload_id}: {abort_error}")
                
                raise upload_error
                
        except Exception as e:
            logger.error(f"Error in multipart upload for {file_name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'file_name': file_name
            }

    def upload_django_file(self, uploaded_file, path_prefix: Optional[str] = None, 
                          use_multipart: bool = True, 
                          multipart_threshold: int = 10 * 1024 * 1024) -> Dict[str, Any]:
        """
        Upload a Django UploadedFile object to S3.
        
        Args:
            uploaded_file: Django UploadedFile object
            path_prefix: Optional prefix for the S3 key
            use_multipart: Whether to use multipart upload for large files
            multipart_threshold: File size threshold for multipart upload (default 10MB)
            
        Returns:
            Dictionary with upload result
        """
        try:
            file_name = uploaded_file.name
            content_type = getattr(uploaded_file, 'content_type', 'application/octet-stream')
            file_size = getattr(uploaded_file, 'size', None)
            
            logger.info(f"Uploading Django file {file_name} (size: {self._format_size(file_size) if file_size else 'unknown'})")
            
            # Decide whether to use multipart upload
            if use_multipart and file_size and file_size > multipart_threshold:
                logger.info(f"Using multipart upload for large file {file_name}")
                return self.upload_multipart_stream(
                    uploaded_file,
                    file_name,
                    content_type,
                    path_prefix
                )
            else:
                logger.info(f"Using single-part upload for file {file_name}")
                return self.upload_file_stream(
                    uploaded_file,
                    file_name,
                    content_type,
                    path_prefix,
                    file_size
                )
                
        except Exception as e:
            logger.error(f"Error uploading Django file {uploaded_file.name}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'file_name': getattr(uploaded_file, 'name', 'unknown')
            }

    def upload_batch_django_files(self, uploaded_files: List, 
                                 path_prefix: Optional[str] = None,
                                 use_multipart: bool = True,
                                 multipart_threshold: int = 10 * 1024 * 1024) -> Dict[str, Any]:
        """
        Upload multiple Django UploadedFile objects to S3.
        
        Args:
            uploaded_files: List of Django UploadedFile objects
            path_prefix: Optional prefix for all S3 keys
            use_multipart: Whether to use multipart upload for large files
            multipart_threshold: File size threshold for multipart upload
            
        Returns:
            Dictionary with batch upload results
        """
        results = []
        failures = []
        total_size = 0
        
        logger.info(f"Starting batch upload of {len(uploaded_files)} files")
        
        for uploaded_file in uploaded_files:
            try:
                result = self.upload_django_file(
                    uploaded_file,
                    path_prefix,
                    use_multipart,
                    multipart_threshold
                )
                
                if result['success']:
                    results.append(result)
                    file_size = result.get('file_size', 0)
                    total_size += file_size
                    logger.info(f"Successfully uploaded {result['file_name']}")
                else:
                    failures.append({
                        'file_name': result.get('file_name', 'unknown'),
                        'error': result.get('error', 'Unknown error')
                    })
                    logger.error(f"Failed to upload {result.get('file_name')}: {result.get('error')}")
                    
            except Exception as e:
                file_name = getattr(uploaded_file, 'name', 'unknown')
                logger.error(f"Exception during upload of {file_name}: {str(e)}")
                failures.append({
                    'file_name': file_name,
                    'error': str(e)
                })
        
        success_count = len(results)
        failure_count = len(failures)
        
        logger.info(f"Batch upload completed: {success_count} succeeded, {failure_count} failed, total size: {self._format_size(total_size)}")
        
        return {
            'success': failure_count == 0,
            'results': results,
            'failures': failures,
            'total_uploaded': success_count,
            'total_failed': failure_count,
            'total_size': total_size,
            'total_size_formatted': self._format_size(total_size)
        }

    def get_file_info(self, s3_key: str) -> Dict[str, Any]:
        """
        Get information about an uploaded file in S3.
        
        Args:
            s3_key (str): The S3 key for the file
            
        Returns:
            Dict[str, Any]: Dictionary containing file information or error information
        """
        try:
            # Check if the file exists in S3
            response = self.s3_client.head_object(
                Bucket=self.ingest_bucket,
                Key=s3_key
            )
            
            file_size = response.get('ContentLength', 0)
            content_type = response.get('ContentType', 'application/octet-stream')
            last_modified = response.get('LastModified', None)
            etag = response.get('ETag', '').strip('"')
            
            return {
                'success': True,
                's3_key': s3_key,
                'exists': True,
                'file_size': file_size,
                'file_size_formatted': self._format_size(file_size),
                'content_type': content_type,
                'last_modified': last_modified.isoformat() if last_modified else None,
                'etag': etag
            }
            
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return {
                    'success': True,
                    's3_key': s3_key,
                    'exists': False
                }
            else:
                logger.error(f"Error getting file info for {s3_key}: {str(e)}")
                return {
                    'success': False,
                    'error': str(e),
                    's3_key': s3_key,
                    'exists': False
                }
        except Exception as e:
            logger.error(f"Error getting file info for {s3_key}: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                's3_key': s3_key,
                'exists': False
            }

    def _format_size(self, size_bytes: int) -> str:
        """
        Format a size in bytes to a human-readable format.
        
        Args:
            size_bytes (int): Size in bytes
            
        Returns:
            str: Formatted size string
        """
        # Define size units
        units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
        size = float(size_bytes)
        unit_index = 0
        
        # Find the appropriate unit
        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1
        
        # Format with proper precision
        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        else:
            return f"{size:.2f} {units[unit_index]}"

    # Legacy methods for backward compatibility (these will now redirect to streaming)
    def generate_presigned_post(self, file_name: str, file_type: str, path_prefix: Optional[str] = None, 
                             expiration: int = 3600, use_multipart: bool = True, part_count: int = 10) -> Dict[str, Any]:
        """
        Legacy method - presigned URLs are no longer supported.
        This method returns an error indicating that streaming upload should be used instead.
        """
        logger.warning(f"Presigned URL requested for {file_name}, but presigned URLs are disabled. Use streaming upload instead.")
        return {
            'success': False,
            'error': 'Presigned URLs are not supported. Please use the streaming upload endpoint instead.',
            'file_name': file_name,
            'alternative': 'Use upload_django_file() or upload_file_stream() methods'
        }

    def generate_batch_presigned_posts(self, files_metadata: List[Dict[str, str]], 
                                    path_prefix: Optional[str] = None,
                                    expiration: int = 3600,
                                    use_multipart: bool = True,
                                    part_count: int = 10) -> Dict[str, Any]:
        """
        Legacy method - presigned URLs are no longer supported.
        This method returns an error indicating that streaming upload should be used instead.
        """
        logger.warning(f"Batch presigned URLs requested for {len(files_metadata)} files, but presigned URLs are disabled.")
        return {
            'success': False,
            'error': 'Presigned URLs are not supported. Please use the streaming upload endpoint instead.',
            'total_files': len(files_metadata),
            'alternative': 'Use upload_batch_django_files() method'
        }

    def upload_files_optimized(self, files: List[Dict[str, Any]], path_prefix: Optional[str] = None, 
                             max_workers: int = 10, multipart_threshold: int = 8 * 1024 * 1024,
                             max_concurrency: int = 10, multipart_chunksize: int = 8 * 1024 * 1024,
                             bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload multiple files in parallel with optimized transfer configuration.
        
        Args:
            files: List of dictionaries containing file information with keys:
                  - file_obj: File-like object or bytes
                  - file_name: Name of the file
                  - content_type: MIME type (optional, defaults to application/octet-stream)
            path_prefix: Optional prefix for all S3 keys
            max_workers: Maximum number of worker processes for parallel uploads
            multipart_threshold: Size threshold for multipart uploads (default 8MB)
            max_concurrency: Maximum number of threads for concurrent part uploads
            multipart_chunksize: Size of each part for multipart uploads (default 8MB)
            bucket_name: Target bucket name (defaults to ingest_bucket)
            
        Returns:
            Dictionary with batch upload results
        """
        results = []
        failures = []
        start_time = time.time()
        total_size = 0
        
        # Determine target bucket
        target_bucket = bucket_name if bucket_name else self.ingest_bucket
        
        logger.info(f"Starting optimized batch upload of {len(files)} files with {max_workers} workers to bucket: {target_bucket}")
        
        # Configure optimized transfer settings
        config = TransferConfig(
            multipart_threshold=multipart_threshold,
            max_concurrency=max_concurrency,
            multipart_chunksize=multipart_chunksize,
            use_threads=True
        )
        
        # Function to upload a single file with the optimized config
        def upload_single_file(file_info):
            try:
                file_obj = file_info.get('file_obj')
                file_name = file_info.get('file_name')
                content_type = file_info.get('content_type', 'application/octet-stream')
                file_size = file_info.get('file_size')
                
                # Generate S3 key
                s3_key = self._generate_file_key(file_name, path_prefix)
                
                logger.debug(f"Uploading file {file_name} to {s3_key}")
                
                # Handle bytes input
                if isinstance(file_obj, bytes):
                    file_obj = BytesIO(file_obj)
                    if file_size is None:
                        file_size = len(file_obj.getvalue())
                
                # Prepare upload arguments
                upload_args = {
                    'ContentType': content_type,
                }
                
                # Upload the file with optimized config
                self.s3_client.upload_fileobj(
                    file_obj,
                    target_bucket,
                    s3_key,
                    ExtraArgs=upload_args,
                    Config=config
                )
                
                # Get file info after upload
                head_response = self.s3_client.head_object(
                    Bucket=target_bucket,
                    Key=s3_key
                )
                actual_file_size = head_response.get('ContentLength', 0)
                
                result = {
                    'success': True,
                    'file_name': file_name,
                    's3_key': s3_key,
                    'bucket': target_bucket,
                    'file_size': actual_file_size,
                    'file_size_formatted': self._format_size(actual_file_size),
                    'content_type': content_type
                }
                
                logger.debug(f"Successfully uploaded {file_name} ({self._format_size(actual_file_size)})")
                return result, None
                
            except Exception as e:
                logger.error(f"Error uploading file {file_info.get('file_name', 'unknown')}: {str(e)}")
                error = {
                    'success': False,
                    'file_name': file_info.get('file_name', 'unknown'),
                    'error': str(e)
                }
                return None, error
        
        # Use ProcessPoolExecutor for parallel uploads
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_file = {executor.submit(upload_single_file, file_info): file_info for file_info in files}
            
            for future in concurrent.futures.as_completed(future_to_file):
                result, error = future.result()
                if result:
                    results.append(result)
                    total_size += result.get('file_size', 0)
                if error:
                    failures.append(error)
        
        end_time = time.time()
        duration = end_time - start_time
        success_count = len(results)
        failure_count = len(failures)
        
        logger.info(f"Optimized batch upload completed in {duration:.2f} seconds: {success_count} succeeded, "
                   f"{failure_count} failed, total size: {self._format_size(total_size)}")
        
        return {
            'success': failure_count == 0,
            'results': results,
            'failures': failures,
            'total_uploaded': success_count,
            'total_failed': failure_count,
            'total_size': total_size,
            'total_size_formatted': self._format_size(total_size),
            'duration_seconds': duration
        }

    def upload_batch_django_files_optimized(self, uploaded_files: List, 
                                 path_prefix: Optional[str] = None,
                                 max_workers: int = 10,
                                 multipart_threshold: int = 8 * 1024 * 1024,
                                 max_concurrency: int = 10,
                                 multipart_chunksize: int = 8 * 1024 * 1024,
                                 bucket_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Upload multiple Django UploadedFile objects to S3 using optimized parallel uploads.
        
        Args:
            uploaded_files: List of Django UploadedFile objects
            path_prefix: Optional prefix for all S3 keys
            max_workers: Maximum number of worker processes for parallel uploads
            multipart_threshold: Size threshold for multipart uploads (default 8MB)
            max_concurrency: Maximum number of threads for concurrent part uploads
            multipart_chunksize: Size of each part for multipart uploads (default 8MB)
            bucket_name: Target bucket name (defaults to ingest_bucket)
            
        Returns:
            Dictionary with batch upload results
        """
        logger.info(f"Starting optimized batch upload of {len(uploaded_files)} Django files with {max_workers} workers")
        
        # Convert Django files to the format needed by upload_files_optimized
        files_to_upload = []
        for uploaded_file in uploaded_files:
            files_to_upload.append({
                'file_obj': uploaded_file,
                'file_name': uploaded_file.name,
                'content_type': getattr(uploaded_file, 'content_type', 'application/octet-stream'),
                'file_size': getattr(uploaded_file, 'size', None)
            })
        
        # Use the optimized upload method
        return self.upload_files_optimized(
            files=files_to_upload,
            path_prefix=path_prefix,
            max_workers=max_workers,
            multipart_threshold=multipart_threshold,
            max_concurrency=max_concurrency,
            multipart_chunksize=multipart_chunksize,
            bucket_name=bucket_name
        )

    def initialize_multipart_upload(self, file_name: str, file_type: str, path_prefix: Optional[str] = None) -> Dict[str, Any]:
        """
        Legacy method - multipart uploads are now handled through streaming.
        This method returns an error indicating that streaming upload should be used instead.
        """
        logger.warning(f"Legacy multipart upload initialization requested for {file_name}, but this method is deprecated.")
        return {
            'success': False,
            'error': 'Direct multipart uploads are no longer supported. Please use the streaming upload endpoint instead.',
            'file_name': file_name,
            'alternative': 'Use upload_django_file() or upload_file_stream() methods with the optimized parameters'
        }
        
    def get_upload_part_urls(self, s3_key: str, upload_id: str, part_count: int, expiration: int = 3600) -> Dict[str, Any]:
        """
        Legacy method - multipart uploads are now handled through streaming.
        This method returns an error indicating that streaming upload should be used instead.
        """
        logger.warning(f"Legacy part upload URLs requested for {s3_key}, but this method is deprecated.")
        return {
            'success': False,
            'error': 'Direct multipart uploads are no longer supported. Please use the streaming upload endpoint instead.',
            's3_key': s3_key,
            'alternative': 'Use upload_django_file() or upload_file_stream() methods with the optimized parameters'
        }
        
    def complete_multipart_upload(self, s3_key: str, upload_id: str, parts: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Legacy method - multipart uploads are now handled through streaming.
        This method returns an error indicating that streaming upload should be used instead.
        """
        logger.warning(f"Legacy multipart upload completion requested for {s3_key}, but this method is deprecated.")
        return {
            'success': False,
            'error': 'Direct multipart uploads are no longer supported. Please use the streaming upload endpoint instead.',
            's3_key': s3_key,
            'alternative': 'Use upload_django_file() or upload_file_stream() methods with the optimized parameters'
        }
        
    def abort_multipart_upload(self, s3_key: str, upload_id: str) -> Dict[str, Any]:
        """
        Legacy method - multipart uploads are now handled through streaming.
        This method returns a success response since there's nothing to abort.
        """
        logger.warning(f"Legacy multipart upload abort requested for {s3_key}, but this method is deprecated.")
        return {
            'success': True,
            'message': 'No action needed as direct multipart uploads are no longer supported.',
            's3_key': s3_key
        }
        
    def list_multipart_uploads(self) -> Dict[str, Any]:
        """
        Legacy method - multipart uploads are now handled through streaming.
        This method returns an empty list since there are no legacy multipart uploads.
        """
        logger.warning("Legacy multipart uploads listing requested, but this method is deprecated.")
        return {
            'success': True,
            'uploads': [],
            'count': 0,
            'message': 'Direct multipart uploads are no longer supported.'
        } 