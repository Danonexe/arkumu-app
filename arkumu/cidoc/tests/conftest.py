import pytest
from rdflib import Graph, Namespace
import os

@pytest.fixture(scope="session")
def cidoc_rdf():
    """Load the CIDOC-CRM RDF file for testing"""
    g = Graph()
    rdf_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'schema',
        'CIDOC_CRM_v7.1.1.rdf'
    )
    g.parse(rdf_path, format='xml')
    return g

@pytest.fixture(scope="session")
def cidoc_ns():
    """CIDOC namespace for testing"""
    return Namespace("http://www.cidoc-crm.org/cidoc-crm/")

# Common fixtures used across test files 