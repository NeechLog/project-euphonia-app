import logging
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import os
import tempfile
import soundfile as sf
from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError
from io import BytesIO
import numpy as np
import io
import subprocess
import ffmpeg
import sys
from pathlib import Path
import tempfile
import os

sys.path.append(os.path.join(os.path.dirname(__file__), 'local_adapter'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'gcloudAdapter'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'e2ecloudAdapter'))


# Default constants
DEFAULT_HASH_ID = "default_user_123"
DEFAULT_BUCKET = "/home/jovyan/voice_assist/prod/voice_sample" #"euphonia-dia"
STORAGE = "local" # or "gcs" or "e2ebucket"
TRANSCRIBE_MODEL = "local" # or "gcs" or "e2ebucket"

#TODO: Review and ensure a single place where temporary sound file is created, pass it's handle around everywhere. In case of sample - same thing 

if(TRANSCRIBE_MODEL == "local"):
    from local_adapter.local_model_parakeet import transcribe_voice as transcribe_voice
# Storage and voice
if(STORAGE == "gcs"):
    from gcloudAdapter.gcp_storage import upload_or_update_data_gcs as upload_or_update_data, get_oldest_training_data, list_all_hash_identifiers
elif(STORAGE=="e2ebucket"):
    from e2ecloudAdapter.e2e_storage import upload_or_update_data_gcs as upload_or_update_data, get_oldest_training_data, list_all_hash_identifiers
elif(STORAGE=="local"):
    from local_adapter.local_storage import upload_or_update_data_local as upload_or_update_data, get_oldest_training_data, list_all_hash_identifiers
CLOUD = "local"
if CLOUD == "gcs":
    from gcloudAdapter.gcp_models import synthesize_speech_with_cloned_voice, call_vertex_Dia_model as call_voice_model
elif CLOUD == "local":
    from local_adapter.local_model import synthesize_speech_with_cloned_voice, call_vertex_Dia_model as call_voice_model


# Configure logging from environment variable
log_level = os.getenv('PYTHON_LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()
logger.debug('Starting FastAPI server')
# Serve static files from the 'web' directory
import os
from pathlib import Path

# Get the absolute path to the web directory
web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
app.mount("/web", StaticFiles(directory=web_dir), name="web")
#model = Dia.from_pretrained("nari-labs/Dia-1.6B", compute_dtype="float16")


    # Ensure you have authenticated with GCP, e.g., via `gcloud auth application-default login`
    # or by setting the GOOGLE_APPLICATION_CREDENTIALS environment variable.
@app.post('/process_audio')
async def process_audio(audio: UploadFile = File(...), hashVoiceName: str = Form(DEFAULT_HASH_ID)):
    """
    Endpoint to receive an audio file and stream it back.
    Accepts a WAV file in the 'wav' form field.
    Returns the same audio as a stream.
    """
    logger.debug(f"Request details: audio filename: {audio.filename}, hashVoiceName: {hashVoiceName}")
    try:
        # Check if file part is present
        if audio.content_type != 'audio/wav':
            raise HTTPException(status_code=400, detail='Invalid file type, must be .wav')

        logger.info(f'Processing audio file: {audio.filename}')
        
        transcribe_result = "Basically default transcription result, this should never appear, unless audio check failed. did you hear any thing?"
        try:
            transcribe_result = await _transcribe_audio_file(audio)
        except HTTPException as he:
            logger.error(f"HTTP error during transcription: {str(he.detail)}")
            transcribe_result = f"Error during transcription: {he.detail}"
        except Exception as e:
            logger.error(f"Unexpected error during transcription: {str(e)}", exc_info=True)
            transcribe_result = "An unexpected error occurred during transcription. Please check logs"

        # Get the oldest training data for the default user
        bucket_name = DEFAULT_BUCKET if os.environ.get("EUPHONIA_DIA_GCS_BUCKET") is None else os.environ.get("EUPHONIA_DIA_GCS_BUCKET")
        # TODO: a case could be made to pick the latest cloned sample, after all why save them? but right now going with oldest. 
        # TODO: Also eventually the hash would be of current user and not default. That will need fix in train_audio as well.
        logger.info(f"Looking for text and voice sample for {hashVoiceName}")
        training_data = get_oldest_training_data(bucket_name, hashVoiceName)
        logger.debug(f"Found text and voice sample for {hashVoiceName}")
        # Initialize with default values
        voice_url = None
        oldest_text = ""
        voice_data = None
        if training_data:
            oldest_text = training_data['text']
            voice_url = training_data['voice_url']

        
        # Create a generator to stream the synthesized audio
        def generate():
            try:
                logger.info("Attempting to synthesize speech with cloned voice...")
                logger.debug(f"Using voice URL: {voice_url}")
                logger.debug(f"Using training text: {oldest_text[:100]}..." if oldest_text else "No training text provided")
                if(training_data):
                    # Call the synthesis function
                    voice_data = synthesize_speech_with_cloned_voice(
                        text_to_synthesize=transcribe_result,
                        clone_from_audio_gcs_url=voice_url,
                        clone_from_text_transcript=oldest_text
                    )
                else:
                    voice_data  = call_voice_model(
                        input_text=transcribe_result
                    )
                
                if voice_data:
                    logger.debug(f'Starting audio file streaming, size: {len(voice_data)} bytes')
                    yield voice_data
                else:
                    logger.warning("No voice data received from synthesis.")
                    yield b''
            except Exception as e:
                logger.error(f"Synthesis failed: {str(e)}", exc_info=True)
                yield b''
        
        # Create headers with the transcription result
        headers = {
            'X-Response-Text': str(transcribe_result),
            'Content-Disposition': f'attachment; filename=processed_{audio.filename}'
        }
        
        # Return the synthesized audio as a stream
        return StreamingResponse(
            generate(),
            media_type='audio/wav',
            headers=headers
        )
        
    except Exception as e:
        logger.error(f'Error processing audio: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


async def _transcribe_audio_file(audio_file):
    """Helper method to handle audio file transcription with temporary file management.
    
    Args:
        audio_file: The uploaded file object (FastAPI's UploadFile)
        
    Returns:
        str: The transcription result
        
    Raises:
        HTTPException: If the audio file is invalid or there's an error during transcription
    """
    # Validate the audio file first
    is_valid, error_msg = await is_valid_wav(audio_file, check_format=True)
    if not is_valid:
        logger.error(f"Invalid audio file: {error_msg}")
        raise HTTPException(status_code=400, detail=f"Invalid audio file: {error_msg}")
    
    # Reset file pointer after validation
    await audio_file.seek(0)
    
    # Create a temporary file with a .wav extension
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
        try:
            # Read the uploaded file content
            contents = await audio_file.read()
            
            # Write the content to the temporary file
            temp_audio.write(contents)
            
            # Ensure the file is written to disk
            temp_audio.flush()
            os.fsync(temp_audio.fileno())
            
            # Transcribe the audio file
            return transcribe_voice(temp_audio.name)
            
        finally:
            # Always clean up the temporary file
            try:
                os.unlink(temp_audio.name)
            except Exception as e:
                logger.warning(f"Could not delete temporary file {temp_audio.name}: {str(e)}")

@app.post('/transcribe')
async def transcribe(wav: UploadFile = File(...)):
    if(is_valid_wav(wav)):
        pred = await _transcribe_audio_file(wav)
    else:
        pred = "Invalid WAV file"

    return {'response': 'success!', 'transcript': pred}


@app.post('/gendia')
async def gendia(phrase: str = Form(...), sample_phrase: str = Form(None), sample_voice: UploadFile = File(None), hash_id: str = Form(DEFAULT_HASH_ID)):
    try:
        # Required parameter
        if not phrase:
            logger.error('No phrase provided in request')
            raise HTTPException(status_code=400, detail='No phrase provided')
        
        if sample_phrase:
            logger.info(f'Received sample phrase: {sample_phrase}')
       
        if sample_voice:
            logger.info(f'Received sample voice file: {sample_voice.filename}')
            is_valid, error_msg = is_valid_wav(sample_voice, check_format=True)
            if not is_valid:
               raise HTTPException(status_code=400, detail=f'Invalid WAV file: {error_msg}')
        
        training_data, error = prepare_training_data(
            phrase=phrase,
            sample_phrase=sample_phrase,
            sample_voice=sample_voice if sample_voice and sample_phrase else None,
            hash_id=hash_id
        )
        if error:
            raise HTTPException(status_code=400, detail=error)
        
        voice_data = synthesize_speech_with_cloned_voice(
                    text_to_synthesize=phrase,
                    clone_from_audio_gcs_url=training_data['voice_url'],
                    clone_from_text_transcript=training_data['text']
                )
        return StreamingResponse(BytesIO(voice_data), media_type='audio/wav')
    except Exception as e:
        logger.error(f'Error processing gendia request: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally :
        if '_temp_file' in training_data and os.path.exists(training_data['_temp_file']):
            try:
                os.unlink(training_data['_temp_file'])
                logger.info(f'Cleaned up temporary file: {training_data["_temp_file"]}')
            except Exception as e:
                logger.error(f'Error cleaning up temporary file: {str(e)}')

def prepare_training_data(phrase, sample_phrase=None, sample_voice=None, hash_id=None):
    """
    Prepares training data from either provided samples or existing storage.
    
    Args:
        phrase: The input phrase to process
        sample_phrase: Optional text sample for training
        sample_voice: Optional voice sample file for training
        hash_id: Optional hash ID for looking up existing training data
        
    Returns:
        dict: Training data with text and voice URL
        str: Error message if any, None otherwise
    """
    if sample_phrase and sample_voice:
        logger.info('Using provided sample phrase and voice for voice generation in request')
        
        # Create a temporary file for the voice data
        try:
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_voice:
                # Save the uploaded voice data to the temporary file
                sample_voice.save(tmp_voice.name)
                # Create a file URL for the temporary file
                voice_url = f'file://{tmp_voice.name}'
                logger.info(f'Created temporary voice file at: {voice_url}')
                
                return {
                    'text': sample_phrase,
                    'voice_url': voice_url,
                    '_temp_file': tmp_voice.name  # Store temp file path for cleanup -
                }, None
                
        except Exception as e:
            error_msg = f'Error processing voice sample: {str(e)}'
            logger.error(error_msg)
            return None, error_msg
    
    # Fall back to existing training data
    logger.info('Looking up training data from storage')
    if not hash_id:
        hash_id = DEFAULT_HASH_ID
        logger.info(f'Using default hash_id: {hash_id}')

    bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
    training_data = get_oldest_training_data(bucket_name, hash_id)
    if not training_data:
        error_msg = 'No training data found. Please provide samplePhrase and sampleVoice or ensure voice data is available.'
        logger.error(error_msg)
        return None, error_msg
    
    return training_data, None


def generate_sound_wave(phrase):
    try:
        logger.info(f'Starting sound wave generation for phrase: {phrase}')
        
        # Example: Generate a simple sine wave for demonstration
        sample_rate = 44100  # Sample rate in Hz
        duration = 2  # Duration in seconds
        frequency = 440  # Frequency of the sine wave (A4 note)
        
        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        wave = 0.5 * np.sin(2 * np.pi * frequency * t)  # Generate sine wave
        wave = (wave * 32767).astype(np.int16)  # Convert to 16-bit PCM format
    
    
        text = "[S1] Dia is an open weights text to dialogue model." 
        text += " [S2] You get full control over scripts and voices. "
        text += " [S1] Wow. Amazing. (laughs) [S2] Try it now on Git hub or Hugging Face."
        text += " [S1] " + phrase + " [S2] Thank you."
        logger.debug(f'Generated text prompt: {text}')
        
        # Generate audio
        logger.info('Starting audio generation with Dia model')
      #  wave = model.generate(text, use_torch_compile=True, verbose=True)
        logger.info('Audio generation completed successfully')
        
        # Use a generator to yield audio data
        logger.info('Starting audio data streaming')
        for sample in wave:
            yield sample.tobytes()
            
    except Exception as e:
        logger.error(f'Error generating sound wave: {str(e)}', exc_info=True)
        raise


@app.post('/train_audio')
async def train_audio(
    audio: UploadFile = File(...),
    text: str = Form(...),
    hash_id: str = Form(None)
):
    """
    Endpoint to receive an audio file, text, and hash_id for training.
    Accepts an audio file in the 'audio' form field, 'text' and 'hash_id' as form data.
    Returns success/error response.
    """
    try:
        # Check if required parts are present
        if not audio:
            raise HTTPException(status_code=400, detail='No audio file part in request')
            
        if not text:
             raise HTTPException(status_code=400, detail='Text is a required parameter')

                
        # Read audio file data
        audio_data = await audio.read()
        # Use default hash_id if not provided
        if not hash_id:
            hash_id = DEFAULT_HASH_ID
            logger.info(f'Using default hash_id: {hash_id}')
        logger.info(f'Training audio file: {audio.filename} for hash_id: {hash_id}')
        # Upload to GCS
        try:
            bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
            logger.info(f'Using bucket: {bucket_name}')
                
            text_url, voice_url = upload_or_update_data(
                bucket_name=bucket_name,
                hash_identifier=hash_id,
                text_data=text,
                voice_data_bytes=audio_data,
                audio_filename=audio.filename
            )
        except Exception as e:
            logger.error(f'GCS upload failed: {str(e)}', exc_info=True)
            raise HTTPException(status_code=500, detail=f'Failed to upload to storage: {str(e)}')
        
        if not text_url or not voice_url:
            raise HTTPException(status_code=500, detail='Failed to upload training data to storage')

            
        return {'response': 'success', 'message': 'Training data uploaded successfully', 'text_url': text_url, 'voice_url': voice_url}
        
    except Exception as e:
        logger.error(f'Error in train_audio: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=f'Failed to process training data: {str(e)}')



@app.get('/get_voice_models')
async def get_voice_models(bucket: str = None):
    """
    Endpoint to retrieve a list of all available voice models (hash identifiers) from the GCS bucket.
    
    Returns:
        JSON response containing a list of voice model identifiers.
        Example: {"voice_models": ["model1", "model2", ...]}
    """
    try:
        # First try to get bucket name from request parameters, then from environment, then use default
        bucket_name = bucket or os.getenv('EUPHONIA_DIA_GCS_BUCKET', DEFAULT_BUCKET)
        logger.info(f"Fetching all voice models from bucket: {bucket_name}")
        
        # Get all hash identifiers (voice models)
        voice_models = list_all_hash_identifiers(bucket_name)
        
        logger.info(f"Found {len(voice_models)} voice models")
        return {'status': 'success', 'voice_models': voice_models}
        
    except Exception as e:
        error_msg = f"Error fetching voice models: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


async def is_valid_wav(file_storage, check_format=True):
    """
    Validates if the uploaded file is a valid WAV file with optional format validation.
    
    Args:
        file_storage: FileStorage object from Flask request.files
        check_format: If True, validates audio format (mono, 16kHz)
        
    Returns:
        tuple: (is_valid: bool, error_message: str)
    """
    # Create a temporary file at the beginning
    tmp_fd, tmp_wav_file = tempfile.mkstemp(suffix='.wav')
    try:
        # Read the file content and write to temp file
        file_content = await file_storage.read()
        
        # Check if the file is empty
        if not file_content:
            return False, "Empty file provided"
            
        # Write content to the temporary file
        with os.fdopen(tmp_fd, 'wb') as f:
            f.write(file_content)
        
        # First, try to validate as WAV using pydub
        try:
            audio = AudioSegment.from_file(tmp_wav_file, format="wav")
            if len(audio) <= 0:
                return False, "Audio file has zero duration"
        except CouldntDecodeError:
            return False, "File is not a valid WAV file"
        
        # Then perform format validation if requested
        if check_format:
            try:
                # Validate WAV format using soundfile
                audio_array, samplerate = sf.read(tmp_wav_file)      
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
    finally:
        # Clean up the temporary file
        try:
            os.unlink(tmp_wav_file)
        except Exception:
            pass
        # Reset file pointer for any potential future use
        await file_storage.seek(0)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=60001)
