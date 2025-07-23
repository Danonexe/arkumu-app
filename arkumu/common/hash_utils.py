"""
Centralized hashing utilities for consistent hash generation across the application.

Uses BLAKE2B for better performance and collision resistance than SHA-256.
"""
import hashlib
from arkumu.common.uri_utils import normalize_string_nfc


def generate_value_hash(value: str) -> str:
    """
    Generate a consistent hash for resource values.
    
    Uses BLAKE2B with 32-byte digest (64 hex characters) for database storage.
    The value is normalized using NFC before hashing for Unicode consistency.
    
    Args:
        value: The string value to hash
        
    Returns:
        64-character hexadecimal hash string
        
    Example:
        >>> generate_value_hash("Hello World")
        '4b227777d4dd1fc61c6f884f48641d02b4d121d3fd328cb08b5531fcacdabf8a...'
    """
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
        
    # Normalize Unicode to NFC form for consistent hashing
    normalized_value = normalize_string_nfc(value)
    
    # Use BLAKE2B with 32-byte digest (64 hex chars) for database storage
    return hashlib.blake2b(normalized_value.encode('utf-8'), digest_size=32).hexdigest()


def generate_value_hash_and_normalize(value: str) -> tuple[str, str]:
    """
    Generate hash and return both hash and normalized value to avoid double normalization.
    
    Args:
        value: The string value to hash and normalize
        
    Returns:
        Tuple of (hash, normalized_value)
    """
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
        
    # Normalize once
    normalized_value = normalize_string_nfc(value)
    
    # Generate hash from normalized value
    value_hash = hashlib.blake2b(normalized_value.encode('utf-8'), digest_size=32).hexdigest()
    
    return value_hash, normalized_value


def generate_uri_hash(value: str, digest_size: int = 8) -> str:
    """
    Generate a shorter hash for URI generation.
    
    Uses BLAKE2B with configurable digest size for URL-friendly identifiers.
    
    Args:
        value: The string value to hash
        digest_size: Number of bytes for the digest (default: 8 = 16 hex chars)
        
    Returns:
        Hexadecimal hash string (2 * digest_size characters)
        
    Example:
        >>> generate_uri_hash("Hello World", digest_size=8)
        '4b227777d4dd1fc6'
    """
    if not isinstance(value, str):
        raise ValueError("Value must be a string")
        
    # Normalize Unicode to NFC form for consistent hashing
    normalized_value = normalize_string_nfc(value)
    
    # Use BLAKE2B with smaller digest for URI generation
    return hashlib.blake2b(normalized_value.encode('utf-8'), digest_size=digest_size).hexdigest()


# Legacy function name for backward compatibility
def hash_value(value: str) -> str:
    """Legacy alias for generate_value_hash."""
    return generate_value_hash(value)