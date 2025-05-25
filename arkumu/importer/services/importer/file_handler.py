import os
import csv
import logging
from typing import Dict, List, Any

from arkumu.metadata.models.resource import Resource, ResourceType
from arkumu.metadata.utils.rdf_helpers import add_semantic_triple

logger = logging.getLogger(__name__)

class FileHandler:
    """
    Handles file uploads and file path processing for the import workflow.
    """
    
    @staticmethod
    def handle_file_uploads(
        file_path: str,
        dataset_name: str,
        institution: str,
        base_uri: str,
        delimiter: str,
        has_quoted_fields: bool,
        file_columns: List[str],
        files_base_directory: str,
        upload_service,
        uploaded_files: Dict[str, str],
        stats: Dict[str, Any]
    ):
        """
        Handle file uploads for specified file columns.
        
        Args:
            file_path: Path to the CSV file
            dataset_name: Name of the dataset
            institution: Institution code
            base_uri: Base URI for resources
            delimiter: CSV delimiter
            has_quoted_fields: Whether CSV fields are quoted
            file_columns: List of column names containing file paths
            files_base_directory: Base directory for resolving file paths
            upload_service: Service for uploading files
            uploaded_files: Dict tracking already uploaded files
            stats: Statistics dictionary to update
        """
        # Add file upload stats if not present
        if "files_uploaded" not in stats:
            stats["files_uploaded"] = 0
        if "upload_errors" not in stats:
            stats["upload_errors"] = 0
        
        try:
            # Get dataset resource
            dataset_uri = f"{base_uri}/datasets/{dataset_name}"
            dataset = Resource.objects.get(uri=dataset_uri)
            
            # Read CSV to get file paths
            with open(file_path, newline='', encoding='utf-8') as f:
                quoting = csv.QUOTE_ALL if has_quoted_fields else csv.QUOTE_MINIMAL
                reader = csv.DictReader(f, delimiter=delimiter, quoting=quoting)
                
                # Process each row
                for row_num, row in enumerate(reader):
                    # Process each file column
                    for col_name in file_columns:
                        if col_name not in row:
                            continue
                            
                        file_path_value = row.get(col_name)
                        if not file_path_value or file_path_value.strip() == '':
                            continue
                            
                        # Find the cell resource for this value
                        cell_uri = f"{dataset_uri}/{col_name}/{row.get('id', str(row_num))}"
                        try:
                            cell = Resource.objects.get(uri=cell_uri)
                            
                            # Resolve and upload the file
                            full_file_path = FileHandler.resolve_file_path(
                                files_base_directory,
                                file_path_value
                            )
                            
                            # Check if already uploaded
                            if full_file_path in uploaded_files:
                                file_url = uploaded_files[full_file_path]
                                logger.debug(f"📎 Using cached upload: {file_path_value} -> {file_url}")
                            else:
                                # Upload the file
                                logger.debug(f"📤 Uploading file: {full_file_path}")
                                success, result = upload_service.upload_file(full_file_path)
                                
                                if success:
                                    file_url = result
                                    uploaded_files[full_file_path] = file_url
                                    stats["files_uploaded"] += 1
                                    logger.info(f"✅ Uploaded: {file_path_value} -> {file_url}")
                                else:
                                    logger.error(f"❌ Upload failed: {file_path_value} - {result}")
                                    stats["upload_errors"] += 1
                                    continue
                            
                            # Add file URL as a property of the cell
                            has_file_url = Resource.objects.get_or_create(
                                uri="http://purl.org/dc/terms/hasFormat",
                                defaults={
                                    "resource_type": ResourceType.PROPERTY,
                                    "name": "hasFormat",
                                    "source": institution
                                }
                            )[0]
                            
                            # Add the triple
                            add_semantic_triple(
                                subject_uri=cell_uri,
                                predicate_uri="http://purl.org/dc/terms/hasFormat",
                                object_uri_or_value=file_url,
                                source=institution
                            )
                            stats["triples_created"] += 1
                            
                            logger.debug(f"🔗 Linked file URL: {cell_uri} -> {file_url}")
                            
                        except Resource.DoesNotExist:
                            logger.error(f"❌ Cell resource not found: {cell_uri}")
                            continue
                            
        except Exception as e:
            logger.error(f"❌ Error processing file columns: {e}")
            stats["errors"] += 1
    
    @staticmethod
    def resolve_file_path(base_directory: str, relative_path: str) -> str:
        """
        Resolve a relative file path against a base directory.
        
        Args:
            base_directory: Base directory
            relative_path: Relative path from the CSV
            
        Returns:
            Absolute path to the file
        """
        # Handle different path formats
        clean_path = relative_path.strip().replace('\\', '/').lstrip('/')
        
        # Try different combinations to find the file
        candidates = [
            os.path.join(base_directory, clean_path),
            os.path.join(base_directory, 'files', clean_path),
            os.path.join(base_directory, '..', 'files', clean_path),
            os.path.join(base_directory, 'data', clean_path),
            os.path.join(base_directory, '..', 'data', clean_path)
        ]
        
        for path in candidates:
            if os.path.exists(path):
                logger.debug(f"📁 Resolved file path: {relative_path} -> {path}")
                return path
        
        # If file not found, return the first candidate and log warning
        logger.warning(f"⚠️ File not found: {relative_path} (tried {len(candidates)} locations)")
        return candidates[0]
    
    @staticmethod
    def analyze_file_columns(csv_path: str, delimiter: str = ';') -> Dict[str, Any]:
        """
        Analyze a CSV file to identify potential file path columns.
        
        Args:
            csv_path: Path to the CSV file
            delimiter: CSV delimiter
            
        Returns:
            Dict with analysis results
        """
        try:
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                
                # Sample first few rows
                sample_rows = []
                for i, row in enumerate(reader):
                    if i >= 10:  # Sample first 10 rows
                        break
                    sample_rows.append(row)
                
                if not sample_rows:
                    return {"error": "No data rows found"}
                
                # Analyze each column for file path patterns
                column_analysis = {}
                for column_name in sample_rows[0].keys():
                    file_path_count = 0
                    total_non_empty = 0
                    sample_values = []
                    
                    for row in sample_rows:
                        value = row.get(column_name, '')
                        if value and value.strip():
                            total_non_empty += 1
                            sample_values.append(value)
                            
                            # Check if value looks like a file path
                            if FileHandler._looks_like_file_path(value):
                                file_path_count += 1
                    
                    if total_non_empty > 0:
                        file_path_percentage = (file_path_count / total_non_empty) * 100
                        
                        column_analysis[column_name] = {
                            "is_likely_file_column": file_path_percentage > 50,
                            "file_path_percentage": file_path_percentage,
                            "sample_values": sample_values[:3],
                            "total_values": total_non_empty
                        }
                
                return {
                    "total_columns": len(sample_rows[0].keys()) if sample_rows else 0,
                    "rows_analyzed": len(sample_rows),
                    "column_analysis": column_analysis,
                    "likely_file_columns": [
                        col for col, analysis in column_analysis.items() 
                        if analysis["is_likely_file_column"]
                    ]
                }
                
        except Exception as e:
            logger.error(f"Error analyzing file columns in {csv_path}: {e}")
            return {"error": str(e)}
    
    @staticmethod
    def _looks_like_file_path(value: str) -> bool:
        """
        Check if a value looks like a file path.
        
        Args:
            value: Value to check
            
        Returns:
            bool: True if value looks like a file path
        """
        value = value.strip()
        
        # Common file extensions
        file_extensions = [
            '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.svg',  # Images
            '.pdf', '.doc', '.docx', '.txt', '.rtf',  # Documents
            '.mp4', '.avi', '.mov', '.wmv', '.flv',  # Videos
            '.mp3', '.wav', '.flac', '.aac',  # Audio
            '.zip', '.rar', '.7z', '.tar', '.gz',  # Archives
            '.xml', '.json', '.csv', '.xlsx', '.xls'  # Data files
        ]
        
        # Check for file extensions
        value_lower = value.lower()
        for ext in file_extensions:
            if value_lower.endswith(ext):
                return True
        
        # Check for path-like patterns
        if '/' in value or '\\' in value:
            return True
        
        # Check for common file path keywords
        path_keywords = ['image', 'photo', 'document', 'file', 'media', 'attachment']
        for keyword in path_keywords:
            if keyword in value_lower:
                return True
        
        return False
    
    @staticmethod
    def validate_files_exist(
        csv_path: str, 
        file_columns: List[str], 
        files_base_directory: str,
        delimiter: str = ';'
    ) -> Dict[str, Any]:
        """
        Validate that files referenced in CSV actually exist.
        
        Args:
            csv_path: Path to the CSV file
            file_columns: List of file column names
            files_base_directory: Base directory for file resolution
            delimiter: CSV delimiter
            
        Returns:
            Dict with validation results
        """
        try:
            missing_files = []
            found_files = []
            total_file_references = 0
            
            with open(csv_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                
                for row_num, row in enumerate(reader):
                    for col_name in file_columns:
                        if col_name in row:
                            file_path_value = row.get(col_name)
                            if file_path_value and file_path_value.strip():
                                total_file_references += 1
                                
                                resolved_path = FileHandler.resolve_file_path(
                                    files_base_directory, 
                                    file_path_value
                                )
                                
                                if os.path.exists(resolved_path):
                                    found_files.append({
                                        "csv_path": file_path_value,
                                        "resolved_path": resolved_path,
                                        "row": row_num + 1,
                                        "column": col_name
                                    })
                                else:
                                    missing_files.append({
                                        "csv_path": file_path_value,
                                        "resolved_path": resolved_path,
                                        "row": row_num + 1,
                                        "column": col_name
                                    })
            
            return {
                "total_file_references": total_file_references,
                "found_files": len(found_files),
                "missing_files": len(missing_files),
                "missing_file_details": missing_files[:20],  # Limit to first 20
                "success_rate": (len(found_files) / total_file_references * 100) if total_file_references > 0 else 0
            }
            
        except Exception as e:
            logger.error(f"Error validating files for {csv_path}: {e}")
            return {"error": str(e)} 