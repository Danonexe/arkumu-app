from rest_framework import serializers

class S3ConfigSerializer(serializers.Serializer):
    aws_access_key_id = serializers.CharField(required=False, allow_null=True)
    aws_secret_access_key = serializers.CharField(required=False, allow_null=True)
    region_name = serializers.CharField(required=False, default='us-east-1')
    bucket_name = serializers.CharField(required=False, default='arkumu-files')
    base_url = serializers.CharField(required=False)

class SingleCSVImportSerializer(serializers.Serializer):
    csv_path = serializers.CharField(required=True)
    dataset_name = serializers.CharField(required=False, allow_null=True)
    institution = serializers.CharField(required=False, default='DEFAULT')
    base_uri = serializers.CharField(required=False, default='http://arkumu.org/data')
    delimiter = serializers.CharField(required=False, default=';')
    has_quoted_fields = serializers.BooleanField(required=False, default=False)
    is_relationship_table = serializers.BooleanField(required=False, default=False)
    fk_columns = serializers.ListField(required=False, allow_null=True)
    file_columns = serializers.ListField(required=False, default=[])
    files_base_directory = serializers.CharField(required=False, allow_null=True)
    s3_config = S3ConfigSerializer(required=False)

class CSVImportSerializer(serializers.Serializer):
    directory_path = serializers.CharField(required=True)
    institution = serializers.CharField(required=False, default='DEFAULT')
    base_uri = serializers.CharField(required=False, default='http://arkumu.org/data')
    delimiter = serializers.CharField(required=False, default=';')
    has_quoted_fields = serializers.BooleanField(required=False, default=False)
    relationship_config_path = serializers.CharField(required=False, allow_null=True)
    file_columns = serializers.DictField(required=False, default=dict)
    files_base_directory = serializers.CharField(required=False, allow_null=True)
    s3_config = S3ConfigSerializer(required=False)

class FileColumnsConfigSerializer(serializers.Serializer):
    config = serializers.DictField(required=True)
    output_path = serializers.CharField(required=False, allow_null=True)

class FileColumnsConfigGetSerializer(serializers.Serializer):
    path = serializers.CharField(required=True)

class ClearDatabaseSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=True, help_text="Set to true to confirm database clearing") 