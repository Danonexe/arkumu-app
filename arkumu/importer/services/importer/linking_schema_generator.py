import json
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum

logger = logging.getLogger(__name__)


class LinkType(Enum):
    """Types of links that can be created between resources."""
    FOREIGN_KEY = "foreign_key"
    DUPLICATE = "duplicate"
    RELATED = "related"
    HIERARCHICAL = "hierarchical"


class MergeStrategy(Enum):
    """Strategies for handling duplicates."""
    PREFER_FIRST = "prefer_first"
    PREFER_LAST = "prefer_last"
    MERGE_ALL = "merge_all"
    MANUAL_REVIEW = "manual_review"


@dataclass
class ColumnReference:
    """Reference to a specific column in a CSV file."""
    file: str
    column: str
    
    def __str__(self):
        return f"{self.file}.{self.column}"


@dataclass
class LinkRule:
    """Rule for linking two columns/resources."""
    source: ColumnReference
    target: ColumnReference
    link_type: LinkType
    confidence: float
    shared_count: int
    description: str
    evidence: Dict[str, Any]
    
    def to_dict(self):
        return {
            "source": {"file": self.source.file, "column": self.source.column},
            "target": {"file": self.target.file, "column": self.target.column},
            "link_type": self.link_type.value,
            "confidence": self.confidence,
            "shared_count": self.shared_count,
            "description": self.description,
            "evidence": self.evidence
        }


@dataclass
class DuplicateRule:
    """Rule for handling duplicate entities."""
    columns: List[ColumnReference]
    merge_strategy: MergeStrategy
    confidence: float
    description: str
    
    def to_dict(self):
        return {
            "columns": [{"file": col.file, "column": col.column} for col in self.columns],
            "merge_strategy": self.merge_strategy.value,
            "confidence": self.confidence,
            "description": self.description
        }


@dataclass
class LinkingSchema:
    """Complete schema for linking resources after import."""
    version: str
    generated_at: str
    source_analysis: Dict[str, Any]
    foreign_keys: List[LinkRule]
    duplicates: List[DuplicateRule]
    related_entities: List[LinkRule]
    hierarchical_links: List[LinkRule]
    statistics: Dict[str, Any]
    
    def to_dict(self):
        return {
            "version": self.version,
            "generated_at": self.generated_at,
            "source_analysis": self.source_analysis,
            "foreign_keys": [rule.to_dict() for rule in self.foreign_keys],
            "duplicates": [rule.to_dict() for rule in self.duplicates],
            "related_entities": [rule.to_dict() for rule in self.related_entities],
            "hierarchical_links": [rule.to_dict() for rule in self.hierarchical_links],
            "statistics": self.statistics
        }
    
    def save_to_file(self, file_path: str):
        """Save the linking schema to a JSON file."""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)
        logger.info(f"Linking schema saved to: {file_path}")


class LinkingSchemaGenerator:
    """Generates linking schemas from relationship analysis results."""
    
    def __init__(self, confidence_thresholds: Optional[Dict[str, float]] = None):
        """
        Initialize the schema generator.
        
        Args:
            confidence_thresholds: Minimum confidence levels for different link types
        """
        self.confidence_thresholds = confidence_thresholds or {
            "foreign_key": 0.8,
            "duplicate": 0.9,
            "related": 0.5,
            "hierarchical": 0.7
        }
    
    def generate_schema(self, analysis_results: Dict[str, Any]) -> LinkingSchema:
        """
        Generate a linking schema from relationship analysis results.
        
        Args:
            analysis_results: Output from RelationshipAnalyzer
            
        Returns:
            LinkingSchema object
        """
        logger.info("🔗 Generating linking schema from relationship analysis...")
        
        relationships = analysis_results.get('relationships', [])
        summary = analysis_results.get('summary', {})
        
        # Categorize relationships into different link types
        foreign_keys = self._extract_foreign_keys(relationships)
        duplicates = self._extract_duplicates(relationships)
        related_entities = self._extract_related_entities(relationships)
        hierarchical_links = self._extract_hierarchical_links(relationships)
        
        # Generate statistics
        statistics = self._generate_statistics(foreign_keys, duplicates, related_entities, hierarchical_links)
        
        # Create schema
        from datetime import datetime
        schema = LinkingSchema(
            version="1.0",
            generated_at=datetime.now().isoformat(),
            source_analysis=summary,
            foreign_keys=foreign_keys,
            duplicates=duplicates,
            related_entities=related_entities,
            hierarchical_links=hierarchical_links,
            statistics=statistics
        )
        
        logger.info(f"✅ Generated linking schema with {len(foreign_keys)} foreign keys, "
                   f"{len(duplicates)} duplicate groups, {len(related_entities)} related entities")
        
        return schema
    
    def _extract_foreign_keys(self, relationships: List[Dict]) -> List[LinkRule]:
        """Extract foreign key relationships."""
        foreign_keys = []
        
        for rel in relationships:
            if (rel['type'] == 'many_to_one' and 
                rel['confidence'] >= self.confidence_thresholds['foreign_key']):
                
                # Determine source and target based on direction
                if rel['direction'] == '1_to_2':
                    source = ColumnReference(rel['file1'], rel['column1'])
                    target = ColumnReference(rel['file2'], rel['column2'])
                else:  # direction == '2_to_1'
                    source = ColumnReference(rel['file2'], rel['column2'])
                    target = ColumnReference(rel['file1'], rel['column1'])
                
                foreign_keys.append(LinkRule(
                    source=source,
                    target=target,
                    link_type=LinkType.FOREIGN_KEY,
                    confidence=rel['confidence'],
                    shared_count=rel['shared_count'],
                    description=rel['description'],
                    evidence=rel['evidence']
                ))
        
        return foreign_keys
    
    def _extract_duplicates(self, relationships: List[Dict]) -> List[DuplicateRule]:
        """Extract duplicate entity relationships."""
        duplicates = []
        
        # Group one-to-one relationships that might be duplicates
        one_to_one_rels = [rel for rel in relationships 
                          if rel['type'] == 'one_to_one' and 
                          rel['confidence'] >= self.confidence_thresholds['duplicate']]
        
        # Group by similar confidence and shared values
        duplicate_groups = {}
        for rel in one_to_one_rels:
            key = f"{rel['shared_count']}_{rel['confidence']:.2f}"
            if key not in duplicate_groups:
                duplicate_groups[key] = []
            duplicate_groups[key].append(rel)
        
        for group in duplicate_groups.values():
            if len(group) >= 1:  # Even single high-confidence one-to-one can be duplicate
                columns = []
                for rel in group:
                    columns.extend([
                        ColumnReference(rel['file1'], rel['column1']),
                        ColumnReference(rel['file2'], rel['column2'])
                    ])
                
                # Remove duplicates while preserving order
                unique_columns = []
                seen = set()
                for col in columns:
                    col_str = str(col)
                    if col_str not in seen:
                        unique_columns.append(col)
                        seen.add(col_str)
                
                if len(unique_columns) >= 2:
                    avg_confidence = sum(rel['confidence'] for rel in group) / len(group)
                    
                    duplicates.append(DuplicateRule(
                        columns=unique_columns,
                        merge_strategy=MergeStrategy.MERGE_ALL if avg_confidence > 0.95 else MergeStrategy.MANUAL_REVIEW,
                        confidence=avg_confidence,
                        description=f"Potential duplicate entities across {len(unique_columns)} columns"
                    ))
        
        return duplicates
    
    def _extract_related_entities(self, relationships: List[Dict]) -> List[LinkRule]:
        """Extract related entity relationships (many-to-many, partial overlap)."""
        related = []
        
        for rel in relationships:
            if (rel['type'] in ['many_to_many', 'partial_overlap'] and 
                rel['confidence'] >= self.confidence_thresholds['related']):
                
                related.append(LinkRule(
                    source=ColumnReference(rel['file1'], rel['column1']),
                    target=ColumnReference(rel['file2'], rel['column2']),
                    link_type=LinkType.RELATED,
                    confidence=rel['confidence'],
                    shared_count=rel['shared_count'],
                    description=rel['description'],
                    evidence=rel['evidence']
                ))
        
        return related
    
    def _extract_hierarchical_links(self, relationships: List[Dict]) -> List[LinkRule]:
        """Extract hierarchical relationships (subset relationships)."""
        hierarchical = []
        
        for rel in relationships:
            if (rel['type'] == 'subset' and 
                rel['confidence'] >= self.confidence_thresholds['hierarchical']):
                
                # Determine parent and child based on direction
                if rel['direction'] == '1_subset_of_2':
                    source = ColumnReference(rel['file1'], rel['column1'])  # child
                    target = ColumnReference(rel['file2'], rel['column2'])  # parent
                else:  # direction == '2_subset_of_1'
                    source = ColumnReference(rel['file2'], rel['column2'])  # child
                    target = ColumnReference(rel['file1'], rel['column1'])  # parent
                
                hierarchical.append(LinkRule(
                    source=source,
                    target=target,
                    link_type=LinkType.HIERARCHICAL,
                    confidence=rel['confidence'],
                    shared_count=rel['shared_count'],
                    description=rel['description'],
                    evidence=rel['evidence']
                ))
        
        return hierarchical
    
    def _generate_statistics(self, foreign_keys: List[LinkRule], duplicates: List[DuplicateRule], 
                           related: List[LinkRule], hierarchical: List[LinkRule]) -> Dict[str, Any]:
        """Generate statistics about the linking schema."""
        
        total_links = len(foreign_keys) + len(duplicates) + len(related) + len(hierarchical)
        
        # Calculate confidence distribution
        all_confidences = ([fk.confidence for fk in foreign_keys] + 
                          [dup.confidence for dup in duplicates] + 
                          [rel.confidence for rel in related] + 
                          [hier.confidence for hier in hierarchical])
        
        avg_confidence = sum(all_confidences) / len(all_confidences) if all_confidences else 0
        high_confidence_count = sum(1 for conf in all_confidences if conf > 0.8)
        
        # Count unique files involved
        unique_files = set()
        for fk in foreign_keys:
            unique_files.add(fk.source.file)
            unique_files.add(fk.target.file)
        for dup in duplicates:
            for col in dup.columns:
                unique_files.add(col.file)
        for rel in related:
            unique_files.add(rel.source.file)
            unique_files.add(rel.target.file)
        for hier in hierarchical:
            unique_files.add(hier.source.file)
            unique_files.add(hier.target.file)
        
        return {
            "total_links": total_links,
            "foreign_keys_count": len(foreign_keys),
            "duplicates_count": len(duplicates),
            "related_entities_count": len(related),
            "hierarchical_links_count": len(hierarchical),
            "average_confidence": round(avg_confidence, 3),
            "high_confidence_links": high_confidence_count,
            "files_involved": len(unique_files),
            "confidence_distribution": {
                "very_high": sum(1 for conf in all_confidences if conf > 0.9),
                "high": sum(1 for conf in all_confidences if 0.8 < conf <= 0.9),
                "medium": sum(1 for conf in all_confidences if 0.6 < conf <= 0.8),
                "low": sum(1 for conf in all_confidences if conf <= 0.6)
            }
        }


def generate_linking_schema_from_analysis(analysis_results: Dict[str, Any], 
                                        output_file: Optional[str] = None,
                                        confidence_thresholds: Optional[Dict[str, float]] = None) -> LinkingSchema:
    """
    Convenience function to generate a linking schema from analysis results.
    
    Args:
        analysis_results: Output from RelationshipAnalyzer
        output_file: Optional path to save the schema JSON file
        confidence_thresholds: Optional custom confidence thresholds
        
    Returns:
        LinkingSchema object
    """
    generator = LinkingSchemaGenerator(confidence_thresholds)
    schema = generator.generate_schema(analysis_results)
    
    if output_file:
        schema.save_to_file(output_file)
    
    return schema


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        analysis_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else "linking_schema.json"
        
        print(f"Loading analysis from: {analysis_file}")
        with open(analysis_file, 'r') as f:
            analysis_results = json.load(f)
        
        schema = generate_linking_schema_from_analysis(analysis_results, output_file)
        print(f"Generated linking schema with {schema.statistics['total_links']} links")
    else:
        print("Usage: python linking_schema_generator.py <analysis_file.json> [output_file.json]") 