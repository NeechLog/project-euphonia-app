import base64
import logging
import os
import random
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# File extensions and type identifiers
TEXT_EXTENSION = '.txt'
BINARY_EXTENSION = '.wav'
TEXT_PREFIX = 'text_'
VOICE_PREFIX = 'voice_'
TEXT_CONTENT_TYPE = 'text/plain'
BINARY_CONTENT_TYPE = 'application/octet-stream'
DATA_DIR = os.environ.get('DATA_DIR', os.path.join(os.getcwd(), 'euphonia-dia'))

def _get_matching_files(directory: str, prefix: str) -> List[str]:
    """Get all files with the given prefix in the directory."""
    logger.debug(f"Fetching files with prefix: {prefix} from directory: {directory}")
    if not os.path.exists(directory):
        return []
    files = [f for f in os.listdir(directory) if f.startswith(prefix)]
    logger.debug(f"Found {len(files)} files with prefix: {prefix}")
    return files

def _get_random_number() -> int:
    """Generate a random 6-digit number."""
    num = random.randint(100000, 999999)
    logger.debug(f"Generated random number: {num}")
    return num

def _write_file(directory: str, file_name: str, data: str | byte, content_type: str) -> str:
    """Helper function to write data to a file."""
    logger.debug(f"Writing to file: {file_name} with content type: {content_type}")
    try:
        # Create directory if it doesn't exist
        os.makedirs(directory, exist_ok=True)
        
        # Write the file
        file_path = os.path.join(directory, file_name)
        mode = 'w' if content_type.startswith('text/') else 'wb'
        
        with open(file_path, mode) as f:
            f.write(data)
            
        logger.info(f"Successfully wrote to {file_path}")
        return f"file://{os.path.abspath(file_path)}"
    except Exception as e:
        logger.error(f"Failed to write file {file_name}. Error: {str(e)}")
        raise

def _construct_filename(prefix: str, custom_name: Optional[str], suffix: str, default_extension: str) -> Tuple[str, str]:
    """Construct a filename with proper prefix and suffix handling."""
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

def _resolve_data_dir(base_dir: str) -> str:
    """
    Resolve the base directory path, handling relative paths with DATA_DIR environment variable.
    
    Args:
        base_dir: The base directory path (can be relative or absolute)
        
    Returns:
        str: The resolved absolute path
    """
    if not os.path.isabs(base_dir):
        base_dir = os.path.join(DATA_DIR, base_dir)
    return base_dir


def upload_or_update_data_local(
    base_dir: str,
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
    Uploads or updates text and voice data in local storage as separate files.

    The objects will be stored as:
    - Text: '{base_dir}/{hash_identifier}/text_<suffix>.<ext>' or custom filename if provided
    - Voice: '{base_dir}/{hash_identifier}/voice_<suffix>.<ext>' or custom filename if provided

    If base_dir is not an absolute path, it will be treated as relative to the DATA_DIR environment variable.
    If DATA_DIR is not set, it will use the current working directory.

    Args:
        base_dir: The base directory for storage. Can be relative or absolute path.
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
        
        # Resolve base directory
        base_dir = _resolve_data_dir(base_dir)
        
        # Create the directory if it doesn't exist
        os.makedirs(base_dir, exist_ok=True)
        
        # Create the directory for this hash_identifier
        target_dir = os.path.join(base_dir, hash_identifier)
        
        # Check if any files exist in the hash_identifier directory
        logger.debug(f"Checking for existing files in directory: {target_dir}")
        existing_files = []
        if os.path.exists(target_dir):
            existing_files = os.listdir(target_dir)
        
        # If no files exist and no random number provided, use 0 as suffix
        if not existing_files and random_num is None:
            suffix = "0"
            logger.debug("No existing files found and no random number provided, using suffix: 0")
        else:
            # Use provided random number or generate a new one
            suffix = str(random_num) if random_num is not None else str(_get_random_number())
            logger.debug(f"Using suffix: {suffix} (random_num: {random_num})")

        # Generate text filename
        text_filename, text_extension = _construct_filename(
            TEXT_PREFIX, text_filename, suffix, TEXT_EXTENSION
        )
        text_content_type = text_content_type or TEXT_CONTENT_TYPE

        # Generate audio filename
        audio_filename, audio_extension = _construct_filename(
            VOICE_PREFIX, audio_filename, suffix, BINARY_EXTENSION
        )
        audio_content_type = audio_content_type or BINARY_CONTENT_TYPE

        # Write text data
        logger.info(f"Writing text data to {text_filename}")
        text_url = _write_file(target_dir, text_filename, text_data, text_content_type)
        logger.info(f"Successfully wrote text data to {text_url}")

        # Write voice data
        logger.info(f"Writing voice data to {audio_filename}")
        voice_url = _write_file(target_dir, audio_filename, voice_data_bytes, audio_content_type)
        logger.info(f"Successfully wrote voice data to {voice_url}")

        logger.info(f"Successfully wrote text and voice data with suffix: {suffix}")
        return text_url, voice_url

    except Exception as e:
        logger.exception("An error occurred during local storage write")
        return None, None

def _extract_suffix(file_name: str, prefix: str) -> Optional[str]:
    """Extract the suffix from a file name based on the expected pattern."""
    logger.debug(f"Extracting suffix from file: {file_name} with prefix: {prefix}")
    base_name = os.path.basename(file_name)
    
    # Check for pattern: {prefix}{suffix}.ext
    if base_name.startswith(prefix):
        suffix = base_name[len(prefix):].split('.')[0]
        if suffix.isdigit():
            return suffix
    
    # Check for pattern: {base_name}_{prefix}{suffix}.ext
    parts = base_name.split('_' + prefix, 1)
    if len(parts) == 2 and parts[1].split('.')[0].isdigit():
        return parts[1].split('.')[0]
    
    return None

def _find_matching_pair(directory: str, random_num: Optional[int] = None) -> List[Dict[str, str]]:
    """Find matching text and voice files with the same random number."""
    if not os.path.exists(directory):
        return []
        
    files = os.listdir(directory)
    text_files = [f for f in files if f.startswith(TEXT_PREFIX) or f.endswith('_' + TEXT_PREFIX)]
    voice_files = [f for f in files if f.startswith(VOICE_PREFIX) or f.endswith('_' + VOICE_PREFIX)]
    
    # Group files by their suffix
    suffix_map = {}
    
    for file in text_files + voice_files:
        prefix = TEXT_PREFIX if file in text_files else VOICE_PREFIX
        suffix = _extract_suffix(file, prefix)
        
        if suffix is None:
            continue
            
        if suffix not in suffix_map:
            suffix_map[suffix] = {'text': None, 'voice': None}
            
        file_path = os.path.join(directory, file)
        if file in text_files:
            suffix_map[suffix]['text'] = file_path
        else:
            suffix_map[suffix]['voice'] = file_path
    
    # Filter for complete pairs
    pairs = []
    for suffix, files in suffix_map.items():
        if files['text'] and files['voice']:
            pairs.append({
                'text_url': f"file://{os.path.abspath(files['text'])}",
                'voice_url': f"file://{os.path.abspath(files['voice'])}",
                'suffix': suffix
            })
    
    # Filter by random_num if provided
    if random_num is not None:
        pairs = [p for p in pairs if p['suffix'] == str(random_num)]
    
    # Sort by modification time (oldest first)
    pairs.sort(key=lambda x: os.path.getmtime(x['text_url'].replace('file://', '')))
    
    return pairs

def get_oldest_blob_pairs(base_dir: str, hash_identifier: str) -> List[Dict[str, str]]:
    """
    Retrieves the oldest file pairs (text and voice) for a given hash identifier.
    
    Args:
        base_dir: The base directory for storage.
        hash_identifier: The unique identifier for the data.
        
    Returns:
        A list of up to 2 dictionaries, each containing 'text_url', 'voice_url' with file:// URLs,
        and 'suffix' for each pair. Returns an empty list if no matching file pairs are found.
    """
    try:
        # Resolve base directory
        base_dir = _resolve_data_dir(base_dir)
        target_dir = os.path.join(base_dir, hash_identifier)
        
        if not os.path.exists(target_dir):
            return []
            
        pairs = _find_matching_pair(target_dir)
        return pairs[:2]  # Return at most 2 oldest pairs
    except Exception as e:
        logger.error(f"Error getting oldest blob pairs: {str(e)}")
        return []

def get_oldest_training_data(base_dir: str, hash_identifier: str) -> Optional[Dict[str, str]]:
    """
    Retrieves the oldest training data (text and voice URL) for a given hash identifier.
    
    Args:
        base_dir: The base directory for storage.
        hash_identifier: The unique identifier for the data.
        
    Returns:
        A dictionary with 'text' and 'voice_url' if found, None otherwise.
    """
    try:
        pairs = get_oldest_blob_pairs(base_dir, hash_identifier)
        if not pairs:
            return None
            
        oldest_pair = pairs[0]
        
        # Read the text content
        text_path = oldest_pair['text_url'].replace('file://', '')
        with open(text_path, 'r') as f:
            text_content = f.read()
            
        return {
            'text': text_content,
            'voice_url': oldest_pair['voice_url']
        }
    except Exception as e:
        logger.error(f"Error getting oldest training data: {str(e)}")
        return None

def get_oldest_text_for_hash(base_dir: str, hash_identifier: str) -> Optional[str]:
    """
    Retrieves the text content from the oldest text file for the given hash_identifier.
    
    Args:
        base_dir: The base directory for storage.
        hash_identifier: The unique identifier for the data.
        
    Returns:
        The text content as a string if found, None otherwise.
    """
    try:
        target_dir = os.path.join(base_dir, hash_identifier)
        if not os.path.exists(target_dir):
            return None
            
        # Find all text files
        text_files = [f for f in os.listdir(target_dir) 
                     if f.startswith(TEXT_PREFIX) or f.endswith('_' + TEXT_PREFIX)]
        
        if not text_files:
            return None
            
        # Sort by modification time (oldest first)
        text_files.sort(key=lambda f: os.path.getmtime(os.path.join(target_dir, f)))
        
        # Read the oldest text file
        oldest_text_file = os.path.join(target_dir, text_files[0])
        with open(oldest_text_file, 'r') as f:
            return f.read()
            
    except Exception as e:
        logger.error(f"Error getting oldest text for hash: {str(e)}")
        return None

def download_data_from_local(
    base_dir: str,
    hash_identifier: str,
    random_num: Optional[int] = None
) -> Tuple[Optional[str], Optional[str], Optional[bytes], Optional[str]]:
    """
    Downloads text and voice data from local storage for the given hash identifier.

    If base_dir is not an absolute path, it will be treated as relative to the DATA_DIR environment variable.
    If DATA_DIR is not set, it will use the current working directory.

    Args:
        base_dir: The base directory for storage. Can be relative or absolute path.
        hash_identifier: The unique identifier for the data.
        random_num: Optional random number to look for specific files.

    Returns:
        A tuple containing (text_data, text_file_name, voice_data_bytes, voice_file_name).
        Returns (None, None, None, None) if download or reading fails.
    """
    try:
        # Resolve base directory
        base_dir = _resolve_data_dir(base_dir)
            
        target_dir = os.path.join(base_dir, hash_identifier)
        if not os.path.exists(target_dir):
            logger.warning(f"Target directory does not exist: {target_dir}")
            return None, None, None, None
            
        pairs = _find_matching_pair(target_dir, random_num)
        if not pairs:
            logger.warning(f"No matching file pairs found in {target_dir}")
            return None, None, None, None
            
        # Get the first matching pair
        pair = pairs[0]
        text_path = pair['text_url'].replace('file://', '')
        voice_path = pair['voice_url'].replace('file://', '')
        
        # Read text data
        with open(text_path, 'r', encoding='utf-8') as f:
            text_data = f.read()
            
        # Read voice data
        with open(voice_path, 'rb') as f:
            voice_data = f.read()
            
        return (
            text_data,
            os.path.basename(text_path),
            voice_data,
            os.path.basename(voice_path)
        )
        
    except Exception as e:
        logger.error(f"Error downloading data: {str(e)}")
        return None, None, None, None

def reconstruct_local_object_url(
    base_dir: str,
    hash_identifier: str,
    is_voice: bool = False,
    random_num: Optional[int] = None,
    filename: Optional[str] = None
) -> str:
    """
    Reconstructs the local file URL for a text or voice file.
    
    Args:
        base_dir: The base directory for storage.
        hash_identifier: Unique identifier for the data.
        is_voice: If True, returns URL for voice file; otherwise for text file.
        random_num: Optional random number to include in the filename.
        filename: Optional custom filename (without path). If provided, overrides default naming.
    
    Returns:
        The file:// URL of the file.
    """
    try:
        target_dir = os.path.join(base_dir, hash_identifier)
        
        if filename:
            file_path = os.path.join(target_dir, filename)
            return f"file://{os.path.abspath(file_path)}"
            
        prefix = VOICE_PREFIX if is_voice else TEXT_PREFIX
        extension = BINARY_EXTENSION if is_voice else TEXT_EXTENSION
        
        if random_num is not None:
            file_name = f"{prefix}{random_num}{extension}"
            file_path = os.path.join(target_dir, file_name)
            return f"file://{os.path.abspath(file_path)}"
            
        # If no random_num, find the first matching file
        files = os.listdir(target_dir) if os.path.exists(target_dir) else []
        for f in files:
            if ((is_voice and (f.startswith(VOICE_PREFIX) or f.endswith('_' + VOICE_PREFIX)) or
                 not is_voice and (f.startswith(TEXT_PREFIX) or f.endswith('_' + TEXT_PREFIX)))):
                file_path = os.path.join(target_dir, f)
                return f"file://{os.path.abspath(file_path)}"
                
        # If no file found, construct a default path
        suffix = _get_random_number()
        file_name = f"{prefix}{suffix}{extension}"
        file_path = os.path.join(target_dir, file_name)
        return f"file://{os.path.abspath(file_path)}"
        
    except Exception as e:
        logger.error(f"Error reconstructing local object URL: {str(e)}")
        return ""

def list_all_hash_identifiers(base_dir: str) -> List[str]:
    """
    Lists all unique hash identifiers (directories) in the specified base directory.
    
    Args:
        base_dir: The base directory to search for hash identifiers.
        
    Returns:
        A list of unique hash identifiers (strings) found in the directory.
        Returns an empty list if no hashes are found or if there's an error.
    """
    try:
        if not os.path.exists(base_dir):
            return []
            
        # Get all directories in the base directory
        hash_ids = [d for d in os.listdir(base_dir) 
                   if os.path.isdir(os.path.join(base_dir, d))]
                   
        return hash_ids
        
    except Exception as e:
        logger.error(f"Error listing hash identifiers: {str(e)}")
        return []

# --- Example Usage ---
if __name__ == "__main__":
    # Example usage
    BASE_DIR = "./local_storage"
    HASH_ID = "test_hash_123"
    
    # Create test data
    text_data = "This is a test text."
    voice_data = b"fake_audio_data" * 1000  # Simulated binary data
    
    # Upload data
    text_url, voice_url = upload_or_update_data_local(
        BASE_DIR, HASH_ID, text_data, voice_data
    )
    
    print(f"Text URL: {text_url}")
    print(f"Voice URL: {voice_url}")
    
    # Get oldest training data
    training_data = get_oldest_training_data(BASE_DIR, HASH_ID)
    if training_data:
        print(f"\nTraining data text: {training_data['text']}")
        print(f"Training data voice URL: {training_data['voice_url']}")
    
    # List all hash identifiers
    print("\nAll hash identifiers:")
    for hash_id in list_all_hash_identifiers(BASE_DIR):
        print(f"- {hash_id}")
