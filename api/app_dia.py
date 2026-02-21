import logging
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form, Depends
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
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
import shutil

# Import model request helpers
from model_request_helpers import (
    validate_audio_format_from_file,
    validate_audio_format,
    build_and_validate_audio_message,
    build_audio_message,
    validate_audio_message,
    is_valid_wav,
    TEMP_AUDIO_DIR,
    GOOD_AUDIO_DIR
)

sys.path.append(os.path.join(os.path.dirname(__file__), 'local_adapter'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'gcloudAdapter'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'e2ecloudAdapter'))


# Default constants
DEFAULT_HASH_ID = "default_user_123"
DEFAULT_BUCKET = "/home/jovyan/voice_assist/prod/voice_sample" #"euphonia-dia"
STORAGE = "local" # or "gcs" or "e2ebucket"
TRANSCRIBE_MODEL = "local" # or "gcs" or "e2ebucket"
# Constants for audio file storage are now imported from model_request_helpers


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
    # Ensure you have authenticated with GCP, e.g., via `gcloud auth application-default login`
    # or by setting the GOOGLE_APPLICATION_CREDENTIALS environment variable.
    from gcloudAdapter.gcp_models import synthesize_speech_with_cloned_voice, call_vertex_Dia_model as call_voice_model
elif CLOUD == "local":
    from local_adapter.local_model import synthesize_speech_with_cloned_voice, call_vertex_Dia_model as call_voice_model


# Configure logging from environment variable
log_level = os.getenv('PYTHON_LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Import clone client components
try:
    from audiocloneclient.client import AudioCloneClient
    from audiocloneclient import clone_interface_pb2
    from audiomessages import AudioMessage, Metadata
    CLONE_CLIENT_AVAILABLE = True
    logger.info("Clone client imported successfully")
except ImportError as e:
    CLONE_CLIENT_AVAILABLE = False
    logger.warning(f"Clone client not available: {e}")

app = FastAPI()
security = HTTPBearer(auto_error=True)
logger.debug('Starting FastAPI server')
# Serve static files from the 'web' directory
import os
from pathlib import Path
from oauth.google_stateless import router as google_auth_router
from oauth.apple_stateless import router as apple_auth_router
from oauth.routes import router as login_router
from auth_util import auth_router,get_auth_context

# Get the absolute path to the web directory
web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web')
app.mount("/web", StaticFiles(directory=web_dir), name="web")
app.include_router(google_auth_router)
app.include_router(apple_auth_router)
app.include_router(login_router)
app.include_router(auth_router)
for route in app.routes:
    logger.debug("Route is %s", route)
#model = Dia.from_pretrained("nari-labs/Dia-1.6B", compute_dtype="float16")

from fastapi import HTTPException

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
    training_data = None
    try:
        # Required parameter
        if not phrase:
            logger.error('No phrase provided in request')
            raise HTTPException(status_code=400, detail='No phrase provided')
        
        if sample_phrase:
            logger.info(f'Received sample phrase: {sample_phrase}')
       
        if sample_voice:
            logger.info(f'Received sample voice file: {sample_voice.filename}')
            is_valid, error_msg = await is_valid_wav(sample_voice, check_format=True)
            if not is_valid:
               raise HTTPException(status_code=400, detail=f'Invalid WAV file: {error_msg}')
        
        training_data, error = await prepare_training_data(
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
    finally:
        if training_data and '_temp_file' in training_data and os.path.exists(training_data['_temp_file']):
            try:
               # os.unlink(training_data['_temp_file'])
                logger.info(f'did not Cleaned up temporary file: {training_data["_temp_file"]}')
            except Exception as e:
                logger.error(f'Error cleaning up temporary file: {str(e)}')

async def prepare_training_data(phrase, sample_phrase=None, sample_voice=None, hash_id=None):
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
                contents =  await sample_voice.read()
                
                # Write the content to the temporary file
                tmp_voice.write(contents)
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
    hash_id: str = Form(None),
    auth_context: dict = Depends(get_auth_context)
):
    """
    Endpoint to receive an audio file, text, and hash_id for training.
    Accepts an audio file in the 'audio' form field, 'text' and 'hash_id' as form data.
    Returns success/error response.
    """
    try:
        if not auth_context['authenticated']:
            raise HTTPException(status_code=401, detail='Unauthorized')
        # Check if required parts are present
        if not audio:
            raise HTTPException(status_code=400, detail='No audio file part in request')
            
        if not text:
             raise HTTPException(status_code=400, detail='Text is a required parameter')

        if auth_context['is_Admin']:
            if not hash_id:
                hash_id = DEFAULT_HASH_ID
            elif hash_id != auth_context['va_dir']:
                logger.info(f'Using provided hash_id: {hash_id} as user is admin but hash_id does not match va_dir')
        else:
            if not hash_id:
                hash_id = auth_context['va_dir']
            elif hash_id != auth_context['va_dir']:
                logger.info(f'Not Using provided hash_id: {hash_id} as user is not admin and hash_id does not match va_dir')
                hash_id = auth_context['va_dir']
        if not hash_id:
            raise HTTPException(status_code=400, detail='hash_id is a required parameter')        
        
        logger.info(f'Training audio file: {audio.filename} for hash_id: {hash_id}')        
        # Read audio file data
        audio_data = await audio.read()

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
async def get_voice_models(request: Request, bucket: str = None, auth_context: dict = Depends(get_auth_context)):
    """
    Endpoint to retrieve a list of all available voice models (hash identifiers) from the GCS bucket.
    
    Returns:
        JSON response containing a list of voice model identifiers.
        Example: {"voice_models": ["model1", "model2", ...]}
    """
    try:
        # Check if user is authenticated using the auth context
        if not auth_context['authenticated']:
            logger.info("No authorization token provided, returning default voice models")
            return {'status': 'success', 'voice_models': [DEFAULT_HASH_ID]}
        
        if not auth_context['is_Admin']:
            va_dir = auth_context['va_dir']
            if not va_dir:
                logger.error("No va_dir provided, using default")
                raise HTTPException(status_code=403, detail='could not get va_dir from auth context')
            return {'status': 'success', 'voice_models': [va_dir]}
        
        # If token is present and use is admin, return folders.
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



@app.post('/clone_voice')
async def clone_voice(
    request_audio: UploadFile = File(...),
    request_text: str = Form(...),
    sample_audio: UploadFile = File(...),
    sample_text: str = Form(...),
    model_name: str = Form(None),
    auth_context: dict = Depends(get_auth_context)
):
    """
    Endpoint to clone voice using clone server on localhost.
    
    Args:
        request_audio: Audio file to be cloned (target speech)
        request_text: Text transcript for the request audio (phrase to be cloned)
        sample_audio: Sample audio file (source voice to clone from)
        sample_text: Text transcript for the sample audio
        model_name: Optional model name for cloning
    
    Returns:
        StreamingResponse with cloned audio data
    """
    if not CLONE_CLIENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Clone client not available")
    
    try:
        if not auth_context['authenticated']:
            raise HTTPException(status_code=401, detail='Unauthorized')
        
        # Create and validate AudioMessage objects using wrapper
        request_audio_message, _ = build_and_validate_audio_message(
            audio_data=request_audio,
            text=request_text,
            file_name=None,
            check_format=True
        )
        
        sample_audio_message, _ = build_and_validate_audio_message(
            audio_data=sample_audio,
            text=sample_text,
            file_name=None,
            check_format=True
        )
        
        logger.info(f"Processing clone request: {len(request_audio_message.audio_binary)} bytes request audio, {len(sample_audio_message.audio_binary)} bytes sample audio")
        logger.info(f"Audio files: {request_audio_message.audio_file_path}, {sample_audio_message.audio_file_path}")
        
        # Create CloneRequest
        clone_request = clone_interface_pb2.CloneRequest()
        clone_request.request_audio_message.CopyFrom(request_audio_message)
        clone_request.sample_audio_message.CopyFrom(sample_audio_message)
        if model_name:
            clone_request.model_name = model_name
        
        # Call clone server
        with AudioCloneClient("localhost:50051") as client:
            logger.info("Calling clone server at localhost:50051")
            response = client.clone(clone_request)
            
            logger.info(f"Clone response received: {len(response.cloned_audio_message.audio_binary)} bytes")
            if response.model_name:
                logger.info(f"Model used: {response.model_name}")
            if response.meta.status_code:
                logger.info(f"Status code: {response.meta.status_code}")
            
            # Return cloned audio as streaming response
            headers = {
                'X-Model-Name': response.model_name or 'default',
                'X-Status-Code': str(response.meta.status_code or 200),
                'Content-Disposition': f'attachment; filename=cloned_{request_audio.filename}'
            }
            
            return StreamingResponse(
                BytesIO(response.cloned_audio_message.audio_binary),
                media_type='audio/wav',
                headers=headers
            )
                
            
    except grpc.RpcError as e:
        logger.error(f"gRPC error during cloning: {e}")
        raise HTTPException(status_code=503, detail=f"Clone server error: {e.details() if hasattr(e, 'details') else str(e)}")
    except Exception as e:
        logger.error(f'Error during voice cloning: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=f'Voice cloning failed: {str(e)}')


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=60001)
