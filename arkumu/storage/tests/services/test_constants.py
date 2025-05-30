"""
Test constants for storage service tests.

This file contains constants used across multiple test files to ensure consistency
and make it easier to manage test bucket names and other shared values.
"""

# Base test bucket names
TEST_BUCKET_NAME = 'test-bucket'
TEST_INGEST_BUCKET = 'test-ingest-bucket'
TEST_PRODUCTION_BUCKET = 'test-production-bucket'

# Organization-specific test buckets (one per source/organization)
TEST_ORG_BUCKETS = {
    'rsh': 'test-org-rsh',  # Robert Schumann Hochschule Düsseldorf
    'khm': 'test-org-khm',  # Kunsthochschule für Medien Köln
    'fuk': 'test-org-fuk',  # Folkwang Universität der Künste
    'hmt': 'test-org-hmt',  # Hochschule für Musik und Tanz Köln
    'det': 'test-org-det',  # Hochschule für Musik Detmold
}

# Legacy constant for backward compatibility
TEST_ORG_BUCKET_NAME = TEST_ORG_BUCKETS['fuk']  # Default to FUK for existing tests

# Test folder names
TEST_FOLDER_NAME = 'test-folder'
TEST_BASE_FOLDERS = ['data', 'metadata']

# Test file constants
TEST_FILE_SIZES = {
    'small': 1024,           # 1KB
    'medium': 5 * 1024 * 1024,   # 5MB
    'large': 10 * 1024 * 1024,   # 10MB
}

# Upload configuration constants
TEST_MULTIPART_THRESHOLD = 5 * 1024 * 1024  # 5MB
TEST_CHUNK_SIZE = 75  # Files per chunk for batched uploads
TEST_MAX_CONCURRENT = 3  # Max concurrent uploads

# Test content types
TEST_CONTENT_TYPES = {
    'text': 'text/plain',
    'json': 'application/json',
    'binary': 'application/octet-stream',
    'image': 'image/jpeg',
    'video': 'video/mp4',
}

# Test folder structures for folder upload tests
TEST_FOLDER_STRUCTURES = {
    'simple': [
        'file1.txt',
        'file2.txt',
        'file3.txt'
    ],
    'nested': [
        'project/src/main.js',
        'project/src/components/Button.js',
        'project/src/components/Header.js',
        'project/assets/style.css',
        'project/assets/images/logo.png',
        'project/docs/README.md',
        'project/docs/api.md',
        'project/package.json'
    ],
    'deep': [
        'root/level1/level2/level3/deep_file.txt',
        'root/level1/level2/another_file.js',
        'root/level1/config.json',
        'root/README.md'
    ]
} 