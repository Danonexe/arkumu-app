from rest_framework import serializers

class S3ConfigSerializer(serializers.Serializer):
    aws_access_key_id = serializers.CharField(required=False, allow_null=True)
    aws_secret_access_key = serializers.CharField(required=False, allow_null=True)
    region_name = serializers.CharField(required=False, default='us-east-1')
    bucket_name = serializers.CharField(required=False, default='arkumu-files')
    base_url = serializers.CharField(required=False)

class DirectoryImportSerializer(serializers.Serializer):
    """Simplified serializer for importing all CSV files from a directory."""
    directory_path = serializers.CharField(
        required=True,
        help_text="Path to directory containing CSV files to import"
    )
    institution = serializers.CharField(
        required=False, 
        default='DEFAULT',
        help_text="Institution code for the import"
    )
    base_uri = serializers.CharField(
        required=False, 
        default='http://arkumu.org/data',
        help_text="Base URI for generated resources"
    )
    delimiter = serializers.CharField(
        required=False, 
        default=';',
        help_text="CSV column delimiter"
    )
    has_quoted_fields = serializers.BooleanField(
        required=False, 
        default=False,
        help_text="Whether fields in the CSV are quoted"
    )
    relationship_config_path = serializers.CharField(
        required=False, 
        allow_null=True,
        help_text="Optional path to relationship configuration file"
    )
    file_columns = serializers.DictField(
        required=False, 
        default=dict,
        help_text="Dict mapping table names to lists of column names containing file paths"
    )
    files_base_directory = serializers.CharField(
        required=False, 
        allow_null=True,
        help_text="Base directory for resolving relative file paths (defaults to directory_path)"
    )
    s3_config = S3ConfigSerializer(
        required=False,
        help_text="Optional S3 configuration for file uploads"
    )

class ClearDatabaseSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=True, help_text="Set to true to confirm database clearing") 