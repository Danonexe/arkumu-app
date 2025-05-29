from arkumu.storage.models import S3FileObject
from arkumu.metadata.models import Resource
from arkumu.storage.services.bucket_service import BucketService
from django.db import transaction
import os

class FileResourceMatcherService:
    def __init__(self, logger=None):
        self.logger = logger if logger else print # Basic logging
        self.bucket_service = BucketService() # Instantiate BucketService

    def _log(self, message):
        if callable(self.logger):
            self.logger(message)
        # If using Django signals or a more robust logging framework, integrate here

    def match_and_link_by_filename_to_resource_value(self, s3_file_queryset=None):
        """
        Matches S3FileObjects to Resources by comparing the S3FileObject's file_name
        (stripping the extension) to the Resource's value.
        Considers only S3FileObjects where related_resource is null.
        """
        if s3_file_queryset is None:
            files_to_process = S3FileObject.objects.filter(related_resource__isnull=True)
        else:
            # Ensure we only process unlinked files from the provided queryset
            files_to_process = s3_file_queryset.filter(related_resource__isnull=True)

        processed_count = 0
        linked_count = 0
        ambiguous_count = 0 
        error_on_match_count = 0

        self._log(f"Starting matching process. Found {files_to_process.count()} S3 files to process for linking.")

        for s3_file in files_to_process:
            processed_count += 1
            try:
                file_name_without_extension, _ = os.path.splitext(s3_file.file_name)
                
                if not file_name_without_extension:
                    self._log(f"Skipping S3FileObject ID {s3_file.id} ('{s3_file.s3_key}') for matching due to empty filename after stripping extension.")
                    continue

                matching_resources = Resource.objects.filter(value__iexact=file_name_without_extension) # Made case-insensitive
                
                match_count = matching_resources.count()

                if match_count == 1:
                    resource_to_link = matching_resources.first()
                    s3_file.related_resource = resource_to_link
                    s3_file.save(update_fields=['related_resource', 'updated_at'])
                    linked_count += 1
                    self._log(f"Linked S3FileObject ID {s3_file.id} ({s3_file.s3_key}) to Resource ID {resource_to_link.id} ('{resource_to_link.value}').")
                elif match_count > 1:
                    ambiguous_count += 1
                    self._log(f"Ambiguous match for S3FileObject ID {s3_file.id} ({s3_file.s3_key}): Found {match_count} Resources with value '{file_name_without_extension}'. No link made.")
                else:
                    self._log(f"No Resource found with value '{file_name_without_extension}' for S3FileObject ID {s3_file.id} ({s3_file.s3_key}).")

            except Exception as e:
                error_on_match_count += 1
                self._log(f"Error matching S3FileObject ID {s3_file.id} ('{s3_file.s3_key}'): {e}")
        
        self._log(f"Matching process finished. Processed for linking: {processed_count}, Linked: {linked_count}, Ambiguous: {ambiguous_count}, Errors during matching: {error_on_match_count}.")
        return processed_count, linked_count, ambiguous_count, error_on_match_count

    def discover_and_sync_s3_files(self, bucket_name: str, prefix: str = ""):
        self._log(f"Starting S3 discovery and sync for bucket: '{bucket_name}', prefix: '{prefix or "(root)"}'")
        
        try:
            s3_object_list = self.bucket_service.list_bucket_contents(bucket_name=bucket_name, prefix=prefix)
        except Exception as e:
            self._log(f"Error calling BucketService.list_bucket_contents for {bucket_name}/{prefix}: {e}")
            return 0, 0, 0, 1 # synced, created, skipped, errors

        synced_count = 0
        created_count = 0
        skipped_count = 0
        error_on_create_count = 0

        # Fetch all relevant existing S3 keys from our database for quick lookup.
        # This assumes s3_key is unique across all buckets. If not, and s3_key only contains the object key,
        # you might need a more complex way to identify if a file from a specific bucket is already in DB.
        # For now, we assume s3_key is globally unique or refers to the full path including bucket if not.
        # A simple approach if s3_key is just the object key: filter by a combination of bucket name + key if you store bucket in S3FileObject.
        # However, S3FileObject doesn't currently store the bucket_name explicitly.
        # Let's assume s3_key is the full path or unique enough for now.
        
        # Optimization: fetch only keys starting with the prefix if that makes sense for your s3_key structure
        # However, list_bucket_contents already filters by prefix, so we mainly check for existence.
        existing_db_keys = set(S3FileObject.objects.values_list('s3_key', flat=True))

        for s3_item in s3_object_list:
            s3_key = s3_item.get('Key') 
            # Assuming 'Key' is the field name from BucketService.list_bucket_contents
            # Also, BucketService.list_bucket_contents might already filter out folders (items ending with '/').
            # If not, we add the check here.
            if not s3_key or s3_key.endswith('/'): 
                skipped_count +=1
                continue

            # Construct a unique identifier if s3_key from list_bucket_contents does not include bucket_name
            # For example: unique_file_id = f"{bucket_name}/{s3_key}"
            # Then check `if unique_file_id not in existing_db_keys:`
            # And store `unique_file_id` in `S3FileObject.s3_key`
            # For this implementation, we assume s3_key as returned by list_bucket_contents is what we store.

            if s3_key not in existing_db_keys:
                try:
                    file_name = os.path.basename(s3_key)
                    file_size = s3_item.get('Size', 0) # Assuming 'Size' is available
                    # content_type might be available via s3_item or need a head_object call
                    # For files discovered this way, session is None.
                    S3FileObject.objects.create(
                        session=None, 
                        file_name=file_name,
                        original_path=s3_key, # Or adjust as needed
                        s3_key=s3_key,
                        file_size_bytes=file_size,
                        # content_type="application/octet-stream", # Default or get from s3_item if possible
                        status='verified' # Discovered from S3, so considered 'verified' in terms of existence
                    )
                    created_count += 1
                    self._log(f"Created new S3FileObject for key: {s3_key} from bucket {bucket_name}")
                except Exception as e:
                    self._log(f"Error creating S3FileObject for key {s3_key} from bucket {bucket_name}: {e}")
                    error_on_create_count +=1
            else:
                synced_count += 1
        
        self._log(f"S3 discovery and sync finished for {bucket_name}/{prefix}. "
                  f"DB records in sync/already existed: {synced_count}, New records created: {created_count}, "
                  f"Skipped (folders/invalid): {skipped_count}, Errors during creation: {error_on_create_count}.")
        return synced_count, created_count, skipped_count, error_on_create_count

