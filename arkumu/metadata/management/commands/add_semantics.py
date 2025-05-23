from django.core.management.base import BaseCommand
from django.db import transaction
from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple
from arkumu.metadata.utils.rdf_helpers import (
    get_or_create_resource,
    create_triple_if_not_exists,
    add_semantic_triple,
    add_class_to_resource
)


class Command(BaseCommand):
    help = 'Add semantic triples to existing data'

    def add_arguments(self, parser):
        parser.add_argument('--dataset', type=str, help='Dataset name to enhance with semantics')
        parser.add_argument('--source', type=str, default='DEFAULT', help='Source institution code')
        parser.add_argument('--base-uri', type=str, default='http://arkumu.org/data', help='Base URI for resources')
        
    def handle(self, *args, **options):
        dataset_name = options.get('dataset')
        source = options.get('source')
        base_uri = options.get('base_uri')
        
        if not dataset_name:
            self.stdout.write(self.style.ERROR("Please provide a dataset name with --dataset"))
            return
        
        dataset_uri = f"{base_uri}/datasets/{dataset_name}"
        
        try:
            # Get the dataset resource
            dataset = Resource.objects.get(uri=dataset_uri)
            self.stdout.write(f"Found dataset: {dataset}")
            
            # 1. Add ontology classes and properties
            with transaction.atomic():
                # Create CIDOC-CRM classes
                artwork_class, created = get_or_create_resource(
                    uri="http://www.cidoc-crm.org/cidoc-crm/E22_Human-Made_Object",
                    resource_type=ResourceType.CLASS,
                    name="Human-Made Object",
                    source=source
                )
                self.stdout.write(f"{'Created' if created else 'Found'} artwork class: {artwork_class}")
                
                artist_class, created = get_or_create_resource(
                    uri="http://www.cidoc-crm.org/cidoc-crm/E21_Person",
                    resource_type=ResourceType.CLASS,
                    name="Person",
                    source=source
                )
                self.stdout.write(f"{'Created' if created else 'Found'} artist class: {artist_class}")
                
                # Create properties
                created_by, created = get_or_create_resource(
                    uri="http://www.cidoc-crm.org/cidoc-crm/P14_carried_out_by",
                    resource_type=ResourceType.PROPERTY,
                    name="carried out by",
                    source=source
                )
                self.stdout.write(f"{'Created' if created else 'Found'} created_by property: {created_by}")
                
                has_title, created = get_or_create_resource(
                    uri="http://www.cidoc-crm.org/cidoc-crm/P102_has_title",
                    resource_type=ResourceType.PROPERTY,
                    name="has title",
                    source=source
                )
                self.stdout.write(f"{'Created' if created else 'Found'} has_title property: {has_title}")
            
            # 2. Example: Find all cells with "Originaltitel" and create semantic connections
            title_cells = Resource.objects.filter(name="Originaltitel")
            self.stdout.write(f"Found {title_cells.count()} title cells")
            
            # Process each title cell
            for title_cell in title_cells:
                # Get the title value
                title_value = None
                for triple in Triple.objects.filter(subject=title_cell):
                    if triple.predicate.name == "value" and triple.object.resource_type == ResourceType.LITERAL:
                        title_value = triple.object.value
                        break
                
                if not title_value:
                    continue
                
                # Extract row ID from cell URI
                # URI format: {base_uri}/datasets/{dataset_name}/{column_name}/{row_id}
                parts = title_cell.uri.split('/')
                if len(parts) < 5:
                    continue
                    
                row_id = parts[-1]
                
                # Create an artwork resource for this row
                artwork_uri = f"{base_uri}/artworks/{row_id}"
                artwork, created = get_or_create_resource(
                    uri=artwork_uri,
                    resource_type=ResourceType.IRI,
                    name=f"Artwork {row_id}",
                    source=source
                )
                
                # Add class to artwork
                add_class_to_resource(artwork_uri, artwork_class.uri, source)
                
                # Add title to artwork
                add_semantic_triple(
                    subject_uri=artwork_uri,
                    predicate_uri=has_title.uri,
                    object_uri_or_value=title_value,
                    is_object_literal=True,
                    source=source
                )
                
                self.stdout.write(f"Enhanced artwork {row_id}: {title_value}")
            
            self.stdout.write(self.style.SUCCESS("Successfully added semantics to the dataset"))
            
        except Resource.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Dataset not found: {dataset_uri}"))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error: {e}")) 