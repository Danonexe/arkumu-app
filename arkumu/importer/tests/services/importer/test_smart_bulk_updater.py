import pytest
from typing import List, Dict, Any
from arkumu.metadata.models import Resource, Triple
from arkumu.metadata.models.resource import ResourceType
from arkumu.importer.services.importer.smart_bulk_updater import SmartBulkUpdater, UpdateStrategy, BulkUpdateStats
from arkumu.importer.services.importer.uri_utils import mint_uri, slugify_uri_part

# Standard vocabulary URIs that will be used/checked
HAS_PART_URI = "http://purl.org/dc/terms/hasPart"
RDF_VALUE_URI = "http://www.w3.org/1999/02/22-rdf-syntax-ns#value"
DCTERMS_RELATION_URI = "http://purl.org/dc/terms/relation"

BASE_URI = "http://test.arkumu.org/data"
INSTITUTION = "TEST_INST"
NUM_FIXTURE_RESOURCES = 3 # For HAS_PART, RDF_VALUE, DCTERMS_RELATION properties

@pytest.fixture
def initial_data_empty(db):
    Resource.objects.all().delete()
    Triple.objects.all().delete()
    Resource.objects.get_or_create(uri=HAS_PART_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "hasPart", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=RDF_VALUE_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "value", "source": INSTITUTION})
    Resource.objects.get_or_create(uri=DCTERMS_RELATION_URI, defaults={"resource_type": ResourceType.PROPERTY, "name": "relation", "source": INSTITUTION})
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES
    return

@pytest.fixture
def updater_default() -> SmartBulkUpdater:
    return SmartBulkUpdater(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=False)

@pytest.fixture
def updater_row_linking() -> SmartBulkUpdater:
    return SmartBulkUpdater(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=True, link_topology="row")

@pytest.fixture
def updater_mesh_linking() -> SmartBulkUpdater:
    return SmartBulkUpdater(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=True, link_topology="mesh")

@pytest.fixture
def updater_first_col_linking() -> SmartBulkUpdater:
    return SmartBulkUpdater(institution=INSTITUTION, base_uri=BASE_URI, link_row_cells=True, link_topology="first_column")

# simple_csv_data: 2 rows, 3 cells each (id, colA, colB)
simple_csv_data: List[Dict[str, Any]] = [
    {"id": "row1", "colA": "valA1", "colB": "valB1"},
    {"id": "row2", "colA": "valA2", "colB": "valB2"},
]
# Expected for simple_csv_data:
# Resources created by SBU: 1 Dataset + (2rows*3cells) IRIs + (2rows*3cells) Literals = 1 + 6 + 6 = 13
# Triples created by SBU (no linking): (2rows*3cells) hasPart + (2rows*3cells) rdf:value = 6 + 6 = 12

# --- Test Cases ---
@pytest.mark.django_db
def test_resource_and_structural_triple_creation_no_linking(initial_data_empty, updater_default):
    dataset_name = "myDataset"
    stats = updater_default.import_csv_with_smart_updates(simple_csv_data, dataset_name)

    assert stats.resources_created == 13
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES + 13
    assert stats.triples_created == 12
    assert Triple.objects.count() == 12

    dataset_res = Resource.objects.get(uri=mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name))
    assert dataset_res is not None

    for row_data in simple_csv_data:
        row_id_val = row_data["id"]
        for col_name, cell_value in row_data.items(): # This will include the 'id' column as a cell
            if not str(cell_value).strip(): continue # Skip if value is empty, as SBU would
            
            cell_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part(col_name), slugify_uri_part(row_id_val))
            cell_res = Resource.objects.get(uri=cell_uri)
            assert cell_res is not None
            assert cell_res.resource_type == ResourceType.IRI

            assert Triple.objects.filter(subject=dataset_res, predicate__uri=HAS_PART_URI, object=cell_res).exists()
            
            literal_res = Resource.objects.get(resource_type=ResourceType.LITERAL, value=str(cell_value), name=col_name)
            assert Triple.objects.filter(subject=cell_res, predicate__uri=RDF_VALUE_URI, object=literal_res).exists()

@pytest.mark.django_db
def test_skip_existing_resources(initial_data_empty, updater_default):
    dataset_name = "skipTest"
    stats1 = updater_default.import_csv_with_smart_updates(simple_csv_data, dataset_name)
    assert stats1.resources_created == 13 
    assert stats1.triples_created == 12
    initial_resource_count = Resource.objects.count()
    initial_triple_count = Triple.objects.count()

    stats2 = updater_default.import_csv_with_smart_updates(simple_csv_data, dataset_name)
    assert stats2.resources_created == 0
    assert stats2.resources_skipped == 6 # 2 rows * 3 cells/row
    assert stats2.triples_created == 0 
    assert Resource.objects.count() == initial_resource_count
    assert Triple.objects.count() == initial_triple_count

@pytest.mark.django_db
def test_update_existing_literals(initial_data_empty, updater_default):
    dataset_name = "updateTest"
    # Initial import of simple_csv_data: 1 Dataset, 6 Cell IRIs, 6 Literals = 13 SBU resources
    # 6 (Dataset->Cell) + 6 (Cell->Value) = 12 triples
    updater_default.import_csv_with_smart_updates(simple_csv_data, dataset_name)
    
    initial_literal_id_row1 = Resource.objects.get(value="row1", name="id")
    initial_literal_colA_row1 = Resource.objects.get(value="valA1", name="colA")
    initial_literal_colB_row2 = Resource.objects.get(value="valB2", name="colB", source=INSTITUTION, resource_type=ResourceType.LITERAL)

    updated_csv_data = [
        {"id": "newRow1ID", "colA": "newValA1", "colB": "valB1"}, # Cells for this row are NEW due to new ID.
        {"id": "row2", "colA": "valA2", "colB": "newValB2"},    # colB updated for existing cell id/row2.
    ]

    updater_update_strat = SmartBulkUpdater(
        institution=INSTITUTION, 
        base_uri=BASE_URI, 
        link_row_cells=False, 
        default_strategy=UpdateStrategy.UPDATE_VALUES
    )
    stats = updater_update_strat.import_csv_with_smart_updates(updated_csv_data, dataset_name)

    # Expected updates: Only the literal for colB/row2 (valB2 -> newValB2)
    assert stats.resources_updated == 1
    assert stats.triples_updated == 1

    # Expected creations from updated_csv_data:
    # Row 1 ("newRow1ID"): 3 new cell IRIs (id, colA, colB for newRow1ID)
    # Literals for Row 1: "newRow1ID" (new), "newValA1" (new). "valB1" (existing, reused by get_or_create)
    # Total new resources created = 3 Cell IRIs + 2 Literals = 5.
    assert stats.resources_created == 5
    
    # Expected triples created for the new cells of "newRow1ID":
    # 3 (Dataset->Cell) + 3 (Cell->Value) = 6 triples.
    assert stats.triples_created == 6

    # Verify updated values
    updated_literal_id_row1_obj = Resource.objects.get(pk=initial_literal_id_row1.pk) # Original "row1" literal
    assert updated_literal_id_row1_obj.value == "row1" # Should be unchanged as "newRow1ID" is a new cell/literal

    updated_literal_colA_row1_obj = Resource.objects.get(pk=initial_literal_colA_row1.pk) # Original "valA1" literal
    assert updated_literal_colA_row1_obj.value == "valA1" # Should be unchanged

    # Check the actual new literals created for the new row ID
    assert Resource.objects.get(value="newRow1ID", name="id", source=INSTITUTION).value == "newRow1ID"
    assert Resource.objects.get(value="newValA1", name="colA", source=INSTITUTION).value == "newValA1"
    
    # Check the updated literal for colB, row2
    updated_literal_colB_row2 = Resource.objects.get(pk=initial_literal_colB_row2.pk)
    assert updated_literal_colB_row2.value == "newValB2"

    # Ensure other original values remain unchanged where expected
    # Original valB1 literal associated with the first import's colb/row1 should still exist and be unchanged.
    assert Resource.objects.get(value="valB1", name="colB", source=INSTITUTION, resource_type=ResourceType.LITERAL, uri=None).value == "valB1"
    assert Resource.objects.get(value="valA2", name="colA", source=INSTITUTION).value == "valA2"

@pytest.mark.django_db
def test_row_linking_topology_row(initial_data_empty, updater_row_linking):
    dataset_name = "rowLinkDataset"
    stats = updater_row_linking.import_csv_with_smart_updates(simple_csv_data, dataset_name)
    # simple_csv_data: 2 rows, 3 cells each (id, colA, colB)
    # Row resources created: 2 (one for each row_id: "row1", "row2")
    # Total SBU resources: 1 Dataset + 6 Cell IRIs + 6 Literals + 2 Row IRIs = 15
    assert stats.resources_created == 15
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES + 15
    # Triples: 6 (Dataset->Cell) + 6 (Cell->Value) + 6 (Row->Cell for linking) = 18
    assert stats.triples_created == 18
    assert stats.row_links_created == 6 # 3 cells per row * 2 rows linked to their Row IRI

    for row_data in simple_csv_data:
        row_id_val = row_data["id"]
        row_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, "rows", slugify_uri_part(row_id_val))
        row_res = Resource.objects.get(uri=row_uri)
        assert row_res is not None
        assert row_res.resource_type == ResourceType.IRI
        assert not Triple.objects.filter(subject=row_res, predicate__uri="http://www.w3.org/1999/02/22-rdf-syntax-ns#type").exists()

        for col_name, cell_value in row_data.items():
            if not str(cell_value).strip(): continue
            cell_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part(col_name), slugify_uri_part(row_id_val))
            cell_res = Resource.objects.get(uri=cell_uri)
            assert Triple.objects.filter(subject=row_res, predicate__uri=HAS_PART_URI, object=cell_res).exists()


# three_cols_data: 1 row, 4 cells (id, colX, colY, colZ)
three_cols_data = [
    {"id": "rowM1", "colX": "valX1", "colY": "valY1", "colZ": "valZ1"},
]

@pytest.mark.django_db
def test_row_linking_topology_mesh(initial_data_empty, updater_mesh_linking):
    dataset_name = "meshLinkDataset"
    # SBU resources: 1 Dataset + 4 Cell IRIs + 4 Literals = 9
    # Triples: 4 (Dataset->Cell) + 4 (Cell->Value) + 6 (Cell->Cell relation) = 14
    stats = updater_mesh_linking.import_csv_with_smart_updates(three_cols_data, dataset_name)

    assert stats.resources_created == 1+4+4 # Dataset + Cell IRIs + Literals
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES + 9
    # For 4 cells (id, X,Y,Z), mesh links: (id-X), (id-Y), (id-Z), (X-Y), (X-Z), (Y-Z) = 4*3/2 = 6 links
    assert stats.row_links_created == 6
    assert stats.triples_created == 4 + 4 + 6
    
    cells = []
    row_id_val = three_cols_data[0]["id"]
    # Order of items from dict can be test-sensitive. Let's be explicit about the expected cells.
    # The SmartBulkUpdater iterates dict items, so order might matter for `first_column` but for mesh, all pairs are made.
    # For this test, let's assume a specific order for fetching for clarity, though SBU internally might see them differently.
    # Actual created cells will be id, colX, colY, colZ.
    cell_id_res = Resource.objects.get(uri=mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("id"), slugify_uri_part(row_id_val)))
    cell_x_res = Resource.objects.get(uri=mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colX"), slugify_uri_part(row_id_val)))
    cell_y_res = Resource.objects.get(uri=mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colY"), slugify_uri_part(row_id_val)))
    cell_z_res = Resource.objects.get(uri=mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colZ"), slugify_uri_part(row_id_val)))
    
    # Check a few expected dcterms:relation triples (SBU creates them one-way i->j)
    assert Triple.objects.filter(subject=cell_id_res, predicate__uri=DCTERMS_RELATION_URI, object=cell_x_res).exists()
    assert Triple.objects.filter(subject=cell_x_res, predicate__uri=DCTERMS_RELATION_URI, object=cell_y_res).exists()
    assert Triple.objects.filter(subject=cell_y_res, predicate__uri=DCTERMS_RELATION_URI, object=cell_z_res).exists()
    # Verify one of the non-sequential links based on SBU logic
    assert Triple.objects.filter(subject=cell_id_res, predicate__uri=DCTERMS_RELATION_URI, object=cell_z_res).exists()


def test_row_linking_topology_first_column(initial_data_empty, updater_first_col_linking):
    dataset_name = "firstColLinkDataset"
    # Data: {"id": "rowF1", "colP": "valP1", "colQ": "valQ1", "colR": "valR1"} - 4 cells
    # SBU resources: 1 Dataset + 4 Cell IRIs + 4 Literals = 9
    # SBU determines the "first column" cell based on the order of items in the row dictionary.
    # For this test, we assume "id" is the first item processed from the dict.
    # Triples: 4 (Dataset->Cell) + 4 (Cell->Value) + 3 (AnchorCell->OtherCell relation) = 11
    stats = updater_first_col_linking.import_csv_with_smart_updates(three_cols_data, dataset_name) # three_cols_data has id, colX, colY, colZ

    assert stats.resources_created == 1+4+4
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES + 9
    # If "id" is the anchor: links (id-colX), (id-colY), (id-colZ) = 3 links
    assert stats.row_links_created == 3 
    assert stats.triples_created == 4 + 4 + 3

    row_id_val = three_cols_data[0]["id"]
    # Assume 'id' column is the anchor based on typical dict iteration order for row.items()
    anchor_cell_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("id"), slugify_uri_part(row_id_val))
    other_cell_1_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colX"), slugify_uri_part(row_id_val))
    other_cell_2_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colY"), slugify_uri_part(row_id_val))
    other_cell_3_uri = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colZ"), slugify_uri_part(row_id_val))

    anchor_cell = Resource.objects.get(uri=anchor_cell_uri)
    other_cell_1 = Resource.objects.get(uri=other_cell_1_uri)
    other_cell_2 = Resource.objects.get(uri=other_cell_2_uri)
    other_cell_3 = Resource.objects.get(uri=other_cell_3_uri)
    
    assert Triple.objects.filter(subject=anchor_cell, predicate__uri=DCTERMS_RELATION_URI, object=other_cell_1).exists()
    assert Triple.objects.filter(subject=anchor_cell, predicate__uri=DCTERMS_RELATION_URI, object=other_cell_2).exists()
    assert Triple.objects.filter(subject=anchor_cell, predicate__uri=DCTERMS_RELATION_URI, object=other_cell_3).exists()
    assert not Triple.objects.filter(subject=other_cell_1, predicate__uri=DCTERMS_RELATION_URI, object=other_cell_2).exists()


def test_empty_csv_data(initial_data_empty, updater_default):
    dataset_name = "emptyDataset"
    stats = updater_default.import_csv_with_smart_updates([], dataset_name)
    assert stats.rows_processed == 0
    assert stats.cells_processed == 0
    assert stats.resources_created == 0 # No dataset resource created if no cells to process
    assert stats.triples_created == 0
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES # Only fixture resources
    assert Triple.objects.count() == 0


def test_csv_data_with_empty_values(initial_data_empty, updater_default):
    dataset_name = "emptyValuesDataset"
    data = [
        {"id": "row1", "colA": "valA1", "colB": ""}, 
        {"id": "row2", "colA": None, "colB": "valB2"}, 
    ]
    # Non-empty/non-None cells: (row1,id), (row1,colA), (row2,id), (row2,colB) -> 4 cells
    # SBU Resources: 1 Dataset + 4 Cell IRIs + 4 Literals = 9
    # SBU Triples: 4 Dataset->Cell + 4 Cell->Value = 8
    stats = updater_default.import_csv_with_smart_updates(data, dataset_name)
    
    assert stats.resources_created == 9
    assert Resource.objects.count() == NUM_FIXTURE_RESOURCES + 9
    assert stats.triples_created == 8
    assert Triple.objects.count() == 8

    cell_uri_colB_row1 = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colB"), slugify_uri_part("row1"))
    assert not Resource.objects.filter(uri=cell_uri_colB_row1).exists()
    cell_uri_colA_row2 = mint_uri(BASE_URI, INSTITUTION, "datasets", dataset_name, slugify_uri_part("colA"), slugify_uri_part("row2"))
    assert not Resource.objects.filter(uri=cell_uri_colA_row2).exists()


# Consider adding tests for timestamp-based updates if that feature is critical and stable.
# Consider adding tests for error handling, e.g. DB connection issues (might require more complex mocking)
