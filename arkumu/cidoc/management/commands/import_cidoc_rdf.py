from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from arkumu.cidoc.rdf_import import import_cidoc_from_rdf
from arkumu.cidoc.models.schema import CIDOCClass, CIDOCProperty
import os
from pathlib import Path
import time

class Command(BaseCommand):
    help = 'Imports CIDOC-CRM ontology from RDF files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--rdf-file',
            type=str,
            help='Path to the RDF file to import (defaults to provided CIDOC RDF)',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force import even if classes already exist',
        )

    def handle(self, *args, **options):
        # Default RDF file is in the schema directory
        base_dir = Path(__file__).resolve().parent.parent.parent
        default_rdf = os.path.join(base_dir, 'schema/CIDOC_CRM_v7.1.1.rdf')
        
        rdf_file = options.get('rdf_file') or default_rdf
        force = options.get('force', False)
        
        if not os.path.exists(rdf_file):
            raise CommandError(f'RDF file does not exist: {rdf_file}')
        
        # Check if data already exists
        if CIDOCClass.objects.exists() and not force:
            self.stdout.write(
                self.style.WARNING(
                    f'CIDOC classes already exist. Use --force to reimport. Currently {CIDOCClass.objects.count()} classes and {CIDOCProperty.objects.count()} properties exist.'
                )
            )
            return
            
        # Start timing
        start_time = time.time()
        
        # Import RDF data
        try:
            with transaction.atomic():
                # Clear existing data if force is used
                if force and CIDOCClass.objects.exists():
                    self.stdout.write(self.style.WARNING('Clearing existing CIDOC data...'))
                    CIDOCProperty.objects.all().delete()
                    CIDOCClass.objects.all().delete()
                
                self.stdout.write(f'Importing data from {rdf_file}...')
                classes_count, properties_count = import_cidoc_from_rdf(rdf_file)
                
                # Show timing
                end_time = time.time()
                duration = end_time - start_time
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Successfully imported {classes_count} classes and {properties_count} properties in {duration:.2f} seconds'
                    )
                )
                
                # Display some sample data
                if classes_count > 0:
                    sample_class = CIDOCClass.objects.first()
                    self.stdout.write(f'Sample class: {sample_class.class_id} - {sample_class.label}')
                
                if properties_count > 0:
                    sample_prop = CIDOCProperty.objects.first()
                    self.stdout.write(f'Sample property: {sample_prop.property_id} - {sample_prop.label}')
                    
        except Exception as e:
            raise CommandError(f'RDF import failed: {str(e)}') 