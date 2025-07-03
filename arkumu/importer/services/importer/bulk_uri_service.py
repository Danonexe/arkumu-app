import logging
from typing import Optional, Dict, Any, List
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

logger = logging.getLogger(__name__)


class BulkURIService:
    """
    Centralized URI generation service for bulk import operations.
    
    Responsibilities:
    - Generate consistent URIs for all resource types
    - Parse and extract components from existing URIs
    - Handle multi-value indexing for unique URIs
    - Provide URI pattern validation
    """
    
    def __init__(self, base_uri: str, institution: str):
        """
        Initialize the URI service.
        
        Args:
            base_uri: Base URI for all generated resources
            institution: Institution code (will be slugified)
        """
        self.base_uri = base_uri
        self.institution = slugify_uri_part(str(institution)) if institution else "default"
    
    def generate_dataset_uri(self, dataset_name: str) -> str:
        """
        Generate URI for a dataset resource.
        
        Args:
            dataset_name: Name of the dataset
            
        Returns:
            Dataset URI string
        """
        return mint_uri(self.base_uri, self.institution, "datasets", dataset_name)
    
    def generate_column_uri(self, dataset_name: str, column_name: str) -> str:
        """
        Generate URI for a column resource.
        
        Args:
            dataset_name: Name of the dataset
            column_name: Name of the column
            
        Returns:
            Column URI string
        """
        safe_column_name = slugify_uri_part(column_name)
        return mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "columns", safe_column_name)
    
    def generate_row_uri(self, dataset_name: str, row_id: str) -> str:
        """
        Generate URI for a row resource.
        
        Args:
            dataset_name: Name of the dataset
            row_id: Identifier for the row (will be slugified)
            
        Returns:
            Row URI string
        """
        safe_row_id = slugify_uri_part(str(row_id))
        return mint_uri(self.base_uri, self.institution, "datasets", dataset_name, "rows", safe_row_id)
    
    def generate_cell_uri(self, dataset_name: str, column_name: str, row_id: str, 
                         value_index: Optional[int] = None) -> str:
        """
        Generate URI for a cell resource.
        
        Args:
            dataset_name: Name of the dataset
            column_name: Name of the column
            row_id: Identifier for the row
            value_index: Optional index for multi-value cells (creates unique URIs)
            
        Returns:
            Cell URI string
        """
        safe_column_name = slugify_uri_part(column_name)
        
        # Convert row_id to display format (1-based) if it's numeric
        if str(row_id).isdigit():
            display_row_id = int(row_id) + 1
        else:
            display_row_id = row_id
        safe_display_row_id = slugify_uri_part(str(display_row_id))
        
        # For multi-value columns, include value index to make URI unique
        if value_index is not None:
            return mint_uri(self.base_uri, self.institution, "datasets", dataset_name, 
                          safe_column_name, safe_display_row_id, f"v{value_index}")
        else:
            return mint_uri(self.base_uri, self.institution, "datasets", dataset_name, 
                          safe_column_name, safe_display_row_id)
    
    def generate_entity_uri(self, dataset_name: str, entity_value: str) -> str:
        """
        Generate URI for an entity resource (used in FK relationships).
        
        Args:
            dataset_name: Name of the dataset
            entity_value: Value that identifies the entity
            
        Returns:
            Entity URI string
        """
        safe_entity_value = slugify_uri_part(str(entity_value))
        return mint_uri(self.base_uri, self.institution, "entities", dataset_name, safe_entity_value)
    
    def generate_property_uri(self, property_name: str) -> str:
        """
        Generate URI for a property resource.
        
        Args:
            property_name: Name of the property
            
        Returns:
            Property URI string
        """
        safe_property_name = slugify_uri_part(property_name)
        return mint_uri(self.base_uri, self.institution, "properties", safe_property_name)
    
    def generate_junction_uri(self, dataset_name: str, context_column: str, junction_id: str) -> str:
        """
        Generate URI for a junction table resource (used in relationship contexts).
        
        Args:
            dataset_name: Name of the dataset
            context_column: Name of the context column
            junction_id: Unique identifier for the junction
            
        Returns:
            Junction URI string
        """
        safe_context_column = slugify_uri_part(context_column)
        safe_junction_id = slugify_uri_part(junction_id)
        return mint_uri(self.base_uri, self.institution, "junctions", dataset_name, 
                       safe_context_column, safe_junction_id)
    
    def extract_row_id_from_uri(self, cell_uri: str) -> Optional[str]:
        """
        Extract row_id from a standard cell URI.
        
        Args:
            cell_uri: Cell URI to parse
            
        Returns:
            Row ID string or None if parsing fails
        """
        # Standard URI: {base_uri}/{institution}/datasets/{dataset_name}/{column_name}/{row_id}
        try:
            return cell_uri.split('/')[-1]
        except IndexError:
            logger.warning(f"Could not parse row_id from cell_uri: {cell_uri}")
            return None
    
    def extract_column_name_from_uri(self, cell_uri: str) -> Optional[str]:
        """
        Extract column_name from a standard cell URI.
        
        Args:
            cell_uri: Cell URI to parse
            
        Returns:
            Column name string or None if parsing fails
        """
        # Standard URI: {base_uri}/{institution}/datasets/{dataset_name}/{column_name}/{row_id}
        try:
            parts = cell_uri.split('/')
            # Find the datasets part and get the column name after it
            if 'datasets' in parts:
                datasets_index = parts.index('datasets')
                if datasets_index + 2 < len(parts):
                    return parts[datasets_index + 2]  # datasets/{name}/{column_name}/{row_id}
            return None
        except (IndexError, ValueError):
            logger.warning(f"Could not parse column_name from cell_uri: {cell_uri}")
            return None
    
    def extract_dataset_name_from_uri(self, uri: str) -> Optional[str]:
        """
        Extract dataset_name from any dataset-related URI.
        
        Args:
            uri: URI to parse
            
        Returns:
            Dataset name string or None if parsing fails
        """
        try:
            parts = uri.split('/')
            if 'datasets' in parts:
                datasets_index = parts.index('datasets')
                if datasets_index + 1 < len(parts):
                    return parts[datasets_index + 1]  # datasets/{dataset_name}/...
            return None
        except (IndexError, ValueError):
            logger.warning(f"Could not parse dataset_name from uri: {uri}")
            return None
    
    def is_cell_uri(self, uri: str) -> bool:
        """
        Check if a URI represents a cell resource.
        
        Args:
            uri: URI to check
            
        Returns:
            True if the URI is a cell URI, False otherwise
        """
        try:
            parts = uri.split('/')
            # Cell URI pattern: .../datasets/{dataset_name}/{column_name}/{row_id}
            # Must NOT contain 'columns' or 'rows' keywords
            if 'datasets' in parts and 'columns' not in parts and 'rows' not in parts:
                datasets_index = parts.index('datasets')
                # Should have at least 3 parts after 'datasets': dataset_name, column_name, row_id
                return datasets_index + 3 < len(parts)
            return False
        except (IndexError, ValueError):
            return False
    
    def is_row_uri(self, uri: str) -> bool:
        """
        Check if a URI represents a row resource.
        
        Args:
            uri: URI to check
            
        Returns:
            True if the URI is a row URI, False otherwise
        """
        try:
            parts = uri.split('/')
            # Row URI pattern: .../datasets/{dataset_name}/rows/{row_id}
            if 'datasets' in parts and 'rows' in parts:
                datasets_index = parts.index('datasets')
                rows_index = parts.index('rows')
                return datasets_index < rows_index and rows_index + 1 < len(parts)
            return False
        except (IndexError, ValueError):
            return False
    
    def is_column_uri(self, uri: str) -> bool:
        """
        Check if a URI represents a column resource.
        
        Args:
            uri: URI to check
            
        Returns:
            True if the URI is a column URI, False otherwise
        """
        try:
            parts = uri.split('/')
            # Column URI pattern: .../datasets/{dataset_name}/columns/{column_name}
            if 'datasets' in parts and 'columns' in parts:
                datasets_index = parts.index('datasets')
                columns_index = parts.index('columns')
                return datasets_index < columns_index and columns_index + 1 < len(parts)
            return False
        except (IndexError, ValueError):
            return False
    
    def validate_uri_pattern(self, uri: str) -> Dict[str, Any]:
        """
        Validate and analyze a URI pattern.
        
        Args:
            uri: URI to validate
            
        Returns:
            Dictionary with validation results and extracted components
        """
        result = {
            "is_valid": False,
            "uri_type": None,
            "components": {},
            "errors": []
        }
        
        try:
            # Basic URI structure validation
            if not uri or not uri.startswith(('http://', 'https://')):
                result["errors"].append("URI must start with http:// or https://")
                return result
            
            parts = uri.split('/')
            if len(parts) < 4:  # Minimum: protocol, empty, host, path
                result["errors"].append("URI structure is too short")
                return result
            
            # Check for institution and base structure
            if self.institution not in parts:
                result["errors"].append(f"Institution '{self.institution}' not found in URI")
                return result
            
            # Determine URI type and extract components
            if self.is_cell_uri(uri):
                result["uri_type"] = "cell"
                result["components"]["dataset_name"] = self.extract_dataset_name_from_uri(uri)
                result["components"]["column_name"] = self.extract_column_name_from_uri(uri)
                result["components"]["row_id"] = self.extract_row_id_from_uri(uri)
                result["is_valid"] = True
            elif self.is_row_uri(uri):
                result["uri_type"] = "row"
                result["components"]["dataset_name"] = self.extract_dataset_name_from_uri(uri)
                result["is_valid"] = True
            elif self.is_column_uri(uri):
                result["uri_type"] = "column"
                result["components"]["dataset_name"] = self.extract_dataset_name_from_uri(uri)
                result["is_valid"] = True
            elif 'datasets' in parts:
                datasets_index = parts.index('datasets')
                if datasets_index + 1 < len(parts):
                    result["uri_type"] = "dataset"
                    result["components"]["dataset_name"] = parts[datasets_index + 1]
                    result["is_valid"] = True
            else:
                result["errors"].append("Unknown URI pattern")
            
        except Exception as e:
            result["errors"].append(f"URI parsing error: {str(e)}")
        
        return result
    
    def get_uri_hierarchy(self, uri: str) -> List[str]:
        """
        Get the URI hierarchy for a given URI (parent URIs).
        
        Args:
            uri: URI to analyze
            
        Returns:
            List of parent URIs from most general to most specific
        """
        hierarchy = []
        
        validation = self.validate_uri_pattern(uri)
        if not validation["is_valid"]:
            return hierarchy
        
        components = validation["components"]
        uri_type = validation["uri_type"]
        
        if "dataset_name" in components:
            dataset_name = components["dataset_name"]
            
            # Always include dataset URI
            hierarchy.append(self.generate_dataset_uri(dataset_name))
            
            if uri_type == "column" and "column_name" in components:
                # Column is direct child of dataset
                pass
            elif uri_type == "row" and "row_id" in components:
                # Row is direct child of dataset
                pass
            elif uri_type == "cell":
                # Cell can have both column and row parents
                if "column_name" in components:
                    hierarchy.append(self.generate_column_uri(dataset_name, components["column_name"]))
                if "row_id" in components:
                    hierarchy.append(self.generate_row_uri(dataset_name, components["row_id"]))
        
        return hierarchy