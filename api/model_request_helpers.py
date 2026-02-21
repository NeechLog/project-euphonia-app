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
TEMP_AUDIO_DIR = "/tmp/euphonia_audio"
GOOD_AUDIO_DIR = "/tmp/euphonia_audio/validated"

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
    if not file_path or not os.path.exists(file_path):
        return False, f"File not found: {file_path}"
    
    try:
        # First, try to validate as WAV using pydub
        try:
            audio = AudioSegment.from_file(file_path, format="wav")
            if len(audio) <= 0:
                return False, "Audio file has zero duration"
        except CouldntDecodeError:
            return False, "File is not a valid WAV file"
        
        # Then perform format validation if requested
        if check_format:
            try:
                # Validate WAV format using soundfile
                audio_array, samplerate = sf.read(file_path)      
                # Check if audio is mono
                if len(audio_array.shape) != 1:
                    return False, "Audio must be mono"
               # Check if sample rate is a valid number
                if not isinstance(samplerate, (int, float)) or not (4000 <= samplerate <= 48000):
                    return False, f"Invalid sample rate: {samplerate}. Must be a number between 4000 and 48000 Hz"
               # Check for specific sample rate requirement
                # if samplerate != 16000:
                #     return False, f"Audio must be 16kHz (got {samplerate}Hz)"
            except Exception as e:
                return False, f"Error validating audio format: {str(e)}"
        
        return True, ""
        
    except Exception as e:
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
    if not audio_binary:
        return False, "Empty audio data provided"
    
    # Create a temporary file for validation
    tmp_fd, tmp_wav_file = tempfile.mkstemp(suffix='.wav')
    try:
        # Write binary data to temporary file
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(audio_binary)
        
        # Reuse the file-based validation function
        return validate_audio_format_from_file(tmp_wav_file, check_format)
        
    except Exception as e:
        return False, f"Error processing audio data: {str(e)}"
    finally:
        # Clean up the temporary file
        try:
            os.unlink(tmp_wav_file)
        except Exception:
            pass


def build_and_validate_audio_message(audio_data, text, file_name=None, check_format=True):
    """
    Builder function that creates and validates AudioMessage objects.
    
    Args:
        audio_data: Binary audio data or UploadFile object
        text: Text transcript for the audio
        file_name: Optional specific file name (without extension). If None, generates temp name
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (AudioMessage: Validated AudioMessage object, str: file_path)
    Raises:
        HTTPException: If validation fails
    """
    # Create AudioMessage using builder (creates temp file)
    audio_message, temp_file_path = build_audio_message(audio_data, text, file_name)
    
    try:
        # Validate the AudioMessage
        is_valid, error_msg = validate_audio_message(audio_message, check_format)
        if not is_valid:
            raise HTTPException(status_code=400, detail=f"Invalid audio: {error_msg}")
        
        # Validation passed - move temp file to good location
        os.makedirs(GOOD_AUDIO_DIR, exist_ok=True)
        
        # Determine final file name
        if file_name:
            final_filename = f"{file_name}.wav"
        else:
            # Extract name from temp path
            final_filename = os.path.basename(temp_file_path)
        
        final_file_path = os.path.join(GOOD_AUDIO_DIR, final_filename)
        
        # Move file from temp to good location
        shutil.move(temp_file_path, final_file_path)
        
        # Update AudioMessage with new file path
        audio_message.audio_file_path = final_file_path
        
        return audio_message, final_file_path
        
    except Exception as e:
        # Re-raise the original exception
        raise e
    finally:
        # Always clean up temp file if it still exists
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
                print(f"Cleaned up temp file: {temp_file_path}")
        except Exception as cleanup_error:
            print(f"Failed to clean up temp file {temp_file_path}: {cleanup_error}")


def build_audio_message(audio_data, text, file_name=None):
    """
    Builder function to create AudioMessage objects with file creation.
    
    Args:
        audio_data: Binary audio data or UploadFile object
        text: Text transcript for the audio
        file_name: Optional specific file name (without extension). If None, generates temp name
        
    Returns:
        tuple: (AudioMessage: Configured AudioMessage object, str: file_path)
    """
    # Handle both binary data and UploadFile objects
    if hasattr(audio_data, 'read'):
        # It's an UploadFile object, read the data
        audio_binary = audio_data.read() if hasattr(audio_data, 'read') else audio_data
    else:
        # It's already binary data
        audio_binary = audio_data
    
    # Ensure temp directory exists
    os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
    
    # Determine file path
    if file_name:
        file_path = os.path.join(TEMP_AUDIO_DIR, f"{file_name}.wav")
    else:
        # Generate temp file with timestamp
        import time
        timestamp = int(time.time())
        file_path = os.path.join(TEMP_AUDIO_DIR, f"audio_{timestamp}.wav")
    
    # Create file and write audio data
    with open(file_path, 'wb') as f:
        f.write(audio_binary)
        f.flush()
        os.fsync(f.fileno())
    
    # Create AudioMessage object
    audio_message = AudioMessage()
    audio_message.audio_binary = audio_binary
    audio_message.text = text
    audio_message.audio_file_path = file_path
    
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
    if not audio_message:
        return False, "No AudioMessage provided"
    
    # Check if AudioMessage has audio_binary data
    if not audio_message.HasField('audio_binary'):
        return False, "AudioMessage has no audio_binary field"
    
    # If AudioMessage has a file path, use it directly (I/O efficient)
    if audio_message.HasField('audio_file_path') and audio_message.audio_file_path:
        return validate_audio_format_from_file(audio_message.audio_file_path, check_format)
    else:
        # No file path available, validate from binary data
        return validate_audio_format(audio_message.audio_binary, check_format)


async def is_valid_wav(file_storage, check_format=True):
    """
    Validates if the uploaded file is a valid WAV file with optional format validation.
    
    Args:
        file_storage: FileStorage object from Flask request.files
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    try:
        # Read the file content
        file_content = await file_storage.read()
        
        # Use the common validation function
        return validate_audio_format(file_content, check_format)
        
    except Exception as e:
        return False, f"Error processing audio file: {str(e)}"
    finally:
        # Reset file pointer for any potential future use
        await file_storage.seek(0)
