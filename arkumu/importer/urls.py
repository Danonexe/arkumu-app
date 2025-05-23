from django.urls import path
from arkumu.importer.views.import_api import CSVImportView, DirectoryImportView, FileColumnsConfigView

app_name = 'importer'

urlpatterns = [
    # CSV Import API endpoints
    path('api/import/csv', CSVImportView.as_view(), name='import_csv'),
    path('api/import/directory', DirectoryImportView.as_view(), name='import_directory'),
    path('api/import/file-columns-config', FileColumnsConfigView.as_view(), name='file_columns_config'),
] 