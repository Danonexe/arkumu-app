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
    DirectoryImportSerializer,
    ClearDatabaseSerializer
)

logger = logging.getLogger(__name__)


@extend_schema(tags=['import'])
class ImportViewSet(viewsets.GenericViewSet):
    """
    API endpoint for importing CSV data from directories.
    """
    # This base name will be used in the URL
    basename = 'import'
    
    # Define the serializer class for schema generation
    serializer_class = DirectoryImportSerializer
    
    # Define the queryset (even though we don't use it)
    queryset = None
    
    # Allow any access
    permission_classes = [AllowAny]
    
    @extend_schema(
        operation_id='import_directory',
        description='Import all CSV files from a directory with automatic foreign key detection and placeholder-based reference resolution. No manual configuration required.',
        request=DirectoryImportSerializer,
        responses={200: dict},
        examples=[
            OpenApiExample(
                'Example Request',
                value={
                    'directory_path': '/path/to/csv_files',
                    'institution': 'DEFAULT',
                    'delimiter': ';',
                    'has_quoted_fields': False,
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
        url_path='',
        parser_classes=[MultiPartParser, FormParser, JSONParser]
    )
    def import_directory(self, request):
        """
        Import all CSV files from a directory with automatic reference detection.
        
        This endpoint will:
        1. Scan the directory for CSV files
        2. Process all files uniformly with automatic foreign key detection
        3. Create placeholders for missing references
        4. Resolve placeholders when referenced entities are imported
        5. Handle file uploads if S3 config is provided
        """
        serializer = DirectoryImportSerializer(data=request.data)
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