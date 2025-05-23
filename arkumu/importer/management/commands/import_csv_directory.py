import os
import json
import logging
from django.core.management.base import BaseCommand
from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
from arkumu.importer.services.file_upload.s3_upload_service import S3UploadService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Import all CSV files in a directory with file path handling'

    def add_arguments(self, parser):
        parser.add_argument('directory_path', type=str, help='Path to directory containing CSV files')
        parser.add_argument('--institution', type=str, default='DEFAULT', help='Institution code')
        parser.add_argument('--base-uri', type=str, default='http://arkumu.org/data', help='Base URI for generated resources')
        parser.add_argument('--delimiter', type=str, default=';', help='CSV column delimiter')
        parser.add_argument('--has-quoted-fields', action='store_true', help='Whether fields in the CSV are quoted')
        parser.add_argument('--relationship-config', type=str, help='Path to relationship configuration file')
        parser.add_argument('--file-columns-config', type=str, help='Path to file columns configuration JSON')
        parser.add_argument('--files-base-directory', type=str, help='Base directory for resolving file paths')
        parser.add_argument('--aws-access-key', type=str, help='AWS access key ID')
        parser.add_argument('--aws-secret-key', type=str, help='AWS secret access key')
        parser.add_argument('--s3-region', type=str, default='us-east-1', help='AWS S3 region')
        parser.add_argument('--s3-bucket', type=str, default='arkumu-files', help='AWS S3 bucket name')
        parser.add_argument('--s3-base-url', type=str, default='https://s3.amazonaws.com/arkumu-files', help='S3 base URL')
        parser.add_argument('--disable-file-upload', action='store_true', help='Disable file upload functionality')

    def handle(self, *args, **options):
        directory_path = options['directory_path']
        
        if not os.path.isdir(directory_path):
            self.stderr.write(self.style.ERROR(f"Directory not found: {directory_path}"))
            return
            
        # Load file columns configuration if provided
        file_columns = {}
        if options['file_columns_config'] and os.path.exists(options['file_columns_config']):
            try:
                with open(options['file_columns_config'], 'r') as f:
                    file_columns = json.load(f)
                self.stdout.write(self.style.SUCCESS(f"Loaded file columns configuration from {options['file_columns_config']}"))
            except Exception as e:
                self.stderr.write(self.style.ERROR(f"Error loading file columns configuration: {e}"))
        
        # Initialize S3 upload service if file upload is enabled
        upload_service = None
        if not options['disable_file_upload']:
            upload_service = S3UploadService(
                aws_access_key_id=options['aws_access_key'],
                aws_secret_access_key=options['aws_secret_key'],
                region_name=options['s3_region'],
                bucket_name=options['s3_bucket'],
                base_url=options['s3_base_url']
            )
            self.stdout.write(self.style.SUCCESS("Initialized S3 upload service"))
        
        # Set files base directory
        files_base_directory = options['files_base_directory'] or directory_path
        
        # Run the import
        stats = ImportWorkflowService.import_csv_directory(
            directory_path=directory_path,
            institution=options['institution'],
            base_uri=options['base_uri'],
            delimiter=options['delimiter'],
            has_quoted_fields=options['has_quoted_fields'],
            relationship_config_path=options['relationship_config'],
            file_columns=file_columns,
            files_base_directory=files_base_directory,
            upload_service=upload_service
        )
        
        # Print statistics
        self.stdout.write(self.style.SUCCESS("Import completed with the following statistics:"))
        for key, value in stats.items():
            self.stdout.write(f"  {key}: {value}") 