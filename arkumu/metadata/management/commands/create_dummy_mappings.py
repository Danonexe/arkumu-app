"""
Management command to create dummy CSV mappings for testing purposes.

This command analyzes existing CSV datasets in S3 for an organization and creates
realistic mapping configurations with relationships, foreign keys, and anchors.
"""

import json
import logging
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model
from arkumu.metadata.models.mappings import Mapping
from arkumu.metadata.views.csv_mapping.mixins.csv_data import CSVDataMixin

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand, CSVDataMixin):
    help = 'Create dummy CSV mappings for testing based on organization datasets'

    def add_arguments(self, parser):
        parser.add_argument(
            '--organization',
            type=str,
            required=True,
            help='Organization ID to create mappings for (e.g., rsh, khm, etc.)'
        )
        parser.add_argument(
            '--count',
            type=int,
            default=3,
            help='Number of dummy mappings to create (default: 3)'
        )
        parser.add_argument(
            '--user',
            type=str,
            default='testuser',
            help='Username to create mappings as (default: testuser)'
        )

    def handle(self, *args, **options):
        organization_id = options['organization']
        count = options['count']
        username = options['user']

        try:
            # Get or create user
            user, created = User.objects.get_or_create(username=username)
            if created:
                user.set_password('testpassword123')
                user.save()
                self.stdout.write(f"Created user: {username}")

            # Get CSV datasets for organization
            csv_datasets = self.get_csv_datasets_for_organization(organization_id)
            
            if not csv_datasets:
                raise CommandError(f"No CSV datasets found for organization '{organization_id}'")

            self.stdout.write(f"Found {len(csv_datasets)} datasets for organization '{organization_id}'")
            
            # Create dummy mappings
            for i in range(count):
                mapping = self._create_dummy_mapping(organization_id, csv_datasets, user, i + 1)
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created mapping '{mapping.name}' (ID: {mapping.id}) with {len(mapping.mapping_config.get('workspace_columns', {}))} columns"
                    )
                )

        except Exception as e:
            raise CommandError(f"Error creating dummy mappings: {str(e)}")

    def _create_dummy_mapping(self, organization_id, csv_datasets, user, index):
        """Create a single dummy mapping with realistic configuration."""
        
        # Select datasets for this mapping (2-4 datasets)
        import random
        selected_datasets = random.sample(csv_datasets, min(len(csv_datasets), random.randint(2, 4)))
        
        # Generate workspace columns
        workspace_columns = {}
        column_counter = 1
        
        for dataset in selected_datasets:
            dataset_name = dataset['name']
            columns = dataset.get('columns', [])
            
            # Select some columns from each dataset (3-6 columns per dataset)
            selected_columns = random.sample(columns, min(len(columns), random.randint(3, 6)))
            
            for i, column in enumerate(selected_columns):
                col_id = f"{organization_id}::{dataset_name}::{column['name']}"
                
                # Determine column properties
                is_anchor = i == 0 and len([c for c in workspace_columns.values() if c.get('dataset') == dataset_name]) == 0
                is_fk = column['name'].lower().endswith('_id') and not is_anchor
                is_multi_value = column['name'].lower() in ['tags', 'categories', 'keywords']
                
                workspace_columns[col_id] = {
                    'id': col_id,
                    'name': column['name'],
                    'dataset': dataset_name,
                    'source': f"S3:{organization_id}/{dataset_name}.csv",
                    'type': column.get('type', 'string'),
                    'added_at': f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}T{random.randint(10, 16):02d}:{random.randint(10, 59):02d}:00Z",
                    'is_anchor': is_anchor,
                    'is_fk': is_fk,
                    'is_multi_value': is_multi_value,
                    'is_relationship_context': False,
                    'is_external_ontology': False
                }
                
                # Add FK configuration if it's a foreign key
                if is_fk:
                    # Try to find a target in another dataset
                    target_datasets = [d for d in selected_datasets if d['name'] != dataset_name]
                    if target_datasets:
                        target_dataset = random.choice(target_datasets)
                        target_columns = [c for c in target_dataset.get('columns', []) if c['name'].lower().endswith('id')]
                        if target_columns:
                            target_column = random.choice(target_columns)
                            workspace_columns[col_id]['fk_config'] = {
                                'direction': 'outbound',
                                'target_dataset': target_dataset['name'],
                                'target_column': target_column['name']
                            }
                
                column_counter += 1

        # Create some relationship context columns (junction tables)
        if len(selected_datasets) >= 3:
            # Create a junction table relationship
            junction_dataset = selected_datasets[-1]  # Use last dataset as junction
            primary_dataset = selected_datasets[0]
            secondary_dataset = selected_datasets[1]
            
            # Find a suitable column for relationship context
            context_columns = [c for c in junction_dataset.get('columns', []) 
                             if 'relation' in c['name'].lower() or 'type' in c['name'].lower()]
            if context_columns:
                context_col = context_columns[0]
                col_id = f"{organization_id}::{junction_dataset['name']}::{context_col['name']}"
                
                if col_id not in workspace_columns:
                    workspace_columns[col_id] = {
                        'id': col_id,
                        'name': context_col['name'],
                        'dataset': junction_dataset['name'],
                        'source': f"S3:{organization_id}/{junction_dataset['name']}.csv",
                        'type': context_col.get('type', 'string'),
                        'added_at': f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}T{random.randint(10, 16):02d}:{random.randint(10, 59):02d}:00Z",
                        'is_anchor': False,
                        'is_fk': False,
                        'is_multi_value': False,
                        'is_relationship_context': True,
                        'is_external_ontology': False,
                        'relationship_context': {
                            'primary_fk_dataset': primary_dataset['name'],
                            'secondary_fk_dataset': secondary_dataset['name'],
                            'context_predicate': random.choice(['related_to', 'member_of', 'belongs_to', 'associated_with'])
                        }
                    }

        # Generate mapping configuration
        mapping_config = {
            'workspace_columns': workspace_columns,
            'selected_datasets': [d['name'] for d in selected_datasets],
            'column_selection': {},  # Empty for now
            'fk_relationships': {},  # Will be populated from workspace_columns
            'created_at': f"2024-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}T{random.randint(10, 16):02d}:{random.randint(10, 59):02d}:00Z"
        }

        # Create the mapping
        mapping_names = [
            f"Sample Mapping {index}",
            f"Test Dataset Relationships {index}",
            f"Demo Foreign Keys {index}",
            f"Example Junction Tables {index}",
            f"Research Data Model {index}"
        ]
        
        mapping_descriptions = [
            "Automatically generated test mapping with sample relationships",
            "Demo mapping showing foreign key relationships between datasets",
            "Example of junction table modeling with context predicates",
            "Test mapping for relationship visualization",
            "Sample data model for testing graph functionality"
        ]

        mapping = Mapping.objects.create(
            name=random.choice(mapping_names),
            description=random.choice(mapping_descriptions),
            organization_id=organization_id,
            mapping_config=mapping_config,
            validation_status=random.choice(['draft', 'validated', 'active']),
            created_by=user,
            source_datasets=[d['name'] for d in selected_datasets],
            execution_stats={}
        )

        return mapping