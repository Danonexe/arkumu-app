import os
import json
import logging
from typing import Dict, List, Optional, Any

from arkumu.importer.services.draft_mapping.draft_mapping import generate_relationship_config

logger = logging.getLogger(__name__)

class RelationshipConfigService:
    """
    Service for managing relationship configurations between CSV tables.
    """
    
    @staticmethod
    def analyze_csv_directory(
        directory_path: str,
        output_path: Optional[str] = None,
        delimiter: str = ';',
        has_quoted_fields: bool = False
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Analyze all CSV files in a directory and generate a relationship configuration.
        
        Args:r
            directory_path: Path to directory containing CSV files
            output_path: Optional path to save the JSON configuration
            delimiter: CSV column delimiter
            has_quoted_fields: Whether fields in the CSV are quoted
            
        Returns:
            Dict mapping table names to FK column configurations
        """
        if not os.path.isdir(directory_path):
            logger.error(f"Directory not found: {directory_path}")
            return {}
            
        csv_files = [os.path.join(directory_path, f) for f in os.listdir(directory_path) if f.endswith('.csv')]
        
        if not csv_files:
            logger.warning(f"No CSV files found in {directory_path}")
            return {}
            
        logger.info(f"Analyzing {len(csv_files)} CSV files in {directory_path}")
        
        return generate_relationship_config(
            csv_files,
            output_path=output_path,
            delimiter=delimiter,
            has_quoted_fields=has_quoted_fields
        )
    
    @staticmethod
    def save_relationship_config(
        config: Dict[str, List[Dict[str, str]]],
        output_path: str
    ) -> bool:
        """
        Save relationship configuration to a JSON file.
        
        Args:
            config: Relationship configuration dict
            output_path: Path to save the JSON file
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with open(output_path, 'w') as f:
                json.dump(config, f, indent=2)
            logger.info(f"Relationship configuration saved to {output_path}")
            return True
        except Exception as e:
            logger.error(f"Error saving relationship configuration: {e}")
            return False
    
    @staticmethod
    def load_relationship_config(
        config_path: str
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Load relationship configuration from a JSON file.
        
        Args:
            config_path: Path to the JSON configuration file
            
        Returns:
            Loaded configuration dict or empty dict if file not found or invalid
        """
        if not os.path.exists(config_path):
            logger.error(f"Configuration file not found: {config_path}")
            return {}
            
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded relationship configuration from {config_path}")
            return config
        except Exception as e:
            logger.error(f"Error loading relationship configuration: {e}")
            return {}
    
    @staticmethod
    def update_relationship_config(
        config: Dict[str, List[Dict[str, str]]],
        table_name: str,
        fk_columns: List[Dict[str, str]]
    ) -> Dict[str, List[Dict[str, str]]]:
        """
        Update a relationship configuration with new or modified FK columns.
        
        Args:
            config: Existing relationship configuration
            table_name: Name of the table to update
            fk_columns: List of FK column configurations
            
        Returns:
            Updated configuration dict
        """
        config[table_name] = fk_columns
        return config
    
    @staticmethod
    def get_table_relationships(
        config: Dict[str, List[Dict[str, str]]],
        table_name: str
    ) -> List[Dict[str, str]]:
        """
        Get the FK relationships for a specific table.
        
        Args:
            config: Relationship configuration
            table_name: Name of the table to query
            
        Returns:
            List of FK column configurations or empty list if table not found
        """
        return config.get(table_name, []) 