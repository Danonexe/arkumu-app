import os
from django.core.management.base import BaseCommand, CommandError
from ...importers import CIDOCImporter


class Command(BaseCommand):
    help = 'Import data from a CSV file using a mapping file into CIDOC-CRM models'

    def add_arguments(self, parser):
        parser.add_argument('mapping_file', help='Path to the mapping JSON file')
        parser.add_argument('csv_file', help='Path to the CSV data file')
        parser.add_argument(
            '--institution', 
            help='Name of the institution providing the data'
        )
        parser.add_argument(
            '--field', 
            help='Field or collection within the institution'
        )
        parser.add_argument(
            '--batch', 
            help='Identifier for this import batch'
        )
        parser.add_argument(
            '--limit', 
            type=int,
            help='Maximum number of rows to import'
        )
        parser.add_argument(
            '--delimiter', 
            default=';',
            help='CSV delimiter character (default: ;)'
        )

    def handle(self, *args, **options):
        mapping_file = options['mapping_file']
        csv_file = options['csv_file']
        
        # Check if files exist
        if not os.path.exists(mapping_file):
            raise CommandError(f"Mapping file not found: {mapping_file}")
        
        if not os.path.exists(csv_file):
            raise CommandError(f"CSV file not found: {csv_file}")
        
        # Create the importer
        importer = CIDOCImporter(
            mapping_file=mapping_file,
            csv_file=csv_file,
            institution=options.get('institution'),
            field=options.get('field'),
            batch_name=options.get('batch'),
            delimiter=options.get('delimiter')
        )
        
        # Run the import
        self.stdout.write(self.style.SUCCESS(f"Starting import..."))
        stats = importer.import_data(limit=options.get('limit'))
        
        # Report results
        self.stdout.write(self.style.SUCCESS(f"Import completed."))
        self.stdout.write(f"Total rows: {stats['total_rows']}")
        self.stdout.write(f"Processed rows: {stats['processed_rows']}")
        self.stdout.write(f"Skipped rows: {stats['skipped_rows']}")
        self.stdout.write(f"Errors: {stats['errors']}")
        self.stdout.write(f"Entities created/updated: {stats['entities_created']}")
        self.stdout.write(f"Statements created: {stats['statements_created']}")
        
        if stats['errors'] > 0:
            self.stdout.write(self.style.WARNING(f"There were {stats['errors']} errors during import. Check the logs for details."))
        else:
            self.stdout.write(self.style.SUCCESS("Import completed successfully!")) 