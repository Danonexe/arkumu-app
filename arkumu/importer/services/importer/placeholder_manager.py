import logging
import uuid
from typing import Dict, List, Any, Optional

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.models.triples import Triple

logger = logging.getLogger(__name__)

class PlaceholderManager:
    """
    Manages placeholder creation, resolution, and tracking for the import workflow.
    Uses unique hex identifiers for reliable placeholder resolution.
    """
    
    @staticmethod
    def create_placeholders_for_references(
        row: Dict[str, str],
        table_name: str,
        row_id: str,
        institution: str,
        base_uri: str,
        reference_resolver
    ) -> int:
        """
        Create placeholders for any foreign key references in this row.
        Each placeholder gets a unique hex identifier for easy resolution.
        
        Args:
            row: Dictionary of column values for the current row
            table_name: Name of the table being processed
            row_id: ID of the current row
            institution: Institution code
            base_uri: Base URI for resources
            reference_resolver: Instance of ReferenceResolver for detecting references
            
        Returns:
            int: Number of placeholders created
        """
        logger.debug(f"🔧 Starting create_placeholders_for_references: table={table_name}, row_id={row_id}")
        placeholders_created = 0
        
        try:
            logger.debug(f"🔧 Processing {len(row)} columns in row")
            for i, (column_name, value) in enumerate(row.items()):
                if i % 10 == 0:  # Log every 10th column to avoid spam
                    logger.debug(f"🔧 Processing column {i+1}/{len(row)}: {column_name}")
                
                if not value or value.strip() == '':
                    continue
                    
                # Check if this looks like a reference column
                logger.debug(f"🔧 Checking if {column_name} is reference column")
                if reference_resolver.is_reference_column(column_name, value):
                    logger.debug(f"🔧 {column_name} is a reference column, parsing...")
                    target_table, target_id = reference_resolver.parse_reference(column_name, value)
                    
                    if target_table and target_id:
                        logger.debug(f"🔧 Parsed reference: {target_table}:{target_id}")
                        
                        # Always create placeholder - we'll resolve them later in batch
                        # This avoids expensive existence checks during import
                        logger.debug(f"🔧 Creating placeholder for reference")
                        
                        # Generate unique hex identifier for this placeholder
                        placeholder_hex = uuid.uuid4().hex[:12]  # 12-char hex ID
                        
                        # Create placeholder with unique identifier
                        placeholder_name = f"PLACEHOLDER:{placeholder_hex}"
                        placeholder_uri = f"{base_uri}/placeholders/{placeholder_hex}"
                        
                        # Store the exact reference value for direct matching
                        mapping_info = f"reference_value={target_id},column={column_name}"
                        
                        # Create placeholder directly without checking for duplicates
                        # Duplicates will be handled during resolution
                        logger.debug(f"🔧 Creating placeholder resource")
                        placeholder = Resource.objects.create(
                            uri=placeholder_uri,
                            name=placeholder_name,
                            value=mapping_info,
                            resource_type=ResourceType.IRI,
                            source=institution,
                            is_placeholder=True
                        )
                        
                        placeholders_created += 1
                        logger.debug(f"🔗 Created placeholder: {placeholder_name} -> {mapping_info}")
                            
        except Exception as e:
            logger.error(f"Error creating placeholders for {table_name} row {row_id}: {e}")
            
        if placeholders_created > 0:
            logger.info(f"📝 Created {placeholders_created} placeholders for {table_name} row {row_id}")
        
        logger.debug(f"🔧 Finished create_placeholders_for_references: created {placeholders_created}")
        return placeholders_created
    
    @staticmethod
    def resolve_placeholders_for_entity(
        table_name: str,
        entity_id: str,
        institution: str,
        base_uri: str
    ) -> int:
        """
        Resolve any placeholders that reference this entity using the hex-based approach.
        
        Args:
            table_name: Name of the table being imported (for URI generation)
            entity_id: ID of the entity that was just created
            institution: Institution code
            base_uri: Base URI for resources
            
        Returns:
            int: Number of placeholders resolved
        """
        logger.debug(f"🔧 Starting resolve_placeholders_for_entity: table={table_name}, entity_id={entity_id}")
        
        try:
            # Look for placeholders that reference this exact entity_id value
            # The mapping info is stored in the value field as: reference_value=X,column=Y
            reference_pattern = f"reference_value={entity_id}"
            logger.debug(f"🔧 Looking for placeholders with pattern: {reference_pattern}")
            
            # Find all placeholders that reference this entity
            logger.debug(f"🔧 Querying database for placeholders")
            placeholders = Resource.objects.filter(
                source=institution,
                is_placeholder=True,
                value__contains=reference_pattern
            )
            
            placeholder_count = placeholders.count()
            logger.debug(f"🔧 Found {placeholder_count} placeholders to resolve")
            
            resolved_count = 0
            if placeholders.exists():
                # Use the same URI pattern as bulk_import.py
                entity_uri = f"{base_uri}/datasets/{table_name}/{entity_id}"
                logger.debug(f"🔧 Entity URI: {entity_uri}")
                
                for i, placeholder in enumerate(placeholders):
                    logger.debug(f"🔧 Processing placeholder {i+1}/{placeholder_count}: {placeholder.name}")
                    try:
                        # Find all triples that reference this placeholder
                        logger.debug(f"🔧 Finding triples for placeholder {placeholder.uri}")
                        referencing_triples = Triple.objects.filter(
                            object__uri=placeholder.uri,
                            object__source=institution
                        )
                        
                        triple_count = referencing_triples.count()
                        logger.debug(f"🔧 Found {triple_count} triples to update")
                        
                        # Update each triple to point to the real entity
                        for j, triple in enumerate(referencing_triples):
                            if j % 10 == 0:  # Log every 10th triple
                                logger.debug(f"🔧 Updating triple {j+1}/{triple_count}")
                            
                            # Get or create the real entity resource
                            real_entity, created = Resource.objects.get_or_create(
                                uri=entity_uri,
                                defaults={
                                    "resource_type": ResourceType.IRI,
                                    "name": f"{table_name}_{entity_id}",
                                    "source": institution
                                }
                            )
                            
                            # Update the triple to point to the real entity
                            triple.object = real_entity
                            triple.save()
                        
                        # Delete the placeholder
                        logger.debug(f"🔧 Deleting placeholder {placeholder.name}")
                        placeholder.delete()
                        resolved_count += 1
                        
                        logger.debug(f"✅ Resolved placeholder: {placeholder.name} -> {table_name}:{entity_id}")
                        
                    except Exception as e:
                        logger.error(f"Error resolving placeholder {placeholder.uri}: {e}")
                        continue
            
            logger.debug(f"🔧 Finished resolve_placeholders_for_entity: resolved {resolved_count}")
            return resolved_count
            
        except Exception as e:
            logger.error(f"Error resolving placeholders for {table_name}:{entity_id}: {e}")
            return 0
    
    @staticmethod
    def batch_resolve_placeholders_for_table(
        table_name: str,
        entity_ids: List[str],
        institution: str,
        base_uri: str
    ) -> int:
        """
        Efficiently resolve placeholders for multiple entities in a single table.
        This avoids database deadlocks by batching operations.
        
        Args:
            table_name: Name of the table being imported
            entity_ids: List of entity IDs that were just created
            institution: Institution code
            base_uri: Base URI for resources
            
        Returns:
            int: Number of placeholders resolved
        """
        logger.debug(f"🔧 Starting batch_resolve_placeholders_for_table: table={table_name}, entities={len(entity_ids)}")
        logger.debug(f"🔧 Entity IDs to resolve: {entity_ids}")
        
        # First, let's see what placeholders exist
        all_placeholders = Resource.objects.filter(
            source=institution,
            is_placeholder=True
        )
        logger.debug(f"🔧 Total placeholders in system: {all_placeholders.count()}")
        for i, placeholder in enumerate(all_placeholders[:5]):  # Show first 5
            logger.debug(f"🔧 Placeholder {i+1}: name={placeholder.name}, value={placeholder.value}")
        
        if not entity_ids:
            return 0
        
        try:
            resolved_count = 0
            
            # For each entity, find and resolve its placeholders
            for entity_id in entity_ids:
                # Look for placeholders that reference this exact entity_id value
                reference_pattern = f"reference_value={entity_id}"
                logger.debug(f"🔧 Looking for placeholders with pattern: {reference_pattern}")
                
                # Find placeholders for this specific entity
                placeholders = Resource.objects.filter(
                    source=institution,
                    is_placeholder=True,
                    value__contains=reference_pattern
                )
                
                placeholder_count = placeholders.count()
                logger.debug(f"🔧 Found {placeholder_count} placeholders for {table_name}:{entity_id}")
                
                if placeholders.exists():
                    # Use the same URI pattern as bulk_import.py
                    entity_uri = f"{base_uri}/datasets/{table_name}/{entity_id}"
                    
                    # Get or create the real entity resource once
                    real_entity, created = Resource.objects.get_or_create(
                        uri=entity_uri,
                        defaults={
                            "resource_type": ResourceType.IRI,
                            "name": f"{table_name}_{entity_id}",
                            "source": institution
                        }
                    )
                    
                    # Batch update all triples that reference these placeholders
                    for placeholder in placeholders:
                        # Update triples in batch
                        Triple.objects.filter(
                            object__uri=placeholder.uri,
                            object__source=institution
                        ).update(object=real_entity)
                        
                        resolved_count += 1
                    
                    # Delete all placeholders for this entity in batch
                    placeholders.delete()
                    
                    logger.debug(f"✅ Resolved {placeholders.count()} placeholders for {table_name}:{entity_id}")
            
            logger.debug(f"🔧 Finished batch_resolve_placeholders_for_table: resolved {resolved_count}")
            return resolved_count
            
        except Exception as e:
            logger.error(f"Error batch resolving placeholders for {table_name}: {e}")
            return 0
    
    @staticmethod
    def get_unresolved_placeholders(institution: str) -> List[Dict[str, str]]:
        """
        Get all unresolved placeholders for the given institution.
        
        Args:
            institution: Institution code
            
        Returns:
            List of dictionaries with placeholder information
        """
        try:
            placeholders = Resource.objects.filter(
                source=institution,
                name__startswith="PLACEHOLDER:",
                is_placeholder=True
            )
            
            result = []
            for placeholder in placeholders:
                # Parse placeholder info
                if placeholder.name and placeholder.name.startswith("PLACEHOLDER:"):
                    reference_info = placeholder.name[11:]  # Remove "PLACEHOLDER:" prefix
                    
                    result.append({
                        "uri": placeholder.uri,
                        "reference": reference_info,
                        "name": placeholder.name,
                        "value": placeholder.value
                    })
                    
            return result
            
        except Exception as e:
            logger.error(f"Error getting unresolved placeholders: {e}")
            return []
    
    @staticmethod
    def count_placeholders(institution: str) -> int:
        """
        Count the number of unresolved placeholders for an institution.
        
        Args:
            institution: Institution code
            
        Returns:
            int: Number of unresolved placeholders
        """
        try:
            return Resource.objects.filter(
                source=institution,
                name__startswith="PLACEHOLDER:",
                is_placeholder=True
            ).count()
        except Exception as e:
            logger.error(f"Error counting placeholders: {e}")
            return 0
    
    @staticmethod
    def analyze_placeholder_patterns(institution: str) -> Dict[str, Any]:
        """
        Analyze patterns in unresolved placeholders to help debug issues.
        
        Args:
            institution: Institution code
            
        Returns:
            Dict with analysis results
        """
        try:
            placeholders = PlaceholderManager.get_unresolved_placeholders(institution)
            
            # Group by target table
            table_counts = {}
            for placeholder in placeholders:
                reference = placeholder['reference']
                if '_id=' in reference:
                    table_name = reference.split('_id=')[0]
                    table_counts[table_name] = table_counts.get(table_name, 0) + 1
            
            # Sort by count
            sorted_tables = sorted(table_counts.items(), key=lambda x: x[1], reverse=True)
            
            analysis = {
                "total_placeholders": len(placeholders),
                "tables_with_missing_references": len(table_counts),
                "top_missing_tables": sorted_tables[:10],
                "sample_placeholders": placeholders[:20]
            }
            
            return analysis
            
        except Exception as e:
            logger.error(f"Error analyzing placeholder patterns: {e}")
            return {"error": str(e)}

    @staticmethod
    def _find_matching_placeholders_by_similarity(
        table_name: str, 
        entity_id: str, 
        institution: str,
        possible_names: List[str]
    ) -> List[str]:
        """
        No fuzzy matching - only exact matches.
        
        Returns:
            Empty list - no additional matches
        """
        # No fuzzy matching - keep it simple
        return [] 