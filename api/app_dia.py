import logging
from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from starlette.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import os
import tempfile
import soundfile as sf
import numpy as np
import io
import subprocess
import ffmpeg
import sys
from pathlib import Path

# Add necessary paths
sys.path.append(os.path.join(os.path.dirname(__file__), 'local_adapter'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'gcloudAdapter'))
sys.path.append(os.path.join(os.path.dirname(__file__), 'e2ecloudAdapter'))

# Default constants
DEFAULT_HASH_ID = "default_user_123"
DEFAULT_BUCKET = "/home/jovyan/voice_assist/prod/voice_sample"
STORAGE = "local"
TRANSCRIBE_MODEL = "local"

# Conditional imports based on configuration
if TRANSCRIBE_MODEL == "local":
    from local_adapter.local_model_parakeet import transcribe_voice
if STORAGE == "gcs":
    from gcloudAdapter.gcp_storage import upload_or_update_data_gcs as upload_or_update_data, get_oldest_training_data, list_all_hash_identifiers
elif STORAGE == "e2ebucket":
    from e2ecloudAdapter.e2e_storage import upload_or_update_data_gcs as upload_or_update_data, get_oldest_training_data, list_all_hash_identifiers
elif STORAGE == "local":
    from local_adapter.local_storage import upload_or_update_data_local as upload_or_update_data, get_oldest_training_data, list_all_hash_identifiers

CLOUD = "local"
if CLOUD == "gcs":
    from gcloudAdapter.gcp_models import synthesize_speech_with_cloned_voice, call_vertex_Dia_model as call_voice_model
elif CLOUD == "local":
    from local_adapter.local_model import synthesize_speech_with_cloned_voice, call_vertex_Dia_model as call_voice_model

# Configure logging
log_level = os.getenv('PYTHON_LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Serve static files from the 'web' directory
app.mount("/web", StaticFiles(directory="web"), name="web")

@app.get("/")
async def read_root():
    return FileResponse('web/voice_assist.html')

@app.post('/process_audio')
async def process_audio(audio: UploadFile = File(...), hashVoiceName: str = Form(DEFAULT_HASH_ID)):
    """
    Endpoint to receive an audio file and stream it back.
    Accepts a WAV file in the 'wav' form field.
    Returns the same audio as a stream.
    """
    logger.debug(f"Request details: audio filename: {audio.filename}, hashVoiceName: {hashVoiceName}")
    try:
        if audio.content_type != 'audio/wav':
            raise HTTPException(status_code=400, detail='Invalid file type, must be .wav')

        logger.info(f'Processing audio file: {audio.filename}')

        transcribe_result = "Basically this is cloned voice test. As transcription is not yet working. did you hear any thing. If not check logs."
        try:
            audio_bytes = await audio.read()
            transcribe_result = _transcribe_audio_bytes(audio_bytes)
        except Exception as e:
            logger.error(f"Error during transcription: {str(e)}")
            transcribe_result = "Error happend during transcription. Please check logs"

        bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
        logger.info(f"Looking for text and voice sample for {hashVoiceName}")
        training_data = get_oldest_training_data(bucket_name, hashVoiceName)
        logger.debug(f"Found text and voice sample for {hashVoiceName}")

        voice_url = None
        oldest_text = ""
        if training_data:
            oldest_text = training_data['text']
            voice_url = training_data['voice_url']

        async def generate():
            try:
                logger.info("Attempting to synthesize speech with cloned voice...")
                if training_data:
                    voice_data = synthesize_speech_with_cloned_voice(
                        text_to_synthesize=transcribe_result,
                        clone_from_audio_gcs_url=voice_url,
                        clone_from_text_transcript=oldest_text
                    )
                else:
                    voice_data = call_voice_model(input_text=transcribe_result)
                
                if voice_data:
                    logger.debug(f'Starting audio file streaming, size: {len(voice_data)} bytes')
                    yield voice_data
                else:
                    logger.warning("No voice data received from synthesis.")
                    yield b''
            except Exception as e:
                logger.error(f"Synthesis failed: {str(e)}", exc_info=True)
                yield b''

        return StreamingResponse(
            generate(),
            media_type='audio/wav',
            headers={
                'X-Response-Text': transcribe_result,
                'Content-Disposition': f'attachment; filename=processed_{audio.filename}'
            }
        )
        
    except Exception as e:
        logger.error(f'Error processing audio: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

def _transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """Helper method to handle audio file transcription with temporary file management.
    
    Args:
        audio_bytes: The audio data in bytes.
        
    Returns:
        str: The transcription result
        
    Raises:
        Exception: If there's an error during transcription
    """
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
        try:
            temp_audio.write(audio_bytes)
            temp_audio.flush()
            os.fsync(temp_audio.fileno())
            return transcribe_voice(temp_audio.name)
        finally:
            try:
                os.unlink(temp_audio.name)
            except Exception as e:
                logger.warning(f"Could not delete temporary file {temp_audio.name}: {str(e)}")

@app.post('/transcribe')
async def transcribe(wav: UploadFile = File(...)):
    if not wav.filename.lower().endswith('.wav'):
        raise HTTPException(status_code=400, detail='Invalid file type, must be .wav')

    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
        try:
            contents = await wav.read()
            temp_audio.write(contents)
            temp_audio.flush()
            os.fsync(temp_audio.fileno())

            audio_array, samplerate = sf.read(temp_audio.name)
            if len(audio_array.shape) != 1:
                raise ValueError('Audio must be mono')
            if samplerate != 16000:
                raise ValueError('Audio must be 16kHz')

            pred = 'dummy transcript'
            return JSONResponse({'response': 'success!', 'transcript': pred})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'Invalid WAV file: {str(e)}')
        finally:
            os.unlink(temp_audio.name)

@app.post('/gendia')
async def gendia(phrase: str = Form(...), hash_id: str = Form(DEFAULT_HASH_ID)):
    try:
        logger.info(f'Received gendia request with phrase: {phrase}')
        bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
        training_data = get_oldest_training_data(bucket_name, hash_id)
        if not training_data:
            raise HTTPException(status_code=400, detail='No training data found for the user.')

        voice_data = synthesize_speech_with_cloned_voice(
            text_to_synthesize=phrase,
            clone_from_audio_gcs_url=training_data['voice_url'],
            clone_from_text_transcript=training_data['text']
        )
        return StreamingResponse(io.BytesIO(voice_data), media_type='audio/wav')
    except Exception as e:
        logger.error(f'Error processing gendia request: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post('/train_audio')
async def train_audio(audio: UploadFile = File(...), text: str = Form(...), hash_id: str = Form(DEFAULT_HASH_ID)):
    try:
        audio_data = await audio.read()
        logger.info(f'Training audio file: {audio.filename} for hash_id: {hash_id}')
        
        bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
        logger.info(f'Using bucket: {bucket_name}')
        
        text_url, voice_url = upload_or_update_data(
            bucket_name=bucket_name,
            hash_identifier=hash_id,
            text_data=text,
            voice_data_bytes=audio_data,
            audio_filename=audio.filename
        )
        
        if not text_url or not voice_url:
            raise HTTPException(status_code=500, detail='Failed to upload training data to storage')
            
        return JSONResponse({
            'response': 'success',
            'message': 'Training data uploaded successfully',
            'text_url': text_url,
            'voice_url': voice_url
        })
        
    except Exception as e:
        logger.error(f'Error in train_audio: {str(e)}', exc_info=True)
        raise HTTPException(status_code=500, detail=f'Failed to process training data: {str(e)}')

@app.get('/get_voice_models')
async def get_voice_models(bucket: str = None):
    try:
        bucket_name = bucket or os.getenv('EUPHONIA_DIA_GCS_BUCKET', DEFAULT_BUCKET)
        logger.info(f"Fetching all voice models from bucket: {bucket_name}")
        
        voice_models = list_all_hash_identifiers(bucket_name)
        
        logger.info(f"Found {len(voice_models)} voice models")
        return JSONResponse({
            'status': 'success',
            'voice_models': voice_models
        })
        
    except Exception as e:
        error_msg = f"Error fetching voice models: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(status_code=500, detail=error_msg)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=50001)