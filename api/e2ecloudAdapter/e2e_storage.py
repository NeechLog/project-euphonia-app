"""
E2E Cloud Storage adapter with mock implementations.
"""
import logging
from typing import List, Optional, Dict, Any, Tuple, BinaryIO
import uuid

# Mock logger
logger = logging.getLogger(__name__)

# Mock storage
_mock_storage = {}

async def upload_or_update_data_gcs(
    bucket_name: str,
    data: bytes,
    destination_blob_name: str,
    content_type: str = "application/octet-stream",
    metadata: Optional[Dict[str, str]] = None
) -> str:
    """Mock implementation of upload_or_update_data_gcs."""
    logger.info(f"[MOCK] Uploading to {bucket_name}/{destination_blob_name}")
    file_id = str(uuid.uuid4())
    _mock_storage[destination_blob_name] = {
        'data': data,
        'content_type': content_type,
        'metadata': metadata or {},
        'id': file_id
    }
    return f"mock://{bucket_name}/{destination_blob_name}"

def get_oldest_training_data(bucket_name: str, prefix: str = "") -> Optional[Dict[str, Any]]:
    """Mock implementation of get_oldest_training_data."""
    logger.info(f"[MOCK] Getting oldest training data from {bucket_name} with prefix {prefix}")
    
    # Find all keys with the given prefix
    matching_keys = [k for k in _mock_storage.keys() if k.startswith(prefix)]
    
    if not matching_keys:
        return None
        
    # Sort by key (as a simple way to determine 'oldest' in this mock)
    oldest_key = sorted(matching_keys)[0]
    
    return {
        'name': oldest_key,
        'bucket': bucket_name,
        'size': len(_mock_storage[oldest_key]['data']),
        'metadata': _mock_storage[oldest_key]['metadata']
    }

def list_all_hash_identifiers(bucket_name: str, prefix: str = "") -> List[str]:
    """Mock implementation of list_all_hash_identifiers."""
    logger.info(f"[MOCK] Listing all hash identifiers in {bucket_name} with prefix {prefix}")
    
    # Extract hash identifiers from keys with the given prefix
    hash_identifiers = []
    for key in _mock_storage.keys():
        if key.startswith(prefix):
            # Assuming the hash is the part after the last '/' in the key
            parts = key.split('/')
            if parts:
                hash_identifiers.append(parts[-1])
    
    return hash_identifiers

# Add any additional storage-related functions that might be needed

def clear_mock_storage():
    """Clear the mock storage. Useful for testing."""
    global _mock_storage
    _mock_storage = {}
    logger.info("[MOCK] Storage cleared")
