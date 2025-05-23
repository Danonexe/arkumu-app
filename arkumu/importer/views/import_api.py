import os
import json
import logging
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from django.views import View
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser

from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService

logger = logging.getLogger(__name__)

# Default file columns config path
DEFAULT_FILE_COLUMNS_CONFIG_PATH = os.path.join(settings.BASE_DIR, 'file_columns_config.json')


class CSVImportView(APIView):
    """API view for importing a single CSV file"""
    parser_classes = (MultiPartParser, FormParser)
    
    def post(self, request, format=None):
        try:
            # Get the uploaded file
            csv_file = request.FILES.get('csv_file')
            if not csv_file:
                return Response({'error': 'No CSV file provided'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Save the file temporarily
            temp_file_path = os.path.join(settings.MEDIA_ROOT, 'temp', csv_file.name)
            os.makedirs(os.path.dirname(temp_file_path), exist_ok=True)
            
            with open(temp_file_path, 'wb+') as destination:
                for chunk in csv_file.chunks():
                    destination.write(chunk)
            
            # Get parameters from request
            dataset_name = request.data.get('dataset_name') or os.path.splitext(csv_file.name)[0]
            institution = request.data.get('institution', 'DEFAULT')
            base_uri = request.data.get('base_uri', 'http://arkumu.org/data')
            delimiter = request.data.get('delimiter', ';')
            has_quoted_fields = request.data.get('has_quoted_fields', 'false').lower() == 'true'
            
            # Get file columns configuration
            file_columns = []
            if 'file_columns' in request.data:
                if isinstance(request.data['file_columns'], str):
                    try:
                        file_columns = json.loads(request.data['file_columns'])
                    except json.JSONDecodeError:
                        file_columns = request.data['file_columns'].split(',')
                else:
                    file_columns = request.data['file_columns']
            
            # Get files base directory
            files_base_directory = request.data.get('files_base_directory')
            if not files_base_directory:
                files_base_directory = os.path.dirname(temp_file_path)
            
            # Create upload service if file columns are specified
            upload_service = None
            if file_columns:
                upload_service = S3UploadService(
                    bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
            
            # Import the CSV
            stats = ImportWorkflowService.import_csv(
                csv_path=temp_file_path,
                dataset_name=dataset_name,
                institution=institution,
                base_uri=base_uri,
                delimiter=delimiter,
                has_quoted_fields=has_quoted_fields,
                file_columns=file_columns,
                files_base_directory=files_base_directory,
                upload_service=upload_service
            )
            
            # Clean up the temporary file
            os.remove(temp_file_path)
            
            return Response(stats, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error importing CSV: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DirectoryImportView(APIView):
    """API view for importing a directory of CSV files"""
    parser_classes = (JSONParser,)
    
    def post(self, request, format=None):
        try:
            # Get parameters from request
            directory_path = request.data.get('directory_path')
            if not directory_path:
                return Response({'error': 'No directory path provided'}, status=status.HTTP_400_BAD_REQUEST)
            
            if not os.path.isdir(directory_path):
                return Response({'error': f'Directory not found: {directory_path}'}, status=status.HTTP_400_BAD_REQUEST)
            
            institution = request.data.get('institution', 'DEFAULT')
            base_uri = request.data.get('base_uri', 'http://arkumu.org/data')
            delimiter = request.data.get('delimiter', ';')
            has_quoted_fields = request.data.get('has_quoted_fields', False)
            
            # Get relationship configuration
            relationship_config_path = request.data.get('relationship_config_path')
            
            # Get file columns configuration
            file_columns = request.data.get('file_columns', {})
            
            # Get files base directory
            files_base_directory = request.data.get('files_base_directory', directory_path)
            
            # Create upload service if file columns are specified
            upload_service = None
            if file_columns:
                upload_service = S3UploadService(
                    bucket_name=settings.AWS_STORAGE_BUCKET_NAME,
                    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                    region_name=settings.AWS_S3_REGION_NAME
                )
            
            # Import the directory
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
            logger.error(f"Error importing directory: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FileColumnsConfigView(APIView):
    """API view for managing file columns configuration"""
    parser_classes = (JSONParser,)
    
    def get(self, request, format=None):
        try:
            config_path = getattr(settings, 'FILE_COLUMNS_CONFIG_PATH', DEFAULT_FILE_COLUMNS_CONFIG_PATH)
            
            if not os.path.exists(config_path):
                return Response({'error': 'File columns configuration not found'}, status=status.HTTP_404_NOT_FOUND)
            
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            return Response(config, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error retrieving file columns configuration: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, format=None):
        try:
            config = request.data
            if not isinstance(config, dict):
                return Response({'error': 'Invalid configuration format'}, status=status.HTTP_400_BAD_REQUEST)
            
            config_path = getattr(settings, 'FILE_COLUMNS_CONFIG_PATH', DEFAULT_FILE_COLUMNS_CONFIG_PATH)
            os.makedirs(os.path.dirname(config_path), exist_ok=True)
            
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            return Response({'message': 'File columns configuration saved successfully'}, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error saving file columns configuration: {e}")
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR) 