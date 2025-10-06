import logging
from re import A
from flask import Flask, request, jsonify
import os
import tempfile
import soundfile as sf
from flask import Response
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
if(TRANSCRIBE_MODEL == "local"):
    from local_adapter.local_model_parakeet import transcribe_voice as transcribe_voice

# Configure logging from environment variable
log_level = os.getenv('PYTHON_LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO), format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__,static_url_path='/web', static_folder='web')
logger.debug('Starting Flask server on port 5000')
logger.debug('Static files path: %s', app.static_url_path)
logger.debug('Static files root: %s', app.static_folder)
logger.debug('Static files url: %s', app.static_url_path)
logger.debug(' files root: %s', app.root_path)
#model = Dia.from_pretrained("nari-labs/Dia-1.6B", compute_dtype="float16")


    # Ensure you have authenticated with GCP, e.g., via `gcloud auth application-default login`
    # or by setting the GOOGLE_APPLICATION_CREDENTIALS environment variable.
@app.route('/process_audio', methods=['POST'])
def process_audio():
    """
    Endpoint to receive an audio file and stream it back.
    Accepts a WAV file in the 'wav' form field.
    Returns the same audio as a stream.
    """
    logger.debug("Request details: %s", request)
    try:
        # Check if file part is present
        if 'audio' not in request.files:
            return jsonify({'response': 'error', 'message': 'No audio file part in request'}), 400

        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'response': 'error', 'message': 'No selected file'}), 400
            
        logger.info(f'Processing audio file: {audio_file.filename}')
        mime_type = audio_file.content_type

        if mime_type != 'audio/wav':
            return jsonify({'response': 'error', 'message': 'Invalid file type, must be .wav'}), 400
                # Get the text to synthesize from form or use a default
        transcribe_result = "Basically this is cloned voice test. As transcription is not yet working. did you hear any thing. If not check logs."
        try:
            transcribe_result = _transcribe_audio_file(audio_file)
        except Exception as e:
            logger.error(f"Error during transcription: {str(e)}")
            transcribe_result = "Error happend during transcription. Please check logs"

        # Get the oldest training data for the default user
        bucket_name = DEFAULT_BUCKET if os.environ.get("EUPHONIA_DIA_GCS_BUCKET") is None else os.environ.get("EUPHONIA_DIA_GCS_BUCKET")
        # TODO: a case could be made to pick the latest cloned sample, after all why save them? but right now going with oldest. 
        # TODO: Also eventually the hash would be of current user and not default. That will need fix in train_audio as well.
        hashVoiceName = request.form.get('hashVoiceName', DEFAULT_HASH_ID)
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
        
        # Return the synthesized audio as a stream
        return Response(
            generate(),
            mimetype='audio/wav',
            headers={
                'X-Response-Text': processed_text,
                'Content-Disposition': f'attachment; filename=processed_{audio_file.filename}'
            }
        )
        
    except Exception as e:
        logger.error(f'Error processing audio: {str(e)}', exc_info=True)
        return jsonify({'response': 'error', 'message': str(e)}), 500


def _transcribe_audio_file(audio_file):
    """Helper method to handle audio file transcription with temporary file management.
    
    Args:
        audio_file: The uploaded file object
        
    Returns:
        str: The transcription result
        
    Raises:
        Exception: If there's an error during transcription
    """
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_audio:
        try:
            # Save the uploaded file to the temporary file
            audio_file.save(temp_audio.name)
            
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

@app.route('/transcribe', methods=['POST'])
def transcribe():
    # Check if file part is present
    if 'wav' not in request.files:
        return jsonify({'response': 'error', 'message': 'No wav file part in request'}), 400
    audio = request.files['wav']
    if audio.filename == '':
        return jsonify({'response': 'error', 'message': 'No selected file'}), 400
    if not audio.filename.lower().endswith('.wav'):
        return jsonify({'response': 'error', 'message': 'Invalid file type, must be .wav'}), 400

    # Save to temp file
    _, tmp_wav_file = tempfile.mkstemp(suffix='.wav')
    audio.save(tmp_wav_file)

    # Validate WAV file using soundfile
    try:
        audio_array, samplerate = sf.read(tmp_wav_file)
        if len(audio_array.shape) != 1:
            raise ValueError('Audio must be mono')
        if samplerate != 16000:
            raise ValueError('Audio must be 16kHz')
    except Exception as e:
        os.remove(tmp_wav_file)
        return jsonify({'response': 'error', 'message': f'Invalid WAV file: {str(e)}'}), 400

    # Dummy transcription (replace with real model)
    pred = 'dummy transcript'

    os.remove(tmp_wav_file)
    return jsonify({'response': 'success!', 'transcript': pred})


@app.route('/gendia', methods=['POST'])
def gendia():
    try:
        phrase = request.form.get('phrase')
        if not phrase:
            logger.error('No phrase provided in request')
            return jsonify({'response': 'error', 'message': 'No phrase provided'}), 400

        logger.info(f'Received gendia request with phrase: {phrase}')
        hash_id = request.form.get('hash_id')
        
        # Use default hash_id if not provided
        if not hash_id:
            hash_id = DEFAULT_HASH_ID
            logger.info(f'Using default hash_id: {hash_id}')

        bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
        training_data = get_oldest_training_data(bucket_name, hash_id)
        if not training_data:
            return jsonify({
                'response': 'error',
                'message': 'No training data found for the user. Please ensure both text and voice data are available.'
            }), 400

        voice_data = synthesize_speech_with_cloned_voice(
                    text_to_synthesize=phrase,
                    clone_from_audio_gcs_url=training_data['voice_url'],
                    clone_from_text_transcript=training_data['text']
                )
        return Response(voice_data, mimetype='audio/wav')
    except Exception as e:
        logger.error(f'Error processing gendia request: {str(e)}', exc_info=True)
        return jsonify({'response': 'error', 'message': str(e)}), 500

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


@app.route('/train_audio', methods=['POST'])
def train_audio():
    """
    Endpoint to receive an audio file, text, and hash_id for training.
    Accepts an audio file in the 'audio' form field, 'text' and 'hash_id' as form data.
    Returns success/error response.
    """
    try:
        # Check if required parts are present
        if 'audio' not in request.files:
            return jsonify({'response': 'error', 'message': 'No audio file part in request'}), 400
            
        text = request.form.get('text')    
        if not text:
            return jsonify({
                'response': 'error',
                'message': 'Text is a required parameter'
            }), 400
            
        audio_file = request.files['audio']
        if audio_file.filename == '':
            return jsonify({'response': 'error', 'message': 'No selected file'}), 400
                
        # Read audio file data
        audio_data = audio_file.read()
        #get Hash
        hash_id = request.form.get('hash_id')       
        # Use default hash_id if not provided
        if not hash_id:
            hash_id = DEFAULT_HASH_ID
            logger.info(f'Using default hash_id: {hash_id}')
        logger.info(f'Training audio file: {audio_file.filename} for hash_id: {hash_id}')
        # Upload to GCS
        try:
            bucket_name = os.environ.get("EUPHONIA_DIA_GCS_BUCKET", DEFAULT_BUCKET)
            logger.info(f'Using bucket: {bucket_name}')
                
            text_url, voice_url = upload_or_update_data(
                bucket_name=bucket_name,
                hash_identifier=hash_id,
                text_data=text,
                voice_data_bytes=audio_data,
                audio_filename=audio_file.filename
            )
        except Exception as e:
            logger.error(f'GCS upload failed: {str(e)}', exc_info=True)
            return jsonify({
                'response': 'error',
                'message': f'Failed to upload to storage: {str(e)}'
            }), 500
        
        if not text_url or not voice_url:
            return jsonify({
                'response': 'error',
                'message': 'Failed to upload training data to storage'
            }), 500
            
        return jsonify({
            'response': 'success',
            'message': 'Training data uploaded successfully',
            'text_url': text_url,
            'voice_url': voice_url
        })
        
    except Exception as e:
        logger.error(f'Error in train_audio: {str(e)}', exc_info=True)
        return jsonify({
            'response': 'error',
            'message': f'Failed to process training data: {str(e)}'
        }), 500


@app.route('/get_voice_models', methods=['GET'])
def get_voice_models():
    """
    Endpoint to retrieve a list of all available voice models (hash identifiers) from the GCS bucket.
    
    Returns:
        JSON response containing a list of voice model identifiers.
        Example: {"voice_models": ["model1", "model2", ...]}
    """
    try:
        # First try to get bucket name from request parameters, then from environment, then use default
        bucket_name = request.args.get('bucket') or os.getenv('EUPHONIA_DIA_GCS_BUCKET', DEFAULT_BUCKET)
        logger.info(f"Fetching all voice models from bucket: {bucket_name}")
        
        # Get all hash identifiers (voice models)
        voice_models = list_all_hash_identifiers(bucket_name)
        
        logger.info(f"Found {len(voice_models)} voice models")
        return jsonify({
            'status': 'success',
            'voice_models': voice_models
        })
        
    except Exception as e:
        error_msg = f"Error fetching voice models: {str(e)}"
        logger.error(error_msg)
        return jsonify({
            'status': 'error',
            'message': error_msg
        }), 500


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=50001)
