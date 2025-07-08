import os
import json
import csv
from django.core.management.base import BaseCommand, CommandError
from arkumu.common.enums import UpdateStrategy
from arkumu.metadata.services.mapping import FKConfig


class Command(BaseCommand):
    help = 'Import CSV files using the brute force approach'

    def add_arguments(self, parser):
        parser.add_argument('csv_path', type=str, help='Path to CSV file or directory containing CSV files')
        parser.add_argument('--institution', type=str, default='DEFAULT', help='Institution code')
        parser.add_argument('--base-uri', type=str, default='http://arkumu.org/data', help='Base URI for generated resources')
        parser.add_argument('--delimiter', type=str, default=';', help='CSV column delimiter')
        parser.add_argument('--has-quoted-fields', action='store_true', help='Whether fields in the CSV are quoted')
        parser.add_argument('--relationship-file', type=str, help='JSON file with relationship table definitions')
        
    def handle(self, *args, **options):
        csv_path = options['csv_path']
        institution = options['institution']
        base_uri = options['base_uri']
        delimiter = options['delimiter']
        has_quoted_fields = options['has_quoted_fields']
        relationship_file = options.get('relationship_file')
        
        # Load relationship definitions if provided
        relationship_tables = {}
        if relationship_file and os.path.exists(relationship_file):
            with open(relationship_file, 'r') as f:
                relationship_tables = json.load(f)
        
        # Process single file or directory
        if os.path.isfile(csv_path):
            csv_files = [csv_path]
        elif os.path.isdir(csv_path):
            csv_files = [os.path.join(csv_path, f) for f in os.listdir(csv_path) if f.endswith('.csv')]
        else:
            raise CommandError(f"Path not found: {csv_path}")
            
        total_stats = {
            "files_processed": 0,
            "rows_processed": 0,
            "cells_processed": 0,
            "resources_created": 0,
            "triples_created": 0,
            "relationships_created": 0,
            "errors": 0
        }
        
        for file_path in csv_files:
            file_name = os.path.basename(file_path)
            dataset_name = os.path.splitext(file_name)[0]
            
            self.stdout.write(f"Processing {file_name}...")
            
            # Check if this is a relationship table
            is_relationship = False
            fk_columns = []
            
            if dataset_name in relationship_tables:
                is_relationship = True
                fk_columns = relationship_tables[dataset_name]
                self.stdout.write(f"  Treating as relationship table with FK columns: {', '.join(c['column'] for c in fk_columns)}")
            
            # Import based on table type
            if is_relationship:
                # Create FK relationships for SmartBulkUpdaterPolars
                fk_relationships = []
                for fk_col in fk_columns:
                    fk_relationships.append(FKConfig(
                        source_column=fk_col["column"],
                        source_dataset=dataset_name,
                        target_column=fk_col["target_column"],
                        target_dataset=fk_col["target_table"]
                    ))
                
                # Use SmartBulkUpdaterPolars for relationship processing
                updater = SmartBulkUpdaterPolars(
                    default_strategy=UpdateStrategy.UPDATE_VALUES,
                    institution=institution,
                    base_uri=base_uri,
                    fk_relationships=fk_relationships
                )
                
                # Read CSV data
                csv_data = []
                with open(file_path, 'r', encoding='utf-8') as f:
                    quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                    reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                    csv_data = list(reader)
                
                # Process with SmartBulkUpdaterPolars
                bulk_stats = updater.import_csv_with_smart_updates(csv_data, dataset_name)
                
                # Convert BulkUpdateStats to dict format expected by this command
                stats = {
                    "rows_processed": bulk_stats.rows_processed,
                    "cells_processed": bulk_stats.cells_processed,
                    "resources_created": bulk_stats.resources_created,
                    "triples_created": bulk_stats.triples_created,
                    "relationships_created": bulk_stats.relationships_created,
                    "errors": bulk_stats.errors
                }
                
                # Process FK relationships separately
                datasets = {dataset_name: csv_data}
                fk_stats = updater.process_fk_relationships(datasets)
                stats["relationships_created"] += fk_stats.relationships_created
                
            else:
                # Use SmartBulkUpdaterPolars for regular CSV import
                updater = SmartBulkUpdaterPolars(
                    default_strategy=UpdateStrategy.UPDATE_VALUES,
                    institution=institution,
                    base_uri=base_uri,
                    link_row_cells=True,
                    link_topology="row"
                )
                
                # Read CSV data
                csv_data = []
                with open(file_path, 'r', encoding='utf-8') as f:
                    quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                    reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                    csv_data = list(reader)
                
                # Process with SmartBulkUpdaterPolars
                bulk_stats = updater.import_csv_with_smart_updates(csv_data, dataset_name)
                
                # Convert BulkUpdateStats to dict format expected by this command
                stats = {
                    "rows_processed": bulk_stats.rows_processed,
                    "cells_processed": bulk_stats.cells_processed,
                    "resources_created": bulk_stats.resources_created,
                    "triples_created": bulk_stats.triples_created,
                    "row_links_created": bulk_stats.row_links_created,
                    "errors": bulk_stats.errors
                }
            
            # Update total stats
            total_stats["files_processed"] += 1
            for key in stats:
                if key in total_stats:
                    total_stats[key] += stats[key]
            
            # Report file stats
            self.stdout.write(f"  Completed {file_name}:")
            for key, value in stats.items():
                self.stdout.write(f"    {key}: {value}")
        
        # Report total stats
        self.stdout.write(self.style.SUCCESS("\nImport completed!"))
        self.stdout.write("Total statistics:")
        for key, value in total_stats.items():
            self.stdout.write(f"  {key}: {value}") 