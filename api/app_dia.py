import logging
from flask import Flask, request, jsonify
import os
import tempfile
import soundfile as sf
from flask import Response
import numpy as np
from dia.Model import Dia

# Configure logging from environment variable
log_level = os.getenv('PYTHON_LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=getattr(logging, log_level, logging.INFO))
logger = logging.getLogger(__name__)

app = Flask(__name__)
model = Dia.from_pretrained("nari-labs/Dia-1.6B", compute_dtype="float16")

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
        
        # Generate the text prompt
        text = "[S1] Dia is an open weights text to dialogue model." 
        text += " [S2] You get full control over scripts and voices. "
        text += " [S1] Wow. Amazing. (laughs) [S2] Try it now on Git hub or Hugging Face."
        text += " [S1] " + phrase + " [S2] Thank you."
        logger.debug(f'Generated text prompt: {text}')
        
        # Generate audio
        logger.info('Starting audio generation with Dia model')
        wave = model.generate(text, use_torch_compile=True, verbose=True)
        logger.info('Audio generation completed successfully')
        
        # Use a generator to yield audio data
        logger.info('Starting audio data streaming')
        for sample in wave:
            yield sample.tobytes()
            
    except Exception as e:
        logger.error(f'Error generating sound wave: {str(e)}', exc_info=True)
        raise

if __name__ == '__main__':
    app.run(debug=True, host='127.0.0.1', port=8083)
