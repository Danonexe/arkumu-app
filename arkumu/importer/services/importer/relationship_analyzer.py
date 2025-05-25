import os
import csv
import logging
from typing import Dict, List, Set, Tuple, Any
from collections import defaultdict

logger = logging.getLogger(__name__)


class RelationshipAnalyzer:
    """
    Analyzes relationships between CSV files based purely on shared values.
    No assumptions about column names, data types, or structure.
    """
    
    def __init__(self, delimiter: str = ';'):
        self.delimiter = delimiter
    
    def analyze_directory(self, csv_directory: str) -> Dict[str, Any]:
        """
        Analyze all CSV files in a directory to discover relationships.
        
        Args:
            csv_directory: Path to directory containing CSV files
            
        Returns:
            Dictionary containing analysis results
        """
        logger.debug(f"🔍 Starting relationship analysis of directory: {csv_directory}")
        
        # Step 1: Extract all column values
        logger.debug("📊 Step 1: Extracting values from all columns...")
        column_data = self._extract_all_column_values(csv_directory)
        logger.debug(f"   Found {len(column_data)} columns across all files")
        
        # Step 2: Find value intersections
        logger.debug("🔗 Step 2: Finding value intersections between columns...")
        intersections = self._find_value_intersections(column_data)
        logger.debug(f"   Found {len(intersections)} column pairs with shared values")
        
        # Step 3: Classify relationship patterns
        logger.debug("🎯 Step 3: Classifying relationship patterns...")
        relationships = self._classify_relationship_patterns(intersections)
        logger.debug(f"   Identified {len(relationships)} potential relationships")
        
        # Step 4: Generate summary statistics
        summary = self._generate_summary(column_data, intersections, relationships)
        
        logger.debug("✅ Relationship analysis completed")
        
        return {
            'column_data': column_data,
            'intersections': intersections,
            'relationships': relationships,
            'summary': summary
        }
    
    def _extract_all_column_values(self, csv_directory: str) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Extract all values from every column in every CSV file."""
        
        column_data = {}
        csv_files = [f for f in os.listdir(csv_directory) if f.endswith('.csv')]
        
        for csv_file in csv_files:
            file_path = os.path.join(csv_directory, csv_file)
            logger.debug(f"   Processing file: {csv_file}")
            
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f, delimiter=self.delimiter)
                    
                    # Initialize column data for this file
                    for column in reader.fieldnames or []:
                        key = (csv_file, column)
                        column_data[key] = {
                            'values': set(),
                            'total_rows': 0,
                            'non_empty_rows': 0,
                            'sample_values': []
                        }
                    
                    # Collect all values
                    for row_num, row in enumerate(reader):
                        for column in reader.fieldnames or []:
                            key = (csv_file, column)
                            column_data[key]['total_rows'] += 1
                            
                            value = row.get(column, '')
                            if value and str(value).strip():
                                clean_value = str(value).strip()
                                column_data[key]['values'].add(clean_value)
                                column_data[key]['non_empty_rows'] += 1
                                
                                # Keep sample values for inspection
                                if len(column_data[key]['sample_values']) < 10:
                                    column_data[key]['sample_values'].append(clean_value)
                
                logger.debug(f"     Processed {len(reader.fieldnames or [])} columns")
                
            except Exception as e:
                logger.error(f"Error processing file {csv_file}: {e}")
                continue
        
        return column_data
    
    def _find_value_intersections(self, column_data: Dict[Tuple[str, str], Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Find all value intersections between column pairs."""
        
        intersections = []
        column_keys = list(column_data.keys())
        
        total_comparisons = len(column_keys) * (len(column_keys) - 1) // 2
        logger.debug(f"   Performing {total_comparisons} column pair comparisons...")
        
        for i, col1_key in enumerate(column_keys):
            for j, col2_key in enumerate(column_keys):
                if i >= j:  # Skip self-comparison and duplicates
                    continue
                
                values1 = column_data[col1_key]['values']
                values2 = column_data[col2_key]['values']
                
                if len(values1) == 0 or len(values2) == 0:
                    continue
                
                # Calculate intersection
                shared_values = values1 & values2
                
                if len(shared_values) > 0:
                    # Calculate various similarity metrics
                    union_size = len(values1 | values2)
                    jaccard = len(shared_values) / union_size if union_size > 0 else 0
                    overlap_1 = len(shared_values) / len(values1)
                    overlap_2 = len(shared_values) / len(values2)
                    
                    intersections.append({
                        'file1': col1_key[0],
                        'column1': col1_key[1],
                        'file2': col2_key[0],
                        'column2': col2_key[1],
                        'shared_values': shared_values,
                        'shared_count': len(shared_values),
                        'total_values_1': len(values1),
                        'total_values_2': len(values2),
                        'jaccard_similarity': jaccard,
                        'overlap_ratio_1': overlap_1,
                        'overlap_ratio_2': overlap_2,
                        'rows_1': column_data[col1_key]['total_rows'],
                        'rows_2': column_data[col2_key]['total_rows'],
                        'sample_shared_values': list(shared_values)[:5]
                    })
        
        return sorted(intersections, key=lambda x: x['shared_count'], reverse=True)
    
    def _classify_relationship_patterns(self, intersections: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Classify relationship types based on value overlap patterns."""
        
        relationships = []
        
        for intersection in intersections:
            # Skip if same file and same column
            if (intersection['file1'] == intersection['file2'] and 
                intersection['column1'] == intersection['column2']):
                continue
            
            overlap1 = intersection['overlap_ratio_1']
            overlap2 = intersection['overlap_ratio_2']
            shared_count = intersection['shared_count']
            jaccard = intersection['jaccard_similarity']
            
            # Determine relationship type based on overlap patterns
            relationship_type = None
            direction = None
            confidence = 0
            description = ""
            
            # Pattern: Many-to-One (Foreign Key relationship)
            # Check if one column's values are mostly contained in another (foreign key pattern)
            total_values_1 = intersection['total_values_1']
            total_values_2 = intersection['total_values_2']
            
            # Foreign key: many values in col1 reference fewer unique values in col2
            if (overlap1 > 0.8 and total_values_1 >= total_values_2 and 
                shared_count >= 2 and total_values_2 >= 2):
                relationship_type = "many_to_one"
                direction = "1_to_2"  # file1.column1 references file2.column2
                confidence = overlap1 * min(shared_count / 5, 1.0)
                description = f"{intersection['file1']}.{intersection['column1']} likely references {intersection['file2']}.{intersection['column2']}"
                
            elif (overlap2 > 0.8 and total_values_2 >= total_values_1 and 
                  shared_count >= 2 and total_values_1 >= 2):
                relationship_type = "many_to_one"
                direction = "2_to_1"  # file2.column2 references file1.column1
                confidence = overlap2 * min(shared_count / 5, 1.0)
                description = f"{intersection['file2']}.{intersection['column2']} likely references {intersection['file1']}.{intersection['column1']}"
            
            # Pattern: One-to-One (Same entity or duplicate)
            elif overlap1 > 0.8 and overlap2 > 0.8 and jaccard > 0.7:
                relationship_type = "one_to_one"
                direction = "bidirectional"
                confidence = min(overlap1, overlap2) * jaccard
                description = f"{intersection['file1']}.{intersection['column1']} and {intersection['file2']}.{intersection['column2']} represent the same entity"
            
            # Pattern: Many-to-Many (Junction relationship)
            elif 0.3 < overlap1 < 0.8 and 0.3 < overlap2 < 0.8 and shared_count >= 5:
                relationship_type = "many_to_many"
                direction = "bidirectional"
                confidence = (overlap1 + overlap2) / 2 * min(shared_count / 20, 1.0)
                description = f"{intersection['file1']}.{intersection['column1']} and {intersection['file2']}.{intersection['column2']} have many-to-many relationship"
            
            # Pattern: Subset (one column is subset of another)
            elif overlap1 > 0.9 and overlap2 < 0.3 and shared_count >= 2:
                relationship_type = "subset"
                direction = "1_subset_of_2"
                confidence = overlap1
                description = f"{intersection['file1']}.{intersection['column1']} is a subset of {intersection['file2']}.{intersection['column2']}"
                
            elif overlap2 > 0.9 and overlap1 < 0.3 and shared_count >= 2:
                relationship_type = "subset"
                direction = "2_subset_of_1"
                confidence = overlap2
                description = f"{intersection['file2']}.{intersection['column2']} is a subset of {intersection['file1']}.{intersection['column1']}"
            
            # Pattern: Partial overlap (weak relationship)
            elif jaccard > 0.1 and shared_count >= 3:
                relationship_type = "partial_overlap"
                direction = "bidirectional"
                confidence = jaccard * min(shared_count / 10, 1.0)
                description = f"{intersection['file1']}.{intersection['column1']} and {intersection['file2']}.{intersection['column2']} have partial value overlap"
            
            if relationship_type and confidence > 0.05:  # Minimum confidence threshold
                relationships.append({
                    'type': relationship_type,
                    'direction': direction,
                    'file1': intersection['file1'],
                    'column1': intersection['column1'],
                    'file2': intersection['file2'],
                    'column2': intersection['column2'],
                    'confidence': confidence,
                    'shared_count': shared_count,
                    'description': description,
                    'sample_shared_values': intersection['sample_shared_values'],
                    'evidence': {
                        'overlap_ratio_1': overlap1,
                        'overlap_ratio_2': overlap2,
                        'jaccard_similarity': jaccard,
                        'total_values_1': intersection['total_values_1'],
                        'total_values_2': intersection['total_values_2']
                    }
                })
        
        return sorted(relationships, key=lambda x: x['confidence'], reverse=True)
    
    def _generate_summary(self, column_data: Dict, intersections: List, relationships: List) -> Dict[str, Any]:
        """Generate summary statistics of the analysis."""
        
        # File statistics
        files = set(key[0] for key in column_data.keys())
        
        # Column statistics
        total_columns = len(column_data)
        columns_with_data = sum(1 for data in column_data.values() if len(data['values']) > 0)
        
        # Relationship statistics
        relationship_types = defaultdict(int)
        for rel in relationships:
            relationship_types[rel['type']] += 1
        
        # High-confidence relationships
        high_confidence_rels = [rel for rel in relationships if rel['confidence'] > 0.5]
        
        return {
            'files_analyzed': len(files),
            'total_columns': total_columns,
            'columns_with_data': columns_with_data,
            'total_intersections': len(intersections),
            'total_relationships': len(relationships),
            'high_confidence_relationships': len(high_confidence_rels),
            'relationship_types': dict(relationship_types),
            'files': list(files)
        }
    
    def print_analysis_report(self, analysis: Dict[str, Any], top_n: int = 5):
        """Print a concise formatted analysis report."""
        
        summary = analysis['summary']
        relationships = analysis['relationships']
        
        print("\n" + "="*60)
        print("📊 CSV RELATIONSHIP ANALYSIS REPORT")
        print("="*60)
        
        print(f"\n📁 FILES: {summary['files_analyzed']} files analyzed")
        print(f"📋 SUMMARY: {summary['total_relationships']} relationships found")
        print(f"   • High-confidence: {summary['high_confidence_relationships']}")
        print(f"   • Total intersections: {summary['total_intersections']}")
        
        print(f"\n🔗 RELATIONSHIP TYPES:")
        for rel_type, count in summary['relationship_types'].items():
            print(f"   • {rel_type.replace('_', '-')}: {count}")
        
        # Show top foreign key relationships (most important)
        foreign_key_rels = [rel for rel in relationships if rel['type'] == 'many_to_one' and rel['confidence'] > 0.8]
        if foreign_key_rels:
            print(f"\n🔑 KEY FOREIGN KEY RELATIONSHIPS ({len(foreign_key_rels)} found):")
            for i, rel in enumerate(foreign_key_rels[:top_n], 1):
                print(f"   {i}. {rel['file1']}.{rel['column1']} → {rel['file2']}.{rel['column2']}")
                print(f"      Confidence: {rel['confidence']:.2f}, Shared: {rel['shared_count']} values")
        
        # Show potential duplicates
        duplicate_rels = [rel for rel in relationships if rel['type'] == 'one_to_one']
        if duplicate_rels:
            print(f"\n🔄 POTENTIAL DUPLICATES ({len(duplicate_rels)} found):")
            for i, rel in enumerate(duplicate_rels[:3], 1):
                print(f"   {i}. {rel['file1']}.{rel['column1']} ↔ {rel['file2']}.{rel['column2']}")
        
        # Show sample of other relationships
        other_rels = [rel for rel in relationships if rel['type'] not in ['many_to_one', 'one_to_one']]
        if other_rels:
            print(f"\n📊 OTHER RELATIONSHIPS (showing {min(3, len(other_rels))} of {len(other_rels)}):")
            for i, rel in enumerate(other_rels[:3], 1):
                print(f"   {i}. {rel['type']}: {rel['file1']}.{rel['column1']} ↔ {rel['file2']}.{rel['column2']}")
        
        print("\n" + "="*60)


def analyze_csv_relationships(csv_directory: str, delimiter: str = ';', print_report: bool = True) -> Dict[str, Any]:
    """
    Convenience function to analyze CSV relationships in a directory.
    
    Args:
        csv_directory: Path to directory containing CSV files
        delimiter: CSV delimiter (default: ';')
        print_report: Whether to print analysis report (default: True)
        
    Returns:
        Analysis results dictionary
    """
    analyzer = RelationshipAnalyzer(delimiter=delimiter)
    analysis = analyzer.analyze_directory(csv_directory)
    
    if print_report:
        analyzer.print_analysis_report(analysis)
    
    return analysis


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        directory = sys.argv[1]
        delimiter = sys.argv[2] if len(sys.argv) > 2 else ';'
        
        print(f"Analyzing CSV files in: {directory}")
        analysis = analyze_csv_relationships(directory, delimiter)
    else:
        print("Usage: python relationship_analyzer.py <csv_directory> [delimiter]")
        print("Example: python relationship_analyzer.py /path/to/csv/files ';'") 