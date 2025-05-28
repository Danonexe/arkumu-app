from django.urls import path
from arkumu.metadata.views import dashboard_views

app_name = 'metadata'

urlpatterns = [
    path('dashboard/', dashboard_views.metadata_dashboard, name='metadata_dashboard'),
    path('resources/', dashboard_views.resource_list, name='resource_list'),
    path('resources/<uuid:resource_id>/', dashboard_views.resource_detail, name='resource_detail'),
    path('resources/<uuid:resource_id>/graph/', dashboard_views.resource_graph, name='resource_graph'),
    path('triples/search/', dashboard_views.triple_search, name='triple_search'),
    path('triples/', dashboard_views.triple_list, name='triple_list'),
    path('graph/', dashboard_views.full_graph_view, name='full_graph_view'),
    path('graph/data/', dashboard_views.graph_data_view, name='graph_data'),
    path('bulk-editor/', dashboard_views.bulk_triple_editor, name='bulk_triple_editor'),
    path('bulk-editor/query/', dashboard_views.query_relationships, name='query_relationships'),
    path('bulk-editor/create/', dashboard_views.create_bulk_triples, name='create_bulk_triples'),
]
