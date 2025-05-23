import os
import json
import logging
from django.conf import settings
from django.db import connection
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import AllowAny
from rdflib import Graph
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiExample

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService
from arkumu.rest.serializers import (
    SingleCSVImportSerializer,
    CSVImportSerializer,
    FileColumnsConfigSerializer,
    FileColumnsConfigGetSerializer,
    ClearDatabaseSerializer
)

logger = logging.getLogger(__name__)


@extend_schema(tags=['import'])
class ImportViewSet(viewsets.GenericViewSet):
    """
    API endpoints for importing CSV data and managing file configurations.
    """
    # This base name will be used in the URL
    basename = 'import'
    
    # Define the serializer class for schema generation
    serializer_class = SingleCSVImportSerializer
    
    # Define the queryset (even though we don't use it)
    queryset = None
    
    # Allow any access
    permission_classes = [AllowAny]
    
    @extend_schema(
        operation_id='import_single_csv',
        description='Import a single CSV file with optional file path handling.',
        request=SingleCSVImportSerializer,
        responses={200: dict},
        examples=[
            OpenApiExample(
                'Example Request',
                value={
                    'csv_path': '/path/to/data.csv',
                    'dataset_name': 'my_dataset',
                    'institution': 'DEFAULT',
                    'delimiter': ';',
                    'has_quoted_fields': True,
                    'file_columns': ['image_path', 'document_path']
                },
                request_only=True,
            ),
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='csv',
        parser_classes=[MultiPartParser, FormParser, JSONParser]
    )
    def import_csv(self, request):
        """
        Import a single CSV file with optional file path handling.
        """
        serializer = SingleCSVImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get parameters from validated data
        validated_data = serializer.validated_data
        csv_path = validated_data['csv_path']
            
        if not os.path.isfile(csv_path):
            return Response(
                {"error": f"CSV file not found: {csv_path}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get other parameters with defaults
        dataset_name = validated_data.get('dataset_name')
        institution = validated_data.get('institution', 'DEFAULT')
        base_uri = validated_data.get('base_uri', 'http://arkumu.org/data')
        delimiter = validated_data.get('delimiter', ';')
        has_quoted_fields = validated_data.get('has_quoted_fields', False)
        is_relationship_table = validated_data.get('is_relationship_table', False)
        fk_columns = validated_data.get('fk_columns')
        file_columns = validated_data.get('file_columns', [])
        files_base_directory = validated_data.get('files_base_directory')
        
        # Initialize S3 upload service if S3 config is provided
        upload_service = None
        s3_config = validated_data.get('s3_config')
        
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

    @extend_schema(
        operation_id='import_csv_directory',
        description='Import CSV files from a directory with optional file path handling.',
        request=CSVImportSerializer,
        responses={200: dict},
        examples=[
            OpenApiExample(
                'Example Request',
                value={
                    'directory_path': '/path/to/csv_files',
                    'institution': 'DEFAULT',
                    'delimiter': ';',
                    'has_quoted_fields': True,
                    'file_columns': {
                        'table1': ['image_path', 'document_path'],
                        'table2': ['attachment_path']
                    }
                },
                request_only=True,
            ),
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='directory',
        parser_classes=[MultiPartParser, FormParser, JSONParser]
    )
    def import_directory(self, request):
        """
        Import CSV files from a directory with optional file path handling.
        """
        serializer = CSVImportSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # Get parameters from validated data
        validated_data = serializer.validated_data
        directory_path = validated_data['directory_path']
            
        if not os.path.isdir(directory_path):
            return Response(
                {"error": f"Directory not found: {directory_path}"}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Get other parameters with defaults
        institution = validated_data.get('institution', 'DEFAULT')
        base_uri = validated_data.get('base_uri', 'http://arkumu.org/data')
        delimiter = validated_data.get('delimiter', ';')
        has_quoted_fields = validated_data.get('has_quoted_fields', False)
        relationship_config_path = validated_data.get('relationship_config_path')
        file_columns = validated_data.get('file_columns', {})
        files_base_directory = validated_data.get('files_base_directory', directory_path)
        
        # Initialize S3 upload service if S3 config is provided
        upload_service = None
        s3_config = validated_data.get('s3_config')
        
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

    @extend_schema(
        operation_id='create_file_columns_config',
        description='Create or update a file columns configuration.',
        request=FileColumnsConfigSerializer,
        responses={200: dict},
        examples=[
            OpenApiExample(
                'Example Request',
                value={
                    'config': {
                        'table1': ['image_path', 'document_path'],
                        'table2': ['attachment_path']
                    },
                    'output_path': '/path/to/config.json'
                },
                request_only=True,
            ),
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='file-columns-config',
        parser_classes=[JSONParser]
    )
    def create_file_columns_config(self, request):
        """
        Create or update a file columns configuration.
        """
        serializer = FileColumnsConfigSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        validated_data = serializer.validated_data
        config = validated_data['config']
        output_path = validated_data.get('output_path')
            
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
    
    @extend_schema(
        operation_id='get_file_columns_config',
        description='Load a file columns configuration.',
        parameters=[
            OpenApiParameter(
                name='path',
                description='Path to the configuration file',
                required=True,
                type=str,
                location=OpenApiParameter.QUERY
            )
        ],
        responses={200: dict}
    )
    @action(
        detail=False,
        methods=['get'],
        url_path='file-columns-config',
        parser_classes=[JSONParser]
    )
    def get_file_columns_config(self, request):
        """
        Load a file columns configuration.
        """
        serializer = FileColumnsConfigGetSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        path = serializer.validated_data['path']
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


@extend_schema(tags=['testing'])
class TestingViewSet(viewsets.GenericViewSet):
    """
    API endpoints for testing operations.
    """
    # This base name will be used in the URL
    basename = 'testing'
    
    # Define the serializer class for schema generation
    serializer_class = ClearDatabaseSerializer
    
    # Define the queryset (even though we don't use it)
    queryset = None
    
    # Allow any access
    permission_classes = [AllowAny]
    
    @extend_schema(
        operation_id='clear_database',
        description='Clear all data from the database (for testing purposes only).',
        request=ClearDatabaseSerializer,
        responses={
            200: dict,
            400: {"description": "Missing confirmation or invalid request"},
            403: {"description": "Operation not allowed in production mode"}
        },
        examples=[
            OpenApiExample(
                'Example Request',
                value={
                    'confirm': True
                },
                request_only=True,
            ),
        ]
    )
    @action(
        detail=False,
        methods=['post'],
        url_path='clear-database'
    )
    def clear_database(self, request):
        """
        Clear all data from the database (for testing purposes only).
        """
        serializer = ClearDatabaseSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            
        # Check if confirmation is provided
        if not serializer.validated_data.get('confirm'):
            return Response(
                {'error': 'Confirmation required. Set confirm=true to proceed with database clearing'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
            
        try:
            # WARNING: This is a destructive operation and should only be used in testing environments
            if not settings.DEBUG:
                return Response(
                    {'error': 'This operation is only allowed in DEBUG mode'}, 
                    status=status.HTTP_403_FORBIDDEN
                )
            
            # Clear the RDF store
            g = Graph()
            
            # Get the RDF store backend from settings
            store_type = getattr(settings, 'RDFLIB_STORE', 'default')
            
            if store_type == 'SQLAlchemy':
                # If using SQLAlchemy store, clear through SQL
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM rdf_term")
                    cursor.execute("DELETE FROM rdf_namespace")
                    cursor.execute("DELETE FROM rdf_triple")
                    cursor.execute("DELETE FROM rdf_literal")
                    
                stats = {
                    'message': 'Database cleared successfully via SQL',
                    'tables_cleared': ['rdf_term', 'rdf_namespace', 'rdf_triple', 'rdf_literal']
                }
            else:
                # Default approach using rdflib
                store_config = getattr(settings, 'RDFLIB_STORE_CONFIG', {})
                g.open(store_config, create=False)
                g.remove((None, None, None))  # Remove all triples
                g.close()
                
                stats = {
                    'message': 'Database cleared successfully via rdflib',
                    'triples_removed': 'all'
                }
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error clearing database: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 