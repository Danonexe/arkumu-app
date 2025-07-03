"""
Test Script for Chunked Processing

This script tests the new chunked processing functionality with sample data.
"""

import os
import csv
import tempfile
import logging
from typing import Dict, Any
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def create_test_csv(file_path: str, num_rows: int = 50000) -> str:
    """Create a test CSV file with specified number of rows"""
    
    logger.info(f"Creating test CSV with {num_rows} rows at {file_path}")
    
    headers = [
        'id', 'name', 'department', 'skills', 'manager_id', 
        'email', 'start_date', 'salary', 'location', 'projects'
    ]
    
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        
        for i in range(1, num_rows + 1):
            row = [
                f"E{i:06d}",  # id
                f"Employee {i}",  # name
                f"Dept_{i % 10}",  # department (10 departments)
                f"Python,SQL,Data Analysis" if i % 3 == 0 else "Excel,PowerBI",  # multi-value skills
                f"M{(i-1)//10 + 1:04d}",  # manager_id (FK relationship)
                f"employee{i}@company.com",  # email
                f"2024-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}",  # start_date
                f"{30000 + (i % 50000)}",  # salary
                f"Office_{i % 5}",  # location
                f"Proj_{i % 20},Proj_{(i+1) % 20}" if i % 4 == 0 else f"Proj_{i % 20}"  # multi-value projects
            ]
            writer.writerow(row)
    
    # Check file size
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    logger.info(f"Created test CSV: {file_size_mb:.1f}MB")
    
    return file_path


def test_chunked_processing_with_file():
    """Test chunked processing with a large CSV file"""
    
    logger.info("=== Testing Chunked Processing with File ===")
    
    try:
        from .chunked_processor import process_large_dataset_chunked
        from ..orchestrator import ImportOrchestrator
        from ..mapping_consumer import ExecutionConfig, DatasetConfig, ColumnConfig, ColumnType
        
        # Create test CSV file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            test_csv_path = f.name
        
        create_test_csv(test_csv_path, num_rows=30000)  # ~5-10MB file
        
        try:
            # Create mock execution config
            execution_config = ExecutionConfig(
                mapping_id=999,
                mapping_name="Test Chunked Processing",
                datasets=[
                    DatasetConfig(
                        dataset_name="employees",
                        columns=[
                            ColumnConfig(
                                column_name="id",
                                arkumu_type="employee_id",
                                column_type=ColumnType.ANCHOR,
                                is_anchor=True,
                                is_multi_value=False
                            ),
                            ColumnConfig(
                                column_name="name",
                                arkumu_type="full_name",
                                column_type=ColumnType.REGULAR,
                                is_multi_value=False
                            ),
                            ColumnConfig(
                                column_name="skills",
                                arkumu_type="skill",
                                column_type=ColumnType.REGULAR,
                                is_multi_value=True,
                                multi_value_separator=","
                            ),
                            ColumnConfig(
                                column_name="manager_id",
                                arkumu_type="manager",
                                column_type=ColumnType.FOREIGN_KEY,
                                is_multi_value=False
                            ),
                            ColumnConfig(
                                column_name="projects",
                                arkumu_type="project",
                                column_type=ColumnType.REGULAR,
                                is_multi_value=True,
                                multi_value_separator=","
                            )
                        ],
                        dependencies=[]
                    )
                ],
                column_configurations={},
                fk_relationships=[],
                external_ontologies=[],
                processing_phases=[]
            )
            
            # Test with Import Orchestrator
            orchestrator = ImportOrchestrator(
                institution="TEST_INSTITUTION",
                base_uri="http://test.arkumu.org",
                enable_progress_tracking=True
            )
            
            csv_sources = {"employees": test_csv_path}
            
            # Test streaming entity-centric with chunking
            logger.info("Testing streaming entity-centric processing...")
            result = orchestrator._execute_streaming_entity_centric(
                execution_config=execution_config,
                csv_sources=csv_sources,
                result=type('MockResult', (), {
                    'success': True,
                    'errors': [],
                    'warnings': [],
                    'total_resources_created': 0,
                    'total_triples_created': 0,
                    'total_rows_processed': 0,
                    'total_cells_processed': 0,
                    'datasets_processed': 0,
                    'phase_results': [],
                    'peak_memory_usage_mb': None,
                    'add_error': lambda self, msg: self.errors.append(msg),
                    'add_warning': lambda self, msg: self.warnings.append(msg)
                })(),
                chunk_size=5000,  # Small chunks for testing
                max_memory_mb=100
            )
            
            logger.info("=== Chunked Processing Test Results ===")
            logger.info(f"Resources created: {result.total_resources_created}")
            logger.info(f"Triples created: {result.total_triples_created}")
            logger.info(f"Rows processed: {result.total_rows_processed}")
            logger.info(f"Peak memory: {result.peak_memory_usage_mb}MB")
            logger.info(f"Errors: {len(result.errors)}")
            logger.info(f"Warnings: {len(result.warnings)}")
            
            if result.phase_results:
                phase_result = result.phase_results[0]
                logger.info(f"Chunks processed: {phase_result.get('chunks_processed', 'N/A')}")
                logger.info(f"Processing rate: {phase_result.get('processing_rate_rows_per_second', 'N/A')} rows/sec")
            
            return True
            
        finally:
            # Clean up test file
            if os.path.exists(test_csv_path):
                os.unlink(test_csv_path)
                logger.info(f"Cleaned up test file: {test_csv_path}")
    
    except Exception as e:
        logger.error(f"Chunked processing test failed: {e}", exc_info=True)
        return False


def test_chunked_processing_with_memory_data():
    """Test chunked processing with in-memory data"""
    
    logger.info("=== Testing Chunked Processing with Memory Data ===")
    
    try:
        from .chunked_processor import ChunkedProcessor, StreamingConfig
        from ..mapping_consumer import ExecutionConfig, DatasetConfig, ColumnConfig, ColumnType
        
        # Create test data in memory
        test_data = []
        for i in range(1, 25001):  # 25K rows
            test_data.append({
                'id': f"R{i:06d}",
                'title': f"Research Project {i}",
                'keywords': f"AI,ML,research" if i % 3 == 0 else "data,analysis",
                'lead_researcher_id': f"L{(i-1)//100 + 1:04d}",
                'collaborators': f"C{i % 50},C{(i+1) % 50}" if i % 4 == 0 else f"C{i % 50}",
                'budget': str(50000 + (i % 100000)),
                'status': 'active' if i % 3 != 0 else 'completed'
            })
        
        logger.info(f"Created test data with {len(test_data)} rows")
        
        # Configure streaming
        streaming_config = StreamingConfig(
            chunk_size=3000,  # Small chunks for testing
            max_memory_mb=50,
            enable_gc=True,
            persist_chunks=True
        )
        
        # Initialize chunked processor
        processor = ChunkedProcessor(
            institution="TEST_INSTITUTION",
            base_uri="http://test.arkumu.org",
            streaming_config=streaming_config
        )
        
        # Create execution config
        execution_config = ExecutionConfig(
            mapping_id=998,
            mapping_name="Test Memory Chunked Processing",
            datasets=[
                DatasetConfig(
                    dataset_name="research_projects",
                    columns=[
                        ColumnConfig(
                            column_name="id",
                            arkumu_type="project_id",
                            column_type=ColumnType.ANCHOR,
                            is_anchor=True,
                            is_multi_value=False
                        ),
                        ColumnConfig(
                            column_name="keywords",
                            arkumu_type="keyword",
                            column_type=ColumnType.REGULAR,
                            is_multi_value=True,
                            multi_value_separator=","
                        ),
                        ColumnConfig(
                            column_name="collaborators",
                            arkumu_type="collaborator",
                            column_type=ColumnType.REGULAR,
                            is_multi_value=True,
                            multi_value_separator=","
                        )
                    ],
                    dependencies=[]
                )
            ],
            column_configurations={},
            fk_relationships=[],
            external_ontologies=[],
            processing_phases=[]
        )
        
        # Process with chunked processor
        csv_sources = {"research_projects": test_data}
        metrics = processor.process_large_csv_sources(execution_config, csv_sources)
        
        # Get summary
        summary = processor.get_processing_summary()
        
        logger.info("=== Memory Chunked Processing Results ===")
        logger.info(f"Chunks processed: {summary['chunks_processed']}")
        logger.info(f"Total rows processed: {summary['total_rows_processed']}")
        logger.info(f"Total resources created: {summary['total_resources_created']}")
        logger.info(f"Total triples created: {summary['total_triples_created']}")
        logger.info(f"Average memory usage: {summary['average_memory_usage_mb']:.1f}MB")
        logger.info(f"Processing rate: {summary['rows_per_second']:.1f} rows/sec")
        
        # Show chunk details
        for chunk_detail in summary['chunk_details'][:3]:  # First 3 chunks
            logger.info(f"Chunk {chunk_detail['chunk']}: {chunk_detail['rows']} rows, "
                       f"{chunk_detail['resources']} resources, "
                       f"{chunk_detail['memory_mb']:.1f}MB, "
                       f"{chunk_detail['time_seconds']:.2f}s")
        
        return True
        
    except Exception as e:
        logger.error(f"Memory chunked processing test failed: {e}", exc_info=True)
        return False


def main():
    """Run all chunked processing tests"""
    
    logger.info("Starting Chunked Processing Tests")
    
    tests_passed = 0
    total_tests = 2
    
    # Test 1: File-based chunked processing
    if test_chunked_processing_with_file():
        tests_passed += 1
        logger.info("✅ File-based chunked processing test PASSED")
    else:
        logger.error("❌ File-based chunked processing test FAILED")
    
    # Test 2: Memory-based chunked processing
    if test_chunked_processing_with_memory_data():
        tests_passed += 1
        logger.info("✅ Memory-based chunked processing test PASSED")
    else:
        logger.error("❌ Memory-based chunked processing test FAILED")
    
    # Summary
    logger.info(f"=== Test Summary ===")
    logger.info(f"Tests passed: {tests_passed}/{total_tests}")
    
    if tests_passed == total_tests:
        logger.info("🎉 All chunked processing tests PASSED!")
        return True
    else:
        logger.error(f"😞 {total_tests - tests_passed} tests FAILED")
        return False


if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)