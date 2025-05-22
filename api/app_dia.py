import logging
from flask import Flask, request, jsonify
import os
import tempfile
import soundfile as sf
from flask import Response
import numpy as np
import io
import subprocess
import ffmpeg
#from dia.Model import Dia

# Configure logging from environment variable
log_level = os.getenv('PYTHON_LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

app = Flask(__name__,static_url_path='/web', static_folder='web')
logger.debug('Starting Flask server on port 5000')
logger.debug('Static files path: %s', app.static_url_path)
logger.debug('Static files root: %s', app.static_folder)
logger.debug('Static files url: %s', app.static_url_path)
logger.debug(' files root: %s', app.root_path)
#model = Dia.from_pretrained("nari-labs/Dia-1.6B", compute_dtype="float16")

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
        
        # Create a temporary file to save the uploaded audio
        _, tmp_wav_file = tempfile.mkstemp(suffix=audio_file.filename.split('.')[-1])   
        audio_file.save(tmp_wav_file)
        
        # Read the audio file
        audio_array, samplerate = sf.read(tmp_wav_file)
        
        # Clean up the temporary file
        os.remove(tmp_wav_file)
        
        processed_text = "Hi - Server"
        # Create a generator to stream the audio back
        def generate():
            # Create an in-memory buffer for WAV data
            wav_buffer = io.BytesIO()
            
            # Save as WAV to memory first (ffmpeg works better with WAV input)
            sf.write(
                wav_buffer,
                audio_array,
                16000,  # Sample rate
                format='WAV',
                closefd=False
            )
            wav_buffer.seek(0)
            
            # Set up ffmpeg to convert WAV to MP3 in memory
            process = (
                ffmpeg
                .input('pipe:')
                .output('pipe:', format='mp3', audio_bitrate='128k', ac=1, ar='16k')
                .run_async(pipe_stdin=True, pipe_stdout=True, pipe_stderr=True, quiet=True)
            )
            
            # Feed WAV data to ffmpeg
            process.stdin.write(wav_buffer.read())
            process.stdin.close()
            wav_buffer.close()
            
            # Stream MP3 data in chunks
            chunk_size = 4096
            while True:
                chunk = process.stdout.read(chunk_size)
                if not chunk:
                    break
                yield chunk
            
            # Clean up
            process.wait()
        
        # Return the audio as a stream with MP3 MIME type
        return Response(
            generate(),
            mimetype='audio/mp3',
            headers={
                'X-Response-Text': processed_text,
                'Content-Disposition': f'attachment; filename=processed_{os.path.splitext(audio_file.filename)[0]}.mp3'
            }
        )
        
    except Exception as e:
        logger.error(f'Error processing audio: {str(e)}', exc_info=True)
        return jsonify({'response': 'error', 'message': str(e)}), 500


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
        phrase = request.json.get('phrase')
        if not phrase:
            logger.error('No phrase provided in request')
            return jsonify({'response': 'error', 'message': 'No phrase provided'}), 400

        logger.info(f'Received gendia request with phrase: {phrase}')
        return Response(generate_sound_wave(phrase), mimetype='audio/wav')
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

if __name__ == '__main__':
    app.run(debug=True, host='localhost', port=50001)
