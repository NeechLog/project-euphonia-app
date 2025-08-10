import base64
import logging
import os
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from google.cloud import storage
from google.cloud.storage import Blob, Bucket

# File extensions and type identifiers
TEXT_EXTENSION = '.txt'
BINARY_EXTENSION = '.wav'
TEXT_PREFIX = 'text_'
VOICE_PREFIX = 'voice_'
TEXT_CONTENT_TYPE = 'text/plain'
BINARY_CONTENT_TYPE = 'application/octet-stream'

def _get_matching_blobs(bucket:Bucket, prefix: str) -> List[Blob]:
    """Get all blobs with the given prefix."""
    logger.debug(f"Fetching blobs with prefix: {prefix} from bucket: {bucket.name}")
    blobs = list(bucket.client.list_blobs(bucket.name, prefix=prefix))
    logger.debug(f"Found {len(blobs)} blobs with prefix: {prefix}")
    return blobs

def _get_random_number() -> int:
    """Generate a random 6-digit number."""
    num = random.randint(100000, 999999)
    logger.debug(f"Generated random number: {num}")
    return num

def _upload_blob(bucket:Bucket, blob_name: str, data: str, content_type: str) -> str:
    """Helper function to upload data to a blob."""
    logger.debug(f"Uploading to blob: {blob_name} with content type: {content_type}")
    try:
        blob = bucket.blob(blob_name)
        blob.upload_from_string(
            data=data,
            content_type=content_type
        )
        url = f"https://storage.googleapis.com/{bucket.name}/{blob.name}"
        logger.info(f"Successfully uploaded to {url}")
        return url
    except Exception as e:
        logger.error(f"Failed to upload blob {blob_name}. Error: {str(e)}")
        raise

def upload_or_update_data_gcs(
    bucket_name: str, 
    hash_identifier: str, 
    text_data: str, 
    voice_data_bytes: bytes, 
    random_num: Optional[int] = None,
    audio_filename: Optional[str] = None,
    text_filename: Optional[str] = None,
    audio_content_type: Optional[str] = None,
    text_content_type: Optional[str] = None
) -> Tuple[Optional[str], Optional[str]]:
    """
    Uploads or updates text and voice data in Google Cloud Storage as separate files.

    The objects will be stored as:
    - Text: '{hash_identifier}/text_<suffix>.<ext>' or custom filename if provided
    - Voice: '{hash_identifier}/voice_<suffix>.<ext>' or custom filename if provided

    Args:
        bucket_name: The name of the Google Cloud Storage bucket.
        hash_identifier: A unique identifier for the data (e.g., a SHA256 hash).
        text_data: The text string to be stored.
        voice_data_bytes: The raw voice data in bytes.
        random_num: Optional random number to use for filenames. If None, checks if files exist.
        audio_filename: Optional custom filename for the audio file (without path).
        text_filename: Optional custom filename for the text file (without path).
        audio_content_type: Optional content type for the audio file.
        text_content_type: Optional content type for the text file.

    Returns:
        Tuple of (text_url, voice_url) if successful, (None, None) otherwise.
    """
    logger.info(f"Starting upload/update for hash: {hash_identifier}")
    try:
        if not isinstance(voice_data_bytes, bytes):
            error_msg = "voice_data_bytes must be of type bytes"
            logger.error(error_msg)
            raise TypeError(error_msg)
        
        # Initialize GCS client and get bucket
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Check if any files exist in the hash_identifier folder
        prefix = f"{hash_identifier}/"
        logger.debug(f"Checking for existing blobs with prefix: {prefix}")
        blobs = _get_matching_blobs(bucket, prefix)
        
        # If no files exist and no random number provided, use 0 as suffix
        if not blobs and random_num is None:
            suffix = "0"
            logger.debug("No existing blobs found and no random number provided, using suffix: 0")
        else:
            # Use provided random number or generate a new one
            suffix = str(random_num) if random_num is not None else str(_get_random_number())
            logger.debug(f"Using suffix: {suffix} (random_num: {random_num})")

        # Generate text filename
        text_filename, text_extension = _construct_filename(
            TEXT_PREFIX, text_filename, suffix, TEXT_EXTENSION
        )
        text_filename = f"{hash_identifier}/{text_filename}"
        text_content_type = text_content_type or TEXT_CONTENT_TYPE

        # Generate audio filename
        audio_filename, audio_extension = _construct_filename(
            VOICE_PREFIX, audio_filename, suffix, BINARY_EXTENSION
        )
        audio_filename = f"{hash_identifier}/{audio_filename}"
        audio_content_type = audio_content_type or BINARY_CONTENT_TYPE

        # Upload text data
        logger.info(f"Uploading text data to {text_filename}")
        text_url = _upload_blob(bucket, text_filename, text_data, text_content_type)
        logger.info(f"Successfully uploaded text data to {text_url}")

        # Upload voice data (base64 encoded)
        logger.info(f"Uploading voice data to {audio_filename}")
        #encoded_voice = base64.b64encode(voice_data_bytes).decode('utf-8')
        voice_url = _upload_blob(bucket, audio_filename, voice_data_bytes, audio_content_type)
        logger.info(f"Successfully uploaded voice data to {voice_url}")

        logger.info(f"Successfully uploaded text and voice data with suffix: {suffix}")
        return text_url, voice_url

    except Exception as e:
        logger.exception("An error occurred during GCS upload")
        return None, None

def _construct_filename(prefix: str, custom_name: Optional[str], suffix: str, default_extension: str) -> Tuple[str, str]:
    """Construct a filename with proper prefix and suffix handling.
    
    The function handles three main cases:
    1. No custom_name: Returns "{prefix}{suffix}{default_extension}"
    2. Custom name without numeric suffix: Returns "{base_name}_{prefix}{suffix}{extension}"
    3. Custom name with numeric suffix: Replaces the suffix and returns "{base_name}_{prefix}{suffix}{extension}"
    
    Args:
        prefix: The prefix to prepend to the filename (e.g., "text_" or "voice_")
        custom_name: Optional custom filename (without path). If None, uses default naming.
        suffix: Numeric suffix to append (e.g., "123"). Replaces existing numeric suffix if present.
        default_extension: Default extension to use if none in custom_name (e.g., ".txt")
        
    Returns:
        Tuple of (generated_filename, extension_used)
        
    Examples:
        >>> _construct_filename("text_", None, "123", ".txt")
        ("text_123.txt", ".txt")
        
        >>> _construct_filename("text_", "custom.txt", "123", ".txt")
        ("custom_text_123.txt", ".txt")
        
        >>> _construct_filename("text_", "file_456.txt", "123", ".txt")
        ("file_text_123.txt", ".txt")
    """
    if not custom_name:
        return f"{prefix}{suffix}{default_extension}", default_extension
    
    # Get the base name from the custom name (without path and extension)
    base_name = Path(custom_name).stem
    
    # Handle case where filename already has a numeric suffix
    name_parts = base_name.rsplit('_', 1)
    if len(name_parts) > 1 and name_parts[-1].isdigit():
        # If the filename already ends with a number, replace it with our suffix
        base_name = name_parts[0]
    
    # Always apply the prefix and suffix
    extension = Path(custom_name).suffix or default_extension
    return f"{base_name}_{prefix}{suffix}{extension}", extension


def _extract_suffix(blob_name: str, prefix: str) -> Optional[str]:
    """Extract the suffix from a blob name based on the expected pattern.
    
    Handles both patterns:
    1. {prefix}{suffix}.ext (legacy)
    2. {base_name}_{prefix}{suffix}.ext (new format)
    """
    logger.debug(f"Extracting suffix from blob: {blob_name} with prefix: {prefix}")
    # Remove the directory part if present
    base_name = os.path.basename(blob_name)
    logger.debug(f"Base name after removing path: {base_name}")
    
    # Check if the base name starts with the prefix
    if base_name.startswith(prefix):
        # Legacy format: {prefix}{suffix}.ext
        suffix_part = base_name[len(prefix):].rsplit('.', 1)[0]
        logger.debug(f"Legacy format detected. Extracted suffix: {suffix_part}")
        return suffix_part if suffix_part.isdigit() else None
    
    # New format: {base_name}_{prefix}{suffix}.ext
    if f'_{prefix}' in base_name:
        # Extract the part after the prefix
        after_prefix = base_name.split(f'_{prefix}', 1)[1]
        # Get the suffix (digits before the extension)
        suffix_part = after_prefix.split('.', 1)[0]
        logger.debug(f"New format detected. Extracted suffix: {suffix_part}")
        return suffix_part if suffix_part.isdigit() else None
    
    logger.debug("No matching format found for blob name")
    return None

def _find_matching_pair(blobs: List[Blob], random_num: Optional[int] = None) -> Tuple[Optional[Blob], Optional[Blob]]:
    """Find matching text and voice blobs with the same random number."""
    text_blob = None
    voice_blob = None
    
    # If random_num is provided, look for matching files with the random number
    if random_num is not None:
        random_str = str(random_num)
        for blob in blobs:
            suffix = _extract_suffix(blob.name, TEXT_PREFIX if TEXT_PREFIX in blob.name else VOICE_PREFIX)
            if suffix == random_str:
                if TEXT_PREFIX in blob.name:
                    text_blob = blob
                elif VOICE_PREFIX in blob.name:
                    voice_blob = blob
        if text_blob and voice_blob:
            return text_blob, voice_blob
    
    # If no random_num or no match, find all matching text/voice pairs
    text_blobs = []
    voice_blobs = []
    
    for blob in blobs:
        name = blob.name
        if f"{TEXT_PREFIX}" in name:
            suffix = _extract_suffix(name, TEXT_PREFIX)
            if suffix is not None:
                text_blobs.append((blob, suffix))
        elif f"{VOICE_PREFIX}" in name:
            suffix = _extract_suffix(name, VOICE_PREFIX)
            if suffix is not None:
                voice_blobs.append((blob, suffix))
    
    # Find matching suffixes between text and voice blobs
    text_suffixes = {suffix: blob for blob, suffix in text_blobs}
    voice_suffixes = {suffix: blob for blob, suffix in voice_blobs}
    
    # Find common suffixes
    common_suffixes = set(text_suffixes.keys()) & set(voice_suffixes.keys())
    
    if common_suffixes:
        # Get the oldest pair by creation time
        oldest_pair = None
        oldest_time = None
        
        for suffix in common_suffixes:
            text_blob = text_suffixes[suffix]
            voice_blob = voice_suffixes[suffix]
            # Use the older of the two timestamps as the pair's timestamp
            pair_time = min(text_blob.time_created, voice_blob.time_created)
            
            if oldest_time is None or pair_time < oldest_time:
                oldest_time = pair_time
                oldest_pair = (text_blob, voice_blob)
        
        if oldest_pair:
            return oldest_pair
    
    # If no matching pairs found, try to find _0 suffix files
    text_blob = next((b for b in blobs if 
                    (f'/{TEXT_PREFIX}0' in b.name and b.name.endswith(TEXT_EXTENSION)) or
                    (f'/{VOICE_PREFIX}0' in b.name and b.name.endswith(BINARY_EXTENSION))), None)
    
    # If we found a text blob, look for matching voice blob with same suffix
    if text_blob:
        suffix = '0'  # Default suffix if we can't extract it
        if f'/{TEXT_PREFIX}' in text_blob.name:
            suffix = text_blob.name.split(f'/{TEXT_PREFIX}')[1].split('.')[0]
        
        # Look for voice blob with same suffix
        voice_blob = next((b for b in blobs 
                         if f'/{VOICE_PREFIX}{suffix}.' in b.name), None)
        return text_blob, voice_blob
    
    return None, None

def get_oldest_blob_pairs(bucket_name: str, hash_identifier: str) -> Optional[List[Dict[str, str]]]:
    """
    Retrieves the oldest blob pairs (text and voice) for a given hash identifier.
    
    Args:
        bucket_name: The name of the Google Cloud Storage bucket.
        hash_identifier: The unique identifier for the data.
        
    Returns:
        A list of up to 2 dictionaries, each containing 'text_url', 'voice_url' with gs:// URLs,
        and 'suffix' for each pair. Returns None if no matching file pairs are found.
    """
    try:
        # Initialize GCS client and get bucket
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # Get all blobs with the given prefix
        prefix = f"{hash_identifier}/"
        blobs = _get_matching_blobs(bucket, prefix)
        
        # Group blobs by their suffix
        text_blobs = {}
        voice_blobs = {}
        
        for blob in blobs:
            name = blob.name
            if f"{TEXT_PREFIX}" in name:
                suffix = _extract_suffix(name, TEXT_PREFIX)
                if suffix is not None:
                    text_blobs[suffix] = blob
            elif f"{VOICE_PREFIX}" in name:
                suffix = _extract_suffix(name, VOICE_PREFIX)
                if suffix is not None:
                    voice_blobs[suffix] = blob
        
        # Find common suffixes
        common_suffixes = set(text_blobs.keys()) & set(voice_blobs.keys())
        if not common_suffixes:
            return None
        
        # Sort suffixes by creation time (oldest first)
        sorted_suffixes = sorted(
            common_suffixes,
            key=lambda s: min(
                text_blobs[s].time_created,
                voice_blobs[s].time_created
            )
        )
        
        # Get up to 2 oldest pairs
        result = []
        for suffix in sorted_suffixes[:2]:
            text_blob = text_blobs[suffix]
            voice_blob = voice_blobs[suffix]
            
            result.append({
                'text_url': f"gs://{bucket_name}/{text_blob.name}",
                'voice_url': f"gs://{bucket_name}/{voice_blob.name}",
                'suffix': suffix
            })
        
        return result if result else None
        
    except Exception as e:
        print(f"An error occurred while fetching available blobs: {e}")
        return None

def get_oldest_training_data(bucket_name: str, hash_identifier: str) -> Optional[dict]:
    """
    Retrieves the oldest training data (text and voice URL) for a given hash identifier.
    
    Args:
        bucket_name: The name of the Google Cloud Storage bucket.
        hash_identifier: The unique identifier for the data.
        
    Returns:
        A dictionary with 'text' and 'voice_url' if found, None otherwise.
    """
    try:
        # Get the oldest text content
        text_content = get_oldest_text_for_hash(bucket_name, hash_identifier)
        if not text_content:
            logger.warning(f"No text content found for hash: {hash_identifier}")
            return None
            
        # Get the oldest voice URL
        blob_pairs = get_oldest_blob_pairs(bucket_name, hash_identifier)
        if not blob_pairs or not blob_pairs[0].get('voice_url'):
            logger.warning(f"No voice URL found for hash: {hash_identifier}")
            return None
            
        return {
            'text': text_content,
            'voice_url': blob_pairs[0]['voice_url']
        }
        
    except Exception as e:
        logger.error(f"Error getting oldest training data: {e}")
        return None


def get_oldest_text_for_hash(bucket_name: str, hash_identifier: str) -> Optional[str]:
    """
    Retrieves the text content from the oldest text file for the given hash_identifier.
    
    Args:
        bucket_name: The name of the Google Cloud Storage bucket.
        hash_identifier: The unique identifier for the data.
        
    Returns:
        The text content as a string if found, None otherwise.
    """
    try:
        # Get the available blob URLs
        blob_pairs = get_oldest_blob_pairs(bucket_name, hash_identifier)
        if not blob_pairs:
            print(f"No text files found for hash: {hash_identifier}")
            return None
        
        # Get the most recent text URL (first in the list as they're sorted oldest to newest)
        text_url = blob_pairs[0]['text_url']
        
        # Extract the blob path from the URL (remove gs://bucket_name/)
        blob_path = text_url.replace(f"gs://{bucket_name}/", "")
        
        # Initialize GCS client and get the blob
        storage_client = storage.Client()
        blob = storage_client.bucket(bucket_name).blob(blob_path)
        
        # Download and return the text content
        return blob.download_as_text()
        
    except Exception as e:
        print(f"An error occurred while fetching text content: {e}")
        return None


def download_data_from_gcs(bucket_name: str, hash_identifier: str, random_num: Optional[int] = None) -> Tuple[Optional[str], Optional[str], Optional[bytes], Optional[str]]:
    """
    Downloads text and voice data from GCS for the given hash identifier.

    Args:
        bucket_name: The name of the Google Cloud Storage bucket.
        hash_identifier: The unique identifier for the data.
        random_num: Optional random number to look for specific files.

    Returns:
        A tuple containing (text_data, text_blob_name, voice_data_bytes, voice_blob_name).
        Returns (None, None, None, None) if download or decoding fails.
    """
    try:
        # Initialize GCS client and get bucket
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        
        # List all blobs with the hash_identifier prefix
        prefix = f"{hash_identifier}/"
        blobs = _get_matching_blobs(bucket, prefix)
        
        if not blobs:
            print(f"No files found for hash: {hash_identifier}")
            return None, None, None, None
        
        # Find matching text and voice blobs
        text_blob, voice_blob = _find_matching_pair(blobs, random_num)
        
        if not text_blob or not voice_blob:
            print(f"Could not find matching text and voice files for hash: {hash_identifier}")
            return None, None, None, None
        
        # Download text data
        text_data = text_blob.download_as_text()
        
        # Download and decode voice data
        encoded_voice_data = voice_blob.download_as_text()
        voice_data_bytes = base64.b64decode(encoded_voice_data)
        
        print(f"Successfully downloaded data for hash: {hash_identifier}")
        return text_data, text_blob.name, voice_data_bytes, voice_blob.name
        
    except Exception as e:
        print(f"An error occurred during GCS download: {e}")
        return None, None, None, None


def reconstruct_gcs_object_url(
    bucket_name: str,
    hash_identifier: str,
    is_voice: bool = False,
    random_num: Optional[int] = None,
    filename: Optional[str] = None
) -> str:
    """
    Reconstructs the GCS public URL for a text or voice file.
    
    Args:
        bucket_name: Name of the GCS bucket.
        hash_identifier: Unique identifier for the data.
        is_voice: If True, returns URL for voice file; otherwise for text file.
        random_num: Optional random number to include in the filename.
        filename: Optional custom filename (without path). If provided, overrides default naming.
    
    Returns:
        The public URL of the file.
    """
    if filename:
        # If custom filename is provided, use it directly
        blob_name = f"{hash_identifier}/{filename}"
    else:
        # Fall back to default naming
        if random_num is None:
            random_num = _get_random_number()
        
        prefix = VOICE_PREFIX if is_voice else TEXT_PREFIX
        extension = BINARY_EXTENSION if is_voice else TEXT_EXTENSION
        blob_name = f"{hash_identifier}/{prefix}{random_num}{extension}"
    
    return f"https://storage.googleapis.com/{bucket_name}/{blob_name}"

def list_all_hash_identifiers(bucket_name: str) -> List[str]:
    """
    Lists all unique hash identifiers (folders) in the specified GCS bucket.
    
    Args:
        bucket_name: The name of the Google Cloud Storage bucket.
        
    Returns:
        A list of unique hash identifiers (strings) found in the bucket.
        Returns an empty list if no hashes are found or if there's an error.
    """
    logger.info(f"Listing all hash identifiers in bucket: {bucket_name}")
    try:
        storage_client = storage.Client()
        blobs = storage_client.list_blobs(bucket_name, delimiter='/')
        
        # Extract unique prefixes (hash identifiers)
        hash_identifiers = set()
        for page in blobs.pages:
            for prefix in page.prefixes:
                # Remove the trailing '/' from the prefix
                hash_id = prefix.rstrip('/')
                if hash_id:  # Skip empty prefixes
                    hash_identifiers.add(hash_id)
        
        logger.info(f"Found {len(hash_identifiers)} unique hash identifiers")
        return sorted(list(hash_identifiers))
        
    except Exception as e:
        logger.error(f"Error listing hash identifiers: {str(e)}")
        return []

# --- Example Usage ---
if __name__ == "__main__":
    GCS_BUCKET_NAME = os.environ.get("EUPHONIA_DIA_GCS_BUCKET")
    if not GCS_BUCKET_NAME:
        GCS_BUCKET_NAME = "euphonia-dia"
        print(f"Warning: Using default bucket name '{GCS_BUCKET_NAME}'. "
              "Set EUPHONIA_DIA_GCS_BUCKET environment variable for production.")

    sample_hash_id = "sample_audio_hash_001_v6_dl_test"
    sample_text_content_upload = "This is a test transcript for upload and download, version 3."
    sample_voice_binary_data_upload = b'\x11\x22\x33\x44\x55\x66\x77\x88' * 15 
    #test_random_num = _get_random_number()

    print(f"\n--- Attempting to UPLOAD data ---")
    print(f"Hash: {sample_hash_id}, Bucket: {GCS_BUCKET_NAME}, Random: {None}")
    
    text_url, voice_url = upload_or_update_data_gcs(
        bucket_name=GCS_BUCKET_NAME,
        hash_identifier=sample_hash_id,
        text_data=sample_text_content_upload,
        voice_data_bytes=sample_voice_binary_data_upload,
    )

    if text_url and voice_url:
        print(f"\n--- Upload Successful ---")
        print(f"Text URL: {text_url}")
        print(f"Voice URL: {voice_url}")

        # Test URL reconstruction
        reconstructed_text_url = reconstruct_gcs_object_url(
            GCS_BUCKET_NAME, sample_hash_id, is_voice=False)
        reconstructed_voice_url = reconstruct_gcs_object_url(
            GCS_BUCKET_NAME, sample_hash_id, is_voice=True)
            
        print(f"\nReconstructed Text URL:   {reconstructed_text_url}")
        print(f"Reconstructed Voice URL: {reconstructed_voice_url}")
        
        print(f"\n--- Attempting to DOWNLOAD ---")
        retrieved_text, text_blob_name, retrieved_voice_bytes, voice_blob_name = download_data_from_gcs(
            GCS_BUCKET_NAME, sample_hash_id)
        
        if retrieved_text and retrieved_voice_bytes and text_blob_name and voice_blob_name:
            print("\n--- Download Successful ---")
            print(f"Retrieved Text: '{retrieved_text}'")
            
            # Verification
            if retrieved_text == sample_text_content_upload:
                print("SUCCESS: Retrieved text matches uploaded text.")
            else:
                print("ERROR: Retrieved text DOES NOT match uploaded text.")
            
            if retrieved_voice_bytes == sample_voice_binary_data_upload:
                print("SUCCESS: Retrieved voice data matches uploaded voice data.")
            else:
                print("ERROR: Retrieved voice data DOES NOT match uploaded voice data.")
        
        # Test get_oldest_blob_pairs
        print("\n--- Testing get_oldest_blob_pairs ---")
        available_blobs = get_oldest_blob_pairs(GCS_BUCKET_NAME, sample_hash_id)
        if available_blobs:
            print("\nAvailable blob pairs:")
            for i, pair in enumerate(available_blobs, 1):
                print(f"\nPair {i} (suffix: {pair['suffix']}):")
                print(f"  Text URL:  {pair['text_url']}")
                print(f"  Voice URL: {pair['voice_url']}")
                
            print("\n--- Testing get_oldest_text_for_hash ---")
            text_content = get_oldest_text_for_hash(GCS_BUCKET_NAME, sample_hash_id)
            if text_content:
                print("\nRetrieved text content:")
                print(f"{text_content}")
            else:
                print("Failed to retrieve text content")
        else:
            print("No matching blob pairs found.")
                
    else:
        print("\n--- Upload Failed ---")
        print(f"Please check your GCS setup, bucket name ('{GCS_BUCKET_NAME}'), and credentials.")
