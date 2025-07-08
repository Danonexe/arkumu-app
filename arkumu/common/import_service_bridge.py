"""
Import Service Bridge

Provides a compatibility layer between the legacy ImportWorkflowService and the new orchestrator/execution layers.
This allows gradual migration while maintaining existing interfaces.
"""

import logging
from typing import Dict, Any, Optional, List
from django.contrib.auth.models import User

from arkumu.importer.services.orchestrator.import_orchestrator import ImportOrchestrator
# Removed: from arkumu.importer.services.importer.import_workflow import ImportWorkflowService
# Using orchestrator only now
from arkumu.users.models import Organization
from arkumu.metadata.models import Mapping

logger = logging.getLogger(__name__)


class ImportServiceBridge:
    """
    Bridge service that provides backward compatibility for ImportWorkflowService
    while delegating to the new orchestrator/execution layers where possible.
    """
    
    def __init__(self):
        self.orchestrator = ImportOrchestrator()
        # Legacy service removed - using orchestrator only
    
    def import_csv(
        self,
        file_path: str,
        organization: Organization,
        user: User,
        update_strategy: str = "skip_existing",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Import a single CSV file using the new orchestrator if mapping is available,
        otherwise fallback to legacy service.
        """
        try:
            # Try to find a mapping for this organization
            mapping = self._find_suitable_mapping(organization, file_path)
            
            if mapping:
                logger.info(f"Using orchestrator for CSV import with mapping {mapping.id}")
                result = self.orchestrator.execute_mapping(
                    mapping_id=mapping.id,
                    file_path=file_path,
                    user=user,
                    update_strategy=update_strategy,
                    **kwargs
                )
                return self._convert_orchestrator_result(result)
            else:
                # Use orchestrator with automatic mapping detection
                logger.info("No suitable mapping found, using orchestrator with automatic detection")
                result = self.orchestrator.execute_auto_mapping(
                    file_path=file_path,
                    organization=organization,
                    user=user,
                    update_strategy=update_strategy,
                    **kwargs
                )
                return self._convert_orchestrator_result(result)
        except Exception as e:
            logger.error(f"Error in import_csv bridge: {e}")
            # Return error result instead of falling back to legacy service
            return {
                "success": False,
                "error": str(e),
                "organization": organization.code if organization else "unknown",
                "file_path": file_path
            }
    
    def import_csv_directory(
        self,
        directory_path: str,
        organization: Organization,
        user: User,
        update_strategy: str = "skip_existing",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Import a directory of CSV files using the new orchestrator where mappings exist,
        otherwise fallback to legacy service.
        """
        try:
            # Use orchestrator for directory imports
            logger.info("Directory import using orchestrator")
            result = self.orchestrator.execute_directory_import(
                directory_path=directory_path,
                organization=organization,
                user=user,
                update_strategy=update_strategy,
                **kwargs
            )
            return self._convert_orchestrator_result(result)
        except Exception as e:
            logger.error(f"Error in import_csv_directory bridge: {e}")
            return {
                "success": False,
                "error": str(e),
                "organization": organization.code if organization else "unknown",
                "directory_path": directory_path
            }
    
    def import_csv_with_table_services(
        self,
        file_path: str,
        organization: Organization,
        user: User,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Import CSV with table services - this is already a modern approach,
        so we prefer the orchestrator if mapping exists.
        """
        try:
            mapping = self._find_suitable_mapping(organization, file_path)
            
            if mapping:
                logger.info(f"Using orchestrator for table-based CSV import with mapping {mapping.id}")
                result = self.orchestrator.execute_mapping(
                    mapping_id=mapping.id,
                    file_path=file_path,
                    user=user,
                    **kwargs
                )
                return self._convert_orchestrator_result(result)
            else:
                logger.info("No suitable mapping found, using orchestrator with table services mode")
                result = self.orchestrator.execute_table_based_import(
                    file_path=file_path,
                    organization=organization,
                    user=user,
                    **kwargs
                )
                return self._convert_orchestrator_result(result)
        except Exception as e:
            logger.error(f"Error in import_csv_with_table_services bridge: {e}")
            return {
                "success": False,
                "error": str(e),
                "organization": organization.code if organization else "unknown",
                "file_path": file_path
            }
    
    def _find_suitable_mapping(self, organization: Organization, file_path: str) -> Optional[Mapping]:
        """
        Find a suitable mapping for the given organization and file.
        This is a simplified version - in production this would be more sophisticated.
        """
        try:
            # Look for active mappings in the organization
            # For now, just return the first active mapping
            # This could be enhanced to match by filename patterns, etc.
            return Mapping.objects.filter(
                organization_id=organization.code,
                validation_status='validated'
            ).first()
        except Exception as e:
            logger.error(f"Error finding suitable mapping: {e}")
            return None
    
    def _convert_orchestrator_result(self, orchestrator_result) -> Dict[str, Any]:
        """
        Convert orchestrator result to legacy format for backward compatibility.
        """
        if not orchestrator_result:
            return {"success": False, "error": "No result from orchestrator"}
        
        return {
            "success": orchestrator_result.success,
            "mapping_id": orchestrator_result.mapping_id,
            "mapping_name": orchestrator_result.mapping_name,
            "organization": orchestrator_result.organization,
            "strategy_used": orchestrator_result.strategy_used,
            "execution_time_seconds": orchestrator_result.execution_time_seconds,
            "resources_created": orchestrator_result.total_resources_created,
            "triples_created": orchestrator_result.total_triples_created,
            "rows_processed": orchestrator_result.total_rows_processed,
            "cells_processed": orchestrator_result.total_cells_processed,
            "errors": orchestrator_result.errors,
            "datasets_processed": orchestrator_result.datasets_processed,
            "phase_results": orchestrator_result.phase_results
        }


# Global instance for easy access
bridge_service = ImportServiceBridge()