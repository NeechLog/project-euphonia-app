import logging
from typing import Optional, Tuple, Union
import torch
import numpy as np
from pathlib import Path
import requests
from urllib.parse import urlparse
import os
import threading
import atexit
import soundfile as sf
from transformers import AutoProcessor, DiaForConditionalGeneration
from pydub import AudioSegment
import io
import time 
import traceback
from local_utils import _resolve_audio_prompt, download_file_from_url, convertNPArraytoMP3, log_model_outputs , save_debug_sound
model_imps = "DIA" # "TT"
if model_imps == "DIA":
    from local_model_dia import get_tts_instance
else:
    from dia_hf import get_tts_instance
# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
SAMPLE_TEXT = "[S1] Dia is an open weights text to dialogue model. [S2] You get full control over scripts and voices. [S1] Wow. Amazing. (laughs) [S2] Try it now on Git hub or Hugging Face."
GUIDANCE_SCALE_PARAM = 3.0
TEMPERATURE_PARAM = 1.8
TOP_P_PARAM = 0.95
# Constants
DEFAULT_SAMPLE_RATE = 44100  # Common sample rate for TTS model

def synthesize_speech_with_cloned_voice(
    text_to_synthesize: str,
    clone_from_audio_gcs_url: str,
    clone_from_text_transcript: str,
    config_scale: float = 3.0,
    temperature: float = 1.8,
    top_p: float = 0.90
) -> bytes | None:
    """
    Generates speech audio by cloning a voice from an audio sample and its transcript
    using a local transformer-based TTS model.

    Args:
        text_to_synthesize: The text to be converted into speech.
        clone_from_audio_gcs_url: Path to the audio file to clone the voice from.
                                 In local implementation, this can be a local file path.
        clone_from_text_transcript: The transcript of the audio provided for cloning.
        temperature: Controls randomness in generation. Higher is more random.
                     (Default: 1.3)
        top_p: Nucleus sampling parameter. (Default: 0.95)
        config_scale: Configuration scale. (Default: 0.3)

    Returns:
        Decoded audio bytes if successful, otherwise None.
    """
    logger.info(
        f"Synthesizing speech with voice cloning. Text length: {len(text_to_synthesize)}, "
        f"Audio source: {clone_from_audio_gcs_url}"
    )
    
    try:
        # Initialize the TTS model (lazy loading happens here)
        audio_data = _resolve_audio_prompt(clone_from_audio_gcs_url)
        tts = get_tts_instance()
        
        logger.info("Voice cloning not yet implemented - using default voice")
        
        # Generate audio
        audio_array, sample_rate = tts.synthesize(
            text_to_speak=text_to_synthesize,
            audio_prompt=audio_data if(audio_data is not None) else None,  
            clone_from_text = clone_from_text_transcript,
            temperature=temperature,
            guidance_scale=config_scale,
            top_p=top_p
        )
        
        # Convert to WAV format (placeholder - implement proper WAV conversion)
        # For now, just return the raw array as bytes

        audio_bytes = convertNPArraytoMP3(audio_array,sample_rate)
        
        return audio_bytes
        
    except Exception as e:
        logger.error(f"Speech synthesis failed: {str(e)}")
        error_trace = traceback.format_exc()
        logger.error(f"Stack trace:\n{error_trace}")
        raise


def call_vertex_Dia_model(
    input_text: str = SAMPLE_TEXT,
    config_scale: float = GUIDANCE_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM
) -> bytes | None:
    """
    Placeholder for the local implementation of the DIA model.
    This mirrors the GCP Vertex AI DIA model interface.
    """
    tts = get_tts_instance()
    logger.info("Voice  - using default voice")
        
    try:
        # Generate audio (placeholder implementation)
        audio_array, sample_rate = tts.synthesize(
            text_to_speak=input_text,
            temperature=temperature,
            guidance_scale=config_scale,
            top_p=top_p
        )
        
        logger.info("Successfully generated audio with local DIA model")
        return convertNPArraytoMP3(audio_array, sample_rate)
        
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in call_vertex_Dia_model: {str(e)}")
        logger.error(f"Stack trace:\n{error_trace}")
        raise

if __name__ == "__main__":
    # Example usage
    try:
        text = "This is a test of the local TTS system."
        audio_data, sample_rate = synthesize_speech_with_cloned_voice(
            text_to_synthesize=text,
            clone_from_audio_gcs_url="test_audio_gcs_url",
            clone_from_text_transcript="test_transcript",
            temperature=1.3,
            top_p=0.95,
            config_scale=0.3
        )
        import soundfile as sf
        # Save audio to file
        output_path = "output_audio.mp3"
        sf.write(output_path, audio_data, sample_rate, format='mp3')
        logger.error(f"Generated {len(audio_data)} samples of audio at {sample_rate}Hz")
        logger.error(f"Audio saved to: {os.path.abspath(output_path)}")
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
