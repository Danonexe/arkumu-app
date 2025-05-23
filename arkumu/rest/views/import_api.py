import os
import json
import logging
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.conf import settings

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService

logger = logging.getLogger(__name__)

class SingleCSVImportView(APIView):
    """
    API endpoint for importing a single CSV file with file path handling.
    """
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    
    def post(self, request, format=None):
        """
        Import a single CSV file with optional file path handling.
        
        Request body:
        - csv_path: Path to the CSV file
        - dataset_name: Name for the dataset (defaults to CSV filename without extension)
        - institution: Institution code (default: DEFAULT)
        - base_uri: Base URI for generated resources (default: http://arkumu.org/data)
        - delimiter: CSV column delimiter (default: ;)
        - has_quoted_fields: Whether fields in the CSV are quoted (default: false)
        - is_relationship_table: Whether this CSV represents a relationship table (default: false)
        - fk_columns: List of foreign key column configurations (required if is_relationship_table=True)
        - file_columns: List of column names containing file paths
        - files_base_directory: Base directory for resolving file paths
        - s3_config: Configuration for S3 upload (optional)
          - aws_access_key_id: AWS access key ID
          - aws_secret_access_key: AWS secret access key
          - region_name: AWS region name (default: us-east-1)
          - bucket_name: S3 bucket name (default: arkumu-files)
          - base_url: Base URL for accessing uploaded files
        """
        # Get parameters from request
        csv_path = request.data.get('csv_path')
        if not csv_path:
            return Response(
                {"error": "csv_path is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not os.path.isfile(csv_path):
            return Response(
                {"error": f"CSV file not found: {csv_path}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get other parameters with defaults
        dataset_name = request.data.get('dataset_name')
        institution = request.data.get('institution', 'DEFAULT')
        base_uri = request.data.get('base_uri', 'http://arkumu.org/data')
        delimiter = request.data.get('delimiter', ';')
        has_quoted_fields = request.data.get('has_quoted_fields', False)
        is_relationship_table = request.data.get('is_relationship_table', False)
        fk_columns = request.data.get('fk_columns')
        file_columns = request.data.get('file_columns', [])
        files_base_directory = request.data.get('files_base_directory')
        
        # Initialize S3 upload service if S3 config is provided
        upload_service = None
        s3_config = request.data.get('s3_config')
        
        if s3_config:
            # Get S3 configuration with defaults
            aws_access_key_id = s3_config.get('aws_access_key_id')
            aws_secret_access_key = s3_config.get('aws_secret_access_key')
            region_name = s3_config.get('region_name', 'us-east-1')
            bucket_name = s3_config.get('bucket_name', 'arkumu-files')
            base_url = s3_config.get('base_url', f'https://s3.amazonaws.com/{bucket_name}')
            
            # Use environment variables if keys not provided
            if not aws_access_key_id:
                aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
            if not aws_secret_access_key:
                aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
            
            # Initialize S3 upload service
            upload_service = S3UploadService(
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
                bucket_name=bucket_name,
                base_url=base_url
            )
            logger.info("Initialized S3 upload service")
        
        # Run the import
        try:
            stats = ImportWorkflowService.import_csv(
                csv_path=csv_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                is_relationship_table=is_relationship_table,
                fk_columns=fk_columns,
                file_columns=file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service
            )
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error during CSV import: {str(e)}")
            return Response(
                {"error": f"Import failed: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class CSVImportView(APIView):
    """
    API endpoint for importing CSV files with file path handling.
    """
    parser_classes = (MultiPartParser, FormParser, JSONParser)
    
    def post(self, request, format=None):
        """
        Import CSV files from a directory with optional file path handling.
        
        Request body:
        - directory_path: Path to directory containing CSV files
        - institution: Institution code (default: DEFAULT)
        - base_uri: Base URI for generated resources (default: http://arkumu.org/data)
        - delimiter: CSV column delimiter (default: ;)
        - has_quoted_fields: Whether fields in the CSV are quoted (default: false)
        - relationship_config_path: Optional path to relationship configuration file
        - file_columns: Dict mapping table names to lists of column names containing file paths
        - files_base_directory: Base directory for resolving file paths
        - s3_config: Configuration for S3 upload (optional)
          - aws_access_key_id: AWS access key ID
          - aws_secret_access_key: AWS secret access key
          - region_name: AWS region name (default: us-east-1)
          - bucket_name: S3 bucket name (default: arkumu-files)
          - base_url: Base URL for accessing uploaded files
        """
        # Get parameters from request
        directory_path = request.data.get('directory_path')
        if not directory_path:
            return Response(
                {"error": "directory_path is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not os.path.isdir(directory_path):
            return Response(
                {"error": f"Directory not found: {directory_path}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get other parameters with defaults
        institution = request.data.get('institution', 'DEFAULT')
        base_uri = request.data.get('base_uri', 'http://arkumu.org/data')
        delimiter = request.data.get('delimiter', ';')
        has_quoted_fields = request.data.get('has_quoted_fields', False)
        relationship_config_path = request.data.get('relationship_config_path')
        file_columns = request.data.get('file_columns', {})
        files_base_directory = request.data.get('files_base_directory', directory_path)
        
        # Initialize S3 upload service if S3 config is provided
        upload_service = None
        s3_config = request.data.get('s3_config')
        
        if s3_config:
            # Get S3 configuration with defaults
            aws_access_key_id = s3_config.get('aws_access_key_id')
            aws_secret_access_key = s3_config.get('aws_secret_access_key')
            region_name = s3_config.get('region_name', 'us-east-1')
            bucket_name = s3_config.get('bucket_name', 'arkumu-files')
            base_url = s3_config.get('base_url', f'https://s3.amazonaws.com/{bucket_name}')
            
            # Use environment variables if keys not provided
            if not aws_access_key_id:
                aws_access_key_id = os.environ.get('AWS_ACCESS_KEY_ID')
            if not aws_secret_access_key:
                aws_secret_access_key = os.environ.get('AWS_SECRET_ACCESS_KEY')
            
            # Initialize S3 upload service
            upload_service = S3UploadService(
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
                bucket_name=bucket_name,
                base_url=base_url
            )
            logger.info("Initialized S3 upload service")
        
        # Run the import
        try:
            stats = ImportWorkflowService.import_csv_directory(
                directory_path=directory_path,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                relationship_config_path=relationship_config_path,
                file_columns=file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service
            )
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error during CSV import: {str(e)}")
            return Response(
                {"error": f"Import failed: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class FileColumnsConfigView(APIView):
    """
    API endpoint for managing file columns configuration.
    """
    parser_classes = (JSONParser,)
    
    def post(self, request, format=None):
        """
        Create or update a file columns configuration.
        
        Request body:
        - config: Dict mapping table names to lists of column names containing file paths
        - output_path: Path to save the configuration (optional)
        """
        config = request.data.get('config')
        if not config:
            return Response(
                {"error": "config is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        output_path = request.data.get('output_path')
        
        # Save configuration to file if output_path is provided
        if output_path:
            try:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                with open(output_path, 'w') as f:
                    json.dump(config, f, indent=2)
                logger.info(f"Saved file columns configuration to {output_path}")
            except Exception as e:
                logger.error(f"Error saving file columns configuration: {str(e)}")
                return Response(
                    {"error": f"Failed to save configuration: {str(e)}"}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
        
        return Response({"status": "success", "config": config}, status=status.HTTP_200_OK)
    
    def get(self, request, format=None):
        """
        Load a file columns configuration.
        
        Query parameters:
        - path: Path to the configuration file
        """
        path = request.query_params.get('path')
        if not path:
            return Response(
                {"error": "path query parameter is required"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        if not os.path.exists(path):
            return Response(
                {"error": f"Configuration file not found: {path}"}, 
                status=status.HTTP_404_NOT_FOUND
            )
            
        try:
            with open(path, 'r') as f:
                config = json.load(f)
            return Response(config, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Error loading file columns configuration: {str(e)}")
            return Response(
                {"error": f"Failed to load configuration: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            ) 