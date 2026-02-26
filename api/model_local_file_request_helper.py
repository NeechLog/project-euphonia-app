import os
import tempfile
import soundfile as sf
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
import shutil
import logging
from fastapi import HTTPException
from audiomessages import AudioMessage

# Constants for audio file storage
TEMP_AUDIO_DIR = os.getenv('TEMP_AUDIO_DIR', '/tmp/euphonia_audio')
GOOD_AUDIO_DIR = os.getenv('GOOD_AUDIO_DIR', '/tmp/euphonia_audio/validated')

logger = logging.getLogger(__name__)


def validate_audio_format_from_file(file_path, check_format=True):
    """
    Validates audio format from an existing file path.
    
    Args:
        file_path: Path to the audio file
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    logger.debug(f"Validating audio file: {file_path}, check_format: {check_format}")
    
    if not file_path or not os.path.exists(file_path):
        logger.debug(f"File not found: {file_path}")
        return False, f"File not found: {file_path}"
    
    try:
        # First, try to validate as WAV using pydub
        try:
            logger.debug(f"Attempting to load WAV file with pydub: {file_path}")
            audio = AudioSegment.from_file(file_path, format="wav")
            if len(audio) <= 0:
                logger.debug("Audio file has zero duration")
                return False, "Audio file has zero duration"
            logger.debug(f"Successfully loaded audio with pydub, duration: {len(audio)}ms")
        except CouldntDecodeError as e:
            logger.debug(f"Failed to decode WAV file with pydub: {e}")
            return False, "File is not a valid WAV file"
        
        # Then perform format validation if requested
        if check_format:
            try:
                # Validate WAV format using soundfile
                logger.debug(f"Validating audio format with soundfile: {file_path}")
                audio_array, samplerate = sf.read(file_path)
                logger.debug(f"Audio shape: {audio_array.shape}, sample rate: {samplerate}")
                
                # Check if audio is mono
                if len(audio_array.shape) != 1:
                    logger.debug(f"Audio is not mono, shape: {audio_array.shape}")
                    return False, "Audio must be mono"
               # Check if sample rate is a valid number
                if not isinstance(samplerate, (int, float)) or not (4000 <= samplerate <= 48000):
                    logger.debug(f"Invalid sample rate: {samplerate}")
                    return False, f"Invalid sample rate: {samplerate}. Must be a number between 4000 and 48000 Hz"
               # Check for specific sample rate requirement
                # if samplerate != 16000:
                #     return False, f"Audio must be 16kHz (got {samplerate}Hz)"
                
                logger.debug("Audio format validation passed")
            except Exception as e:
                logger.debug(f"Error validating audio format: {e}")
                return False, f"Error validating audio format: {str(e)}"
        
        logger.debug(f"Audio validation successful for: {file_path}")
        return True, ""
        
    except Exception as e:
        logger.debug(f"Error processing audio file {file_path}: {e}")
        return False, f"Error processing audio file: {str(e)}"


def validate_audio_format(audio_binary, check_format=True):
    """
    Validates audio format from binary data.
    
    Args:
        audio_binary: Binary audio data
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    logger.debug(f"Validating audio binary data, size: {len(audio_binary) if audio_binary else 0} bytes, check_format: {check_format}")
    
    if not audio_binary:
        logger.debug("Empty audio data provided")
        return False, "Empty audio data provided"
    
    # Create a temporary file for validation
    tmp_fd, tmp_wav_file = tempfile.mkstemp(suffix='.wav')
    logger.debug(f"Created temporary file for validation: {tmp_wav_file}")
    
    try:
        # Write binary data to temporary file
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(audio_binary)
        
        # Reuse the file-based validation function
        return validate_audio_format_from_file(tmp_wav_file, check_format)
        
    except Exception as e:
        logger.debug(f"Error processing audio data: {e}")
        return False, f"Error processing audio data: {str(e)}"
    finally:
        # Clean up the temporary file
        try:
            os.unlink(tmp_wav_file)
            logger.debug(f"Cleaned up temporary validation file: {tmp_wav_file}")
        except Exception:
            pass


def build_and_validate_audio_message(audio_data, text, file_name=None, check_format=True, locale=None):
    """
    Builder function that creates and validates AudioMessage objects.
    
    Args:
        audio_data: Binary audio data or UploadFile object
        text: Text transcript for the audio
        file_name: Optional specific file name (without extension). If None, generates temp name
        check_format: If True, validates audio format (mono, 16kHz)
        locale: Optional locale string for the audio message
        
    Returns:
        tuple: (AudioMessage: Validated AudioMessage object, str: file_path)
    Raises:
        HTTPException: If validation fails
    """
    logger.debug(f"Building and validating audio message - file_name: {file_name}, check_format: {check_format}, locale: {locale}")
    
    # Handle case where no audio data is provided
    if audio_data is None and text is None and file_name is None:
        logger.debug("No audio data, text, or file_name provided")
        raise HTTPException(status_code=400, detail="Audio data or text or file_name must be provided")
    
    temp_file_path = None
    audio_message, temp_file_path = build_raw_audio_message(audio_data, text, file_name)
    logger.debug(f"Built raw audio message, temp_file_path: {temp_file_path}")
        
    # Set locale if provided
    if locale:
        audio_message.locale = locale
        logger.debug(f"Set locale: {locale}")
    
    try:
        # Validate the AudioMessage
        logger.debug("Validating audio message")
        is_valid, error_msg = validate_audio_message(audio_message, check_format)
        if not is_valid:
            logger.debug(f"Audio validation failed: {error_msg}")
            raise HTTPException(status_code=400, detail=f"Invalid audio: {error_msg}")
        
        logger.debug("Audio validation successful")
        
        # Validation passed - move temp file to good location only if temp file exists
        os.makedirs(GOOD_AUDIO_DIR, exist_ok=True)
        logger.debug(f"Ensured good audio directory exists: {GOOD_AUDIO_DIR}")
        
        # Only move file if we actually created a temp file and it's in TEMP_AUDIO_DIR
        if (temp_file_path and 
            os.path.exists(temp_file_path) and 
            temp_file_path.startswith(TEMP_AUDIO_DIR)):
            logger.debug(f"Moving temp file to good location: {temp_file_path}")
            
            # Determine final file name
            if file_name:
                final_filename = f"{file_name}.wav"
            else:
                # Extract name from temp path
                final_filename = os.path.basename(temp_file_path)
            
            final_file_path = os.path.join(GOOD_AUDIO_DIR, final_filename)
            logger.debug(f"Final file path will be: {final_file_path}")
            
            # Move file from temp to good location
            shutil.move(temp_file_path, final_file_path)
            logger.debug(f"Successfully moved file to: {final_file_path}")
            
            # Update AudioMessage with new file path
            audio_message.audio_file_path = final_file_path
            return audio_message, final_file_path
        else:
            # No file was moved, return None for file_path
            logger.debug("No file movement required - either no temp file, file doesn't exist, or not in temp dir")
            return audio_message, None
        
    except Exception as e:
        # Re-raise the original exception
        logger.debug(f"Exception in build_and_validate_audio_message: {e}")
        raise e
    finally:
        # Always clean up temp file if it still exists
        try:
            if temp_file_path and os.path.exists(temp_file_path) and temp_file_path.startswith(TEMP_AUDIO_DIR):
                os.unlink(temp_file_path)
                logger.debug(f"Cleaned up temp file: {temp_file_path}")
        except Exception as cleanup_error:
            logger.error(f"Failed to clean up temp file {temp_file_path}: {cleanup_error}")


def write_temp_file(audio_binary, file_path):
    """
    Write audio binary data to a temporary file.
    
    Args:
        audio_binary: Binary audio data to write
        file_path: Path where to write the file
        
    Returns:
        None
    """
    logger.debug(f"Writing {len(audio_binary)} bytes to temporary file: {file_path}")
    with open(file_path, 'wb') as f:
        f.write(audio_binary)
        f.flush()
        os.fsync(f.fileno())
    logger.debug(f"Successfully wrote temporary file: {file_path}")


def build_raw_audio_message(audio_data, text, file_name=None):
    """
    Builder function to create AudioMessage objects with file creation.
    
    Args:
        audio_data: Binary audio data or UploadFile object
        text: Text transcript for the audio
        file_name: Optional specific file name (without extension). If None, generates temp name
        
    Returns:
        tuple: (AudioMessage: Configured AudioMessage object, str: file_path)
    """
    logger.debug(f"Building raw audio message - file_name: {file_name}, has_text: {bool(text)}")
    
    # Handle case where no audio data is provided
    if audio_data is None:
        audio_binary = None
        logger.debug("No audio data provided")
    else:
        # Handle UploadFile objects, file paths, and binary data
        if hasattr(audio_data, 'read'):
            # It's an UploadFile object, read the data
            logger.debug("Reading audio data from UploadFile object")
            audio_binary = audio_data.read()
        elif isinstance(audio_data, str):
            # It's a file path string, handle file:// prefix
            if audio_data.startswith('file://'):
                file_path = audio_data[7:]  # Remove 'file://' prefix
            else:
                file_path = audio_data
            logger.debug(f"Reading audio data from file path: {file_path}")
            with open(file_path, 'rb') as f:
                audio_binary = f.read()
            file_name = file_path ## override the parameter since it is actual file. 
        else:
            # It's already binary data (bytes)
            audio_binary = audio_data
            logger.debug(f"Using provided binary audio data, size: {len(audio_binary)} bytes")
    
    # Ensure temp directory exists
    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
    logger.debug(f"Ensured temp directory exists: {TEMP_AUDIO_DIR}")
    
    # Determine file path
    if file_name:
        # Check if file_name is an absolute path or URL
        if (os.path.isabs(file_name) or 
            file_name.startswith(('http://', 'https://', 'ftp://', 'file://'))):
            # Use the file_name as-is for absolute paths and URLs
            file_path = file_name
            logger.debug(f"Using absolute path/URL as file path: {file_path}")
        else:
            # Create path in temp directory for relative file names
            file_path = os.path.join(TEMP_AUDIO_DIR, f"{file_name}.wav")
            logger.debug(f"Using relative file name, temp path: {file_path}")
            # Only write file if we have audio data
            if audio_binary is not None:
                write_temp_file(audio_binary, file_path)
    else:
        file_path = None
        if audio_binary is not None:
            # Generate temp file with timestamp
            import time
            timestamp = int(time.time())
            file_path = os.path.join(TEMP_AUDIO_DIR, f"audio_{timestamp}.wav")
            logger.debug(f"Generated temp file path with timestamp: {file_path}")
            # Only write file if we have audio data
            write_temp_file(audio_binary, file_path)
    
    # Create AudioMessage object
    audio_message = AudioMessage()
    if(audio_binary):
        audio_message.audio_binary = audio_binary
        logger.debug(f"Set audio_binary on AudioMessage, size: {len(audio_binary)} bytes")
    if(text):
        audio_message.text = text
        logger.debug(f"Set text on AudioMessage: {text[:50]}{'...' if len(text) > 50 else ''}")
    if(file_path):
        audio_message.audio_file_path = file_path
        logger.debug(f"Set audio_file_path on AudioMessage: {file_path}")
    
    logger.debug(f"Created AudioMessage with binary: {bool(audio_binary)}, text: {bool(text)}, file_path: {bool(file_path)}")
    return audio_message, file_path


def validate_audio_message(audio_message, check_format=True):
    """
    Validates an AudioMessage object.
    
    Args:
        audio_message: AudioMessage protobuf object
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    logger.debug(f"Validating AudioMessage, check_format: {check_format}")
    
    if not audio_message:
        logger.debug("No AudioMessage provided")
        return False, "No AudioMessage provided"
    
    # Check if AudioMessage has audio_binary data first (primary validation)
    has_binary = audio_message.HasField('audio_binary')
    has_file_path = audio_message.HasField('audio_file_path')
    logger.debug(f"AudioMessage has binary: {has_binary}, has file_path: {has_file_path}")
    
    if not has_binary and not has_file_path:
        logger.debug("AudioMessage has no audio_binary or file_path, only text - considered valid")
        return True, "AudioMessage has no audio_binary field, or file path, only text and it is a valid message"
    
    # If AudioMessage has a file path, use it directly (I/O efficient)
    if has_file_path and audio_message.audio_file_path:
        logger.debug(f"Validating audio from file path: {audio_message.audio_file_path}")
        return validate_audio_format_from_file(audio_message.audio_file_path, check_format)
    
    # If AudioMessage has audio_binary data, validate from binary (preferred for efficiency)
    if has_binary:
        logger.debug("Validating audio from binary data")
        return validate_audio_format(audio_message.audio_binary, check_format)
    
    # No file path available, this should not happen if binary check passed
    logger.debug("No audio data available for validation")
    return False, "Unable to validate audio: no binary data or file path available"


async def is_valid_wav(file_storage, check_format=True):
    """
    Validates if the uploaded file is a valid WAV file with optional format validation.
    
    Args:
        file_storage: FileStorage object from Flask request.files
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    logger.debug(f"Validating uploaded WAV file, check_format: {check_format}")
    
    try:
        # Read the file content
        logger.debug("Reading file content from FileStorage object")
        file_content = await file_storage.read()
        logger.debug(f"Read {len(file_content)} bytes from file")
        
        # Use the common validation function
        return validate_audio_format(file_content, check_format)
        
    except Exception as e:
        logger.debug(f"Error processing uploaded WAV file: {e}")
        return False, f"Error processing audio file: {str(e)}"
    finally:
        # Reset file pointer for any potential future use
        try:
            await file_storage.seek(0)
            logger.debug("Reset file pointer to beginning")
        except Exception as seek_error:
            logger.debug(f"Failed to reset file pointer: {seek_error}")
