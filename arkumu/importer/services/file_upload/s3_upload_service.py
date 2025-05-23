import os
import logging
import boto3
from botocore.exceptions import ClientError
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger(__name__)

class S3UploadService:
    """
    Service for uploading files to S3 during import.
    """
    
    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        region_name: str = 'us-east-1',
        bucket_name: str = 'arkumu-files',
        base_url: str = 'https://s3.amazonaws.com/arkumu-files'
    ):
        """
        Initialize the S3 upload service.
        
        Args:
            aws_access_key_id: AWS access key ID (if None, uses environment variables)
            aws_secret_access_key: AWS secret access key (if None, uses environment variables)
            region_name: AWS region name
            bucket_name: S3 bucket name
            base_url: Base URL for accessing uploaded files
        """
        self.region_name = region_name
        self.bucket_name = bucket_name
        self.base_url = base_url
        
        # Initialize S3 client
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            region_name=region_name
        )
    
    def upload_file(
        self,
        file_path: str,
        object_name: Optional[str] = None,
        extra_args: Optional[Dict[str, Any]] = None
    ) -> Tuple[bool, str]:
        """
        Upload a file to S3.
        
        Args:
            file_path: Path to the file to upload
            object_name: S3 object name (if None, uses file basename)
            extra_args: Extra arguments to pass to boto3 upload_file
            
        Returns:
            Tuple of (success, url_or_error_message)
        """
        if not os.path.exists(file_path):
            return False, f"File not found: {file_path}"
        
        # If object_name not specified, use file basename
        if object_name is None:
            object_name = os.path.basename(file_path)
        
        # Set default extra args if not provided
        if extra_args is None:
            extra_args = {'ACL': 'public-read'}
        
        try:
            self.s3_client.upload_file(
                file_path,
                self.bucket_name,
                object_name,
                ExtraArgs=extra_args
            )
            file_url = f"{self.base_url}/{object_name}"
            logger.info(f"Uploaded {file_path} to {file_url}")
            return True, file_url
        except ClientError as e:
            error_message = str(e)
            logger.error(f"Error uploading {file_path}: {error_message}")
            return False, error_message
    
    def upload_files_from_directory(
        self,
        directory_path: str,
        prefix: str = '',
        recursive: bool = True
    ) -> Dict[str, str]:
        """
        Upload all files from a directory to S3.
        
        Args:
            directory_path: Path to the directory containing files to upload
            prefix: Prefix to add to S3 object names
            recursive: Whether to recursively upload files in subdirectories
            
        Returns:
            Dict mapping local file paths to S3 URLs
        """
        if not os.path.isdir(directory_path):
            logger.error(f"Directory not found: {directory_path}")
            return {}
        
        results = {}
        
        for root, dirs, files in os.walk(directory_path):
            # Skip if not recursive and not in the top directory
            if not recursive and root != directory_path:
                continue
                
            for file in files:
                local_path = os.path.join(root, file)
                
                # Calculate relative path for S3 object name
                rel_path = os.path.relpath(local_path, directory_path)
                object_name = os.path.join(prefix, rel_path).replace('\\', '/')
                
                success, result = self.upload_file(local_path, object_name)
                if success:
                    results[local_path] = result
        
        return results
    
    def resolve_file_path(
        self,
        base_directory: str,
        relative_path: str
    ) -> str:
        """
        Resolve a relative file path against a base directory.
        
        Args:
            base_directory: Base directory
            relative_path: Relative path from the CSV
            
        Returns:
            Absolute path to the file
        """
        # Handle different path formats
        clean_path = relative_path.strip().replace('\\', '/').lstrip('/')
        
        # Try different combinations to find the file
        candidates = [
            os.path.join(base_directory, clean_path),
            os.path.join(base_directory, 'files', clean_path),
            os.path.join(base_directory, '..', 'files', clean_path)
        ]
        
        for path in candidates:
            if os.path.exists(path):
                return path
        
        # If file not found, return the first candidate
        return candidates[0] 