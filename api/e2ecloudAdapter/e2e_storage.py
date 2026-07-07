"""
E2E Cloud Storage adapter with mock implementations.
"""
import logging
from typing import List, Optional, Dict, Any, Tuple, BinaryIO

# Mock logger
logger = logging.getLogger(__name__)

# Mock storage
_mock_storage = {}

def upload_or_update_data_gcs(
    bucket_name: str,
    hash_identifier: str,
    text_data: str,
    voice_data_bytes: bytes,
    random_num: Optional[int] = None,
    audio_filename: Optional[str] = None,
    text_filename: Optional[str] = None,
    audio_content_type: Optional[str] = None,
    text_content_type: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Mock implementation of the training-data upload interface."""
    suffix = random_num if random_num is not None else "mock"
    text_blob_name = f"{hash_identifier}/{text_filename or f'text_{suffix}.txt'}"
    voice_blob_name = f"{hash_identifier}/{audio_filename or f'voice_{suffix}.wav'}"

    logger.info(f"[MOCK] Uploading training data to {bucket_name}/{hash_identifier}")
    _mock_storage[text_blob_name] = {
        'data': text_data.encode("utf-8"),
        'content_type': text_content_type or "text/plain",
        'metadata': {'hash_identifier': hash_identifier},
    }
    _mock_storage[voice_blob_name] = {
        'data': voice_data_bytes,
        'content_type': audio_content_type or "audio/wav",
        'metadata': {'hash_identifier': hash_identifier},
    }

    return f"mock://{bucket_name}/{text_blob_name}", f"mock://{bucket_name}/{voice_blob_name}"

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
