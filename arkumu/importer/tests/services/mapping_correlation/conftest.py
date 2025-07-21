"""
Fixtures for mapping correlation service tests.
"""
import pytest
import tempfile
import json
from pathlib import Path
from arkumu.metadata.models import Mapping
from arkumu.users.models import Organization


@pytest.fixture
def test_organization():
    """Create test organization for KHM."""
    org, created = Organization.objects.get_or_create(
        code="KHM",
        defaults={"name": "Kunsthochschule für Medien Köln", "country": "DE"}
    )
    yield org
    if created:
        org.delete()


@pytest.fixture
def khm_datasets():
    """KHM dataset names from the actual correlation error."""
    return [
        "00_Projekte",
        "01_Grundereignis", 
        "02_Kreuz_Projekte_Personen",
        "03_Personen_Akteurinnen",
        "04_Kreuz_Betreuende_Projekte",
        "05_PersonenBetreuende",
        "06_Auszeichnungen_Projekte",
        "07_Kreuz_Projekte_Keywords",
        "08_Keywords",
        "09_Kreuz_Projekte_Informationsträger",  # This one has the German ä character
        "10_PhysMedien_Informationstraeger",     # This one has the sanitized version
        "11_Kreuz_DigitaleObjekte_Proj",
        "12_Media_DigitaleObjekte",
        "16_Kreuz_Events_Projekte",
        "17_Events_weitereEreignisse",
        "18_Kreuz_Projekte_EquipmentSoftware",
        "19_Equipment_und_Software",
        "20_Equipmentart",
        "21_PhysischesObjekt"
    ]


@pytest.fixture 
def khm_mapping_config(khm_datasets):
    """Create mapping configuration for KHM datasets."""
    
    # Create workspace columns for each dataset
    workspace_columns = {}
    workspace_datasets = []
    
    for dataset_name in khm_datasets:
        # Add to workspace_datasets
        workspace_datasets.append(dataset_name)
        
        # Add columns for each dataset
        workspace_columns[f"{dataset_name}::id"] = {
            "dataset": dataset_name,
            "name": "id",
            "arkumu_type": "identifier",
            "anchor": True
        }
        workspace_columns[f"{dataset_name}::name"] = {
            "dataset": dataset_name, 
            "name": "name",
            "arkumu_type": "text"
        }
        workspace_columns[f"{dataset_name}::description"] = {
            "dataset": dataset_name,
            "name": "description", 
            "arkumu_type": "text"
        }
    
    # Create FK relationships involving the problematic dataset
    fk_relationships = {
        "proj_to_info": {
            "source_dataset": "00_Projekte",
            "source_column": "info_id", 
            "target_dataset": "09_Kreuz_Projekte_Informationsträger",  # German character dataset
            "target_column": "id"
        },
        "info_to_phys": {
            "source_dataset": "09_Kreuz_Projekte_Informationsträger",
            "source_column": "phys_id",
            "target_dataset": "10_PhysMedien_Informationstraeger", 
            "target_column": "id"
        }
    }
    
    return {
        "id": "khm_mapping_test",
        "name": "KHM Test Mapping",
        "organization_id": "KHM",
        "workspace_datasets": workspace_datasets,
        "workspace_columns": workspace_columns,
        "fk_relationships": fk_relationships
    }


@pytest.fixture
def khm_mapping_from_config(khm_mapping_config, test_organization):
    """Create a Mapping model instance from the KHM mapping config."""
    mapping = Mapping.objects.create(
        name=khm_mapping_config["name"],
        organization=test_organization,
        mapping_json=khm_mapping_config
    )
    yield mapping
    mapping.delete()


@pytest.fixture
def khm_csv_files_from_s3(bucket_service):
    """Load real KHM CSV files from S3 bucket."""
    
    # Use the actual KHM organization bucket
    bucket_name = 'khm'  # KHM organization bucket
    
    try:
        # List all CSV files in the metadata directory
        files = bucket_service.list_bucket_contents(bucket_name, prefix='metadata/')
        csv_files = [f for f in files if f['type'] == 'file' and f['name'].endswith('.csv')]
        
        # Convert to file paths that correlation service expects
        file_paths = []
        for csv_file in csv_files:
            # Remove the metadata/ prefix to get just the filename
            file_key = csv_file['name']
            if file_key.startswith('metadata/'):
                file_key = file_key[9:]  # Remove 'metadata/' prefix
            file_paths.append(f"metadata/{file_key}")
        
        return file_paths
        
    except Exception as e:
        # Fallback: create expected file paths based on dataset names
        expected_files = [
            "metadata/00_Projekte.csv",
            "metadata/01_Grundereignis.csv", 
            "metadata/02_Kreuz_Projekte_Personen.csv",
            "metadata/03_Personen_Akteurinnen.csv",
            "metadata/04_Kreuz_Betreuende_Projekte.csv",
            "metadata/05_PersonenBetreuende.csv",
            "metadata/06_Auszeichnungen_Projekte.csv",
            "metadata/07_Kreuz_Projekte_Keywords.csv",
            "metadata/08_Keywords.csv",
            "metadata/09_Kreuz_Projekte_Informationsträger.csv",  # The problematic one with German chars
            "metadata/10_PhysMedien_Informationstraeger.csv",
            "metadata/11_Kreuz_DigitaleObjekte_Proj.csv",
            "metadata/12_Media_DigitaleObjekte.csv",
            "metadata/16_Kreuz_Events_Projekte.csv",
            "metadata/17_Events_weitereEreignisse.csv",
            "metadata/18_Kreuz_Projekte_EquipmentSoftware.csv",
            "metadata/19_Equipment_und_Software.csv",
            "metadata/20_Equipmentart.csv",
            "metadata/21_PhysischesObjekt.csv"
        ]
        
        print(f"Warning: Could not access S3 bucket {bucket_name}: {e}")
        print(f"Using fallback file list with {len(expected_files)} files")
        return expected_files


@pytest.fixture 
def bucket_service():
    """Create bucket service for S3 access."""
    from arkumu.storage.services.bucket_service import BucketService
    return BucketService()