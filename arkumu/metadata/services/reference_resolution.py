"""
Reference Resolution Service

Handles cross-table references, foreign key resolution, and entity matching.
Provides strategies for resolving references between datasets.
"""

from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging
import re
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


class ResolutionStrategy(Enum):
    EXACT_MATCH = "exact_match"
    FUZZY_MATCH = "fuzzy_match"
    PATTERN_MATCH = "pattern_match"
    SEMANTIC_MATCH = "semantic_match"


class ResolutionStatus(Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"
    ERROR = "error"


@dataclass
class ResolutionCandidate:
    """A potential resolution candidate"""
    entity_id: str
    entity_data: Dict[str, Any]
    confidence_score: float
    match_method: str
    match_details: Dict[str, Any]


@dataclass
class ResolutionResult:
    """Result of a reference resolution attempt"""
    source_value: str
    status: ResolutionStatus
    resolved_entity_id: Optional[str]
    candidates: List[ResolutionCandidate]
    confidence_score: float
    resolution_method: str
    metadata: Dict[str, Any]


@dataclass
class EntityRegistry:
    """Registry of entities across datasets"""
    entities: Dict[str, Dict[str, Any]]  # entity_id -> entity_data
    indices: Dict[str, Dict[str, List[str]]]  # field_name -> value -> [entity_ids]
    datasets: Dict[str, str]  # entity_id -> dataset_path


class ReferenceResolutionService:
    """Service for resolving cross-table references and entity matching"""
    
    def __init__(self):
        self.entity_registry = EntityRegistry(
            entities={},
            indices={},
            datasets={}
        )
        self._resolution_strategies = {
            ResolutionStrategy.EXACT_MATCH: self._resolve_exact_match,
            ResolutionStrategy.FUZZY_MATCH: self._resolve_fuzzy_match,
            ResolutionStrategy.PATTERN_MATCH: self._resolve_pattern_match,
            ResolutionStrategy.SEMANTIC_MATCH: self._resolve_semantic_match,
        }
    
    def register_entities_from_dataset(self, dataset_path: str, entities: Dict[str, Dict[str, Any]], 
                                     indexable_fields: List[str] = None) -> int:
        """
        Register entities from a dataset into the global registry
        
        Args:
            dataset_path: Path to the dataset
            entities: Dictionary of entity_id -> entity_data
            indexable_fields: Fields to create indices for (for faster lookup)
            
        Returns:
            Number of entities registered
        """
        if indexable_fields is None:
            indexable_fields = ['source_value', 'name', 'title', 'label']
        
        registered_count = 0
        
        for entity_id, entity_data in entities.items():
            # Register entity
            self.entity_registry.entities[entity_id] = entity_data
            self.entity_registry.datasets[entity_id] = dataset_path
            
            # Create indices for faster lookup
            for field in indexable_fields:
                if field in entity_data and entity_data[field]:
                    value = str(entity_data[field]).lower()
                    
                    if field not in self.entity_registry.indices:
                        self.entity_registry.indices[field] = {}
                    
                    if value not in self.entity_registry.indices[field]:
                        self.entity_registry.indices[field][value] = []
                    
                    self.entity_registry.indices[field][value].append(entity_id)
            
            registered_count += 1
        
        logger.info(f"Registered {registered_count} entities from {dataset_path}")
        return registered_count
    
    def resolve_reference(self, source_value: str, target_entity_type: str = None,
                         strategy: ResolutionStrategy = ResolutionStrategy.EXACT_MATCH,
                         confidence_threshold: float = 0.8,
                         search_fields: List[str] = None) -> ResolutionResult:
        """
        Resolve a reference value to an entity
        
        Args:
            source_value: The value to resolve
            target_entity_type: Expected entity type (optional filter)
            strategy: Resolution strategy to use
            confidence_threshold: Minimum confidence for resolution
            search_fields: Fields to search in (defaults to common fields)
            
        Returns:
            ResolutionResult with resolution details
        """
        if search_fields is None:
            search_fields = ['source_value', 'name', 'title', 'label']
        
        try:
            # Get resolution strategy
            resolver = self._resolution_strategies.get(strategy)
            if not resolver:
                raise ValueError(f"Unknown resolution strategy: {strategy}")
            
            # Find candidates
            candidates = resolver(source_value, target_entity_type, search_fields)
            
            # Filter by confidence threshold
            high_confidence_candidates = [
                c for c in candidates if c.confidence_score >= confidence_threshold
            ]
            
            # Determine resolution status
            if not candidates:
                status = ResolutionStatus.UNRESOLVED
                resolved_entity_id = None
                final_confidence = 0.0
            elif len(high_confidence_candidates) == 1:
                status = ResolutionStatus.RESOLVED
                resolved_entity_id = high_confidence_candidates[0].entity_id
                final_confidence = high_confidence_candidates[0].confidence_score
            elif len(high_confidence_candidates) > 1:
                status = ResolutionStatus.AMBIGUOUS
                # Take highest confidence candidate
                best_candidate = max(high_confidence_candidates, key=lambda c: c.confidence_score)
                resolved_entity_id = best_candidate.entity_id
                final_confidence = best_candidate.confidence_score
            else:
                status = ResolutionStatus.UNRESOLVED
                resolved_entity_id = None
                final_confidence = max(c.confidence_score for c in candidates) if candidates else 0.0
            
            return ResolutionResult(
                source_value=source_value,
                status=status,
                resolved_entity_id=resolved_entity_id,
                candidates=candidates,
                confidence_score=final_confidence,
                resolution_method=strategy.value,
                metadata={
                    'search_fields': search_fields,
                    'target_entity_type': target_entity_type,
                    'confidence_threshold': confidence_threshold,
                    'total_candidates': len(candidates),
                    'high_confidence_candidates': len(high_confidence_candidates)
                }
            )
            
        except Exception as e:
            logger.error(f"Error resolving reference '{source_value}': {str(e)}")
            return ResolutionResult(
                source_value=source_value,
                status=ResolutionStatus.ERROR,
                resolved_entity_id=None,
                candidates=[],
                confidence_score=0.0,
                resolution_method=strategy.value,
                metadata={'error': str(e)}
            )
    
    def _resolve_exact_match(self, source_value: str, target_entity_type: str = None,
                           search_fields: List[str] = None) -> List[ResolutionCandidate]:
        """Resolve using exact string matching"""
        candidates = []
        search_value = str(source_value).lower()
        
        for field in search_fields:
            if field in self.entity_registry.indices:
                matching_entity_ids = self.entity_registry.indices[field].get(search_value, [])
                
                for entity_id in matching_entity_ids:
                    entity_data = self.entity_registry.entities[entity_id]
                    
                    # Filter by entity type if specified
                    if target_entity_type and entity_data.get('type') != target_entity_type:
                        continue
                    
                    candidate = ResolutionCandidate(
                        entity_id=entity_id,
                        entity_data=entity_data,
                        confidence_score=1.0,  # Exact match = 100% confidence
                        match_method='exact_match',
                        match_details={
                            'matched_field': field,
                            'matched_value': source_value
                        }
                    )
                    candidates.append(candidate)
        
        return candidates
    
    def _resolve_fuzzy_match(self, source_value: str, target_entity_type: str = None,
                           search_fields: List[str] = None) -> List[ResolutionCandidate]:
        """Resolve using fuzzy string matching"""
        candidates = []
        search_value = str(source_value).lower()
        
        for field in search_fields:
            if field in self.entity_registry.indices:
                # Check all values in the index for this field
                for indexed_value, entity_ids in self.entity_registry.indices[field].items():
                    # Calculate similarity score
                    similarity = SequenceMatcher(None, search_value, indexed_value).ratio()
                    
                    # Only consider reasonably similar values
                    if similarity >= 0.6:
                        for entity_id in entity_ids:
                            entity_data = self.entity_registry.entities[entity_id]
                            
                            # Filter by entity type if specified
                            if target_entity_type and entity_data.get('type') != target_entity_type:
                                continue
                            
                            candidate = ResolutionCandidate(
                                entity_id=entity_id,
                                entity_data=entity_data,
                                confidence_score=similarity,
                                match_method='fuzzy_match',
                                match_details={
                                    'matched_field': field,
                                    'search_value': source_value,
                                    'matched_value': indexed_value,
                                    'similarity_score': similarity
                                }
                            )
                            candidates.append(candidate)
        
        # Sort by confidence score (highest first)
        candidates.sort(key=lambda c: c.confidence_score, reverse=True)
        
        # Remove duplicates (same entity_id)
        seen_entities = set()
        unique_candidates = []
        for candidate in candidates:
            if candidate.entity_id not in seen_entities:
                unique_candidates.append(candidate)
                seen_entities.add(candidate.entity_id)
        
        return unique_candidates[:10]  # Limit to top 10 candidates
    
    def _resolve_pattern_match(self, source_value: str, target_entity_type: str = None,
                             search_fields: List[str] = None) -> List[ResolutionCandidate]:
        """Resolve using pattern matching (e.g., ID patterns)"""
        candidates = []
        
        # Define common ID patterns
        id_patterns = [
            r'^(\d+)$',  # Pure numeric
            r'^[A-Z]+_(\d+)$',  # Prefix_Number
            r'^(\d+)_.*',  # Number_Suffix
            r'^.*_(\d+)$',  # Prefix_Number
        ]
        
        # Try to extract ID components from source value
        source_id_components = self._extract_id_components(source_value, id_patterns)
        
        for entity_id, entity_data in self.entity_registry.entities.items():
            # Filter by entity type if specified
            if target_entity_type and entity_data.get('type') != target_entity_type:
                continue
            
            # Check each search field
            for field in search_fields:
                if field in entity_data and entity_data[field]:
                    entity_value = str(entity_data[field])
                    entity_id_components = self._extract_id_components(entity_value, id_patterns)
                    
                    # Calculate pattern match score
                    match_score = self._calculate_pattern_match_score(
                        source_id_components, entity_id_components
                    )
                    
                    if match_score > 0.7:  # Reasonable pattern match
                        candidate = ResolutionCandidate(
                            entity_id=entity_id,
                            entity_data=entity_data,
                            confidence_score=match_score,
                            match_method='pattern_match',
                            match_details={
                                'matched_field': field,
                                'source_components': source_id_components,
                                'entity_components': entity_id_components,
                                'pattern_score': match_score
                            }
                        )
                        candidates.append(candidate)
                        break  # Don't match multiple fields for same entity
        
        # Sort by confidence score
        candidates.sort(key=lambda c: c.confidence_score, reverse=True)
        return candidates[:5]  # Limit to top 5
    
    def _resolve_semantic_match(self, source_value: str, target_entity_type: str = None,
                              search_fields: List[str] = None) -> List[ResolutionCandidate]:
        """Resolve using semantic/contextual matching"""
        # Placeholder for semantic matching
        # Would use NLP techniques, word embeddings, etc.
        # For now, return empty list
        return []
    
    def _extract_id_components(self, value: str, patterns: List[str]) -> Dict[str, str]:
        """Extract ID components using regex patterns"""
        components = {'full_value': value}
        
        for pattern in patterns:
            match = re.match(pattern, value)
            if match:
                components['numeric_part'] = match.group(1)
                components['pattern'] = pattern
                break
        
        return components
    
    def _calculate_pattern_match_score(self, source_components: Dict[str, str],
                                     entity_components: Dict[str, str]) -> float:
        """Calculate how well two sets of ID components match"""
        score = 0.0
        
        # Full value exact match
        if source_components['full_value'] == entity_components['full_value']:
            return 1.0
        
        # Pattern match
        if ('pattern' in source_components and 'pattern' in entity_components and
            source_components['pattern'] == entity_components['pattern']):
            score += 0.5
            
            # Numeric part match
            if ('numeric_part' in source_components and 'numeric_part' in entity_components and
                source_components['numeric_part'] == entity_components['numeric_part']):
                score += 0.5
        
        return score
    
    def bulk_resolve_references(self, references: List[Tuple[str, str]], 
                              strategy: ResolutionStrategy = ResolutionStrategy.EXACT_MATCH,
                              confidence_threshold: float = 0.8) -> Dict[str, ResolutionResult]:
        """
        Resolve multiple references in bulk
        
        Args:
            references: List of (source_value, target_entity_type) tuples
            strategy: Resolution strategy to use
            confidence_threshold: Minimum confidence for resolution
            
        Returns:
            Dictionary mapping source_value to ResolutionResult
        """
        results = {}
        
        for source_value, target_entity_type in references:
            result = self.resolve_reference(
                source_value=source_value,
                target_entity_type=target_entity_type,
                strategy=strategy,
                confidence_threshold=confidence_threshold
            )
            results[source_value] = result
        
        return results
    
    def get_resolution_statistics(self) -> Dict[str, Any]:
        """Get statistics about the entity registry and resolutions"""
        total_entities = len(self.entity_registry.entities)
        entities_by_type = {}
        entities_by_dataset = {}
        
        for entity_id, entity_data in self.entity_registry.entities.items():
            # Count by type
            entity_type = entity_data.get('type', 'unknown')
            entities_by_type[entity_type] = entities_by_type.get(entity_type, 0) + 1
            
            # Count by dataset
            dataset = self.entity_registry.datasets.get(entity_id, 'unknown')
            entities_by_dataset[dataset] = entities_by_dataset.get(dataset, 0) + 1
        
        return {
            'total_entities': total_entities,
            'entities_by_type': entities_by_type,
            'entities_by_dataset': entities_by_dataset,
            'indexed_fields': list(self.entity_registry.indices.keys()),
            'index_sizes': {field: len(index) for field, index in self.entity_registry.indices.items()}
        }
    
    def clear_registry(self):
        """Clear the entity registry"""
        self.entity_registry.entities.clear()
        self.entity_registry.indices.clear()
        self.entity_registry.datasets.clear()
        logger.info("Entity registry cleared")
    
    def export_registry(self) -> Dict[str, Any]:
        """Export the entity registry for persistence"""
        return {
            'entities': self.entity_registry.entities,
            'datasets': self.entity_registry.datasets,
            # Skip indices as they can be rebuilt
        }
    
    def import_registry(self, registry_data: Dict[str, Any], rebuild_indices: bool = True):
        """Import entity registry from exported data"""
        self.entity_registry.entities = registry_data.get('entities', {})
        self.entity_registry.datasets = registry_data.get('datasets', {})
        
        if rebuild_indices:
            self._rebuild_indices()
        
        logger.info(f"Imported {len(self.entity_registry.entities)} entities")
    
    def _rebuild_indices(self):
        """Rebuild indices from current entities"""
        self.entity_registry.indices.clear()
        
        indexable_fields = ['source_value', 'name', 'title', 'label']
        
        for entity_id, entity_data in self.entity_registry.entities.items():
            for field in indexable_fields:
                if field in entity_data and entity_data[field]:
                    value = str(entity_data[field]).lower()
                    
                    if field not in self.entity_registry.indices:
                        self.entity_registry.indices[field] = {}
                    
                    if value not in self.entity_registry.indices[field]:
                        self.entity_registry.indices[field][value] = []
                    
                    self.entity_registry.indices[field][value].append(entity_id)
        
        logger.info("Entity indices rebuilt") 