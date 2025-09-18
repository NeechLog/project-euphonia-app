import logging
from typing import Optional, Tuple, Union
import torch
import numpy as np
from pathlib import Path
import requests
from urllib.parse import urlparse
import os

from transformers import AutoProcessor, DiaForConditionalGeneration

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)
SAMPLE_TEXT = "[S1] Dia is an open weights text to dialogue model. [S2] You get full control over scripts and voices. [S1] Wow. Amazing. (laughs) [S2] Try it now on Git hub or Hugging Face."
config_SCALE_PARAM = 0.3
TEMPERATURE_PARAM = 1.3
TOP_P_PARAM = 0.95
# Constants
DEFAULT_SAMPLE_RATE = 24000  # Common sample rate for TTS models

class TransformerTTS:
    """Base class for transformer-based text-to-speech synthesis."""
    
    def __init__(self, model_path: Optional[str] = None, device: str = None):
        """
        Initialize the TTS model.
        
        Args:
            model_path: Path to the pre-trained model. If None, uses default location.
            device: Device to run the model on ('cuda' or 'cpu'). Auto-detects if None.
        """
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_checkpoint = "nari-labs/Dia-1.6B-0626"
      
    
    def load_model(self):
        """Load the TTS model and vocoder."""
        try:
            self.processor = AutoProcessor.from_pretrained(self.model_checkpoint)
            self.model = DiaForConditionalGeneration.from_pretrained(self.model_checkpoint).to(self.device)
            logger.info("TTS model and vocoder loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load TTS model: {str(e)}")
            return False
    
    def synthesize(
        self, 
        text: str,
        audio_prompt :bytes,
        clone_from_text,
        max_new_tokens: int = 3072,
        guidance_scale: float = 3.0,
        temperature: float = 1.8,
        top_p: float = 0.90,
        top_k: int = 45,
        **kwargs
    ) -> Tuple[np.ndarray, int]:
            """
            Synthesize speech from text.
            Args:
                text: Input text to synthesize
                max_new_tokens: Maximum number of new tokens to generate (default: 3072)
                guidance_scale: Controls the strength of guidance (default: 3.0)
                temperature: Controls randomness in generation (default: 1.8)
                top_p: Nucleus sampling threshold (default: 0.90)
                top_k: Number of top-k tokens to consider (default: 45)
                **kwargs: Additional parameters for synthesis
                
            Returns:
                Tuple of (audio_array, sample_rate)
            """
            if self.model_checkpoint is None:
                if not self.load_model():
                    raise RuntimeError("Failed to load TTS model")
            
            try:
                if(audio_prompt):
                    inputs = self.processor(text=clone_from_text+text, audio_prompt = audio_prompt, padding=True, return_tensors="pt").to(self.device)
                else:
                    inputs = self.processor(text = text, padding=True, return_tensors="pt").to(self.device)
                outputs = self.model.generate(**inputs, max_new_tokens = max_new_tokens, guidance_scale = guidance_scale, temperature = temperature, top_p = top_p, top_k = top_k)
                logger.info(f"Synthesizing speech for text: {text[:50]}...")
                audio_array = self.processor.batch_decode(outputs)
                return audio_array, self.sample_rate
                
            except Exception as e:
                logger.error(f"Speech synthesis failed: {str(e)}")
                raise

def synthesize_speech_with_cloned_voice(
    text_to_synthesize: str,
    clone_from_audio_gcs_url: str,
    clone_from_text_transcript: str,
    config_scale: float = 0.3,
    temperature: float = 1.3,
    top_p: float = 0.95
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
        try:
            if(clone_from_audio_gcs_url) :
                audio_data = download_file_from_url(clone_from_audio_gcs_url)
            else:
                audio_data = None
        except Exception as e:
            logger.error(f"Failed to download audio from {clone_from_audio_gcs_url}: {str(e)}")
            
        tts = TransformerTTS()
        
        # TODO: Implement actual voice cloning logic 
        logger.info("Voice cloning not yet implemented - using default voice")
        
        # Generate audio (placeholder implementation)
        audio_array, sample_rate = tts.synthesize(
            text=text_to_synthesize,
            audio_prompt=audio_data if(audio_data is not None) else None,  
            clone_from_text = clone_from_text_transcript,
            temperature=temperature,
            guidance_scale=config_scale,
            top_p=top_p
        )
        
        # Convert to WAV format (placeholder - implement proper WAV conversion)
        # For now, just return the raw array as bytes
        audio_bytes = audio_array.tobytes()
        
        return audio_bytes
        
    except Exception as e:
        logger.error(f"Speech synthesis with cloned voice failed: {str(e)}")
        return None

def call_vertex_Dia_model(
    input_text: str = SAMPLE_TEXT,
    config_scale: float = config_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM
) -> bytes | None:
    """
    Placeholder for the local implementation of the DIA model.
    This mirrors the GCP Vertex AI DIA model interface.
    """
    tts = TransformerTTS()
    logger.info("Voice cloning not yet implemented - using default voice")
        
    # Generate audio (placeholder implementation)
    audio_array, sample_rate = tts.synthesize(
        text=input_text,
        temperature=temperature,
        guidance_scale=config_scale,
        top_p=top_p
    )

    logger.warning("Local DIA model implementation not yet available")
    return {"predictions": [{"content": "Local DIA model implementation not yet available"}]}


def download_file_from_url(url: str) -> bytes:
    """
    Download a file from a URL or read from a local file path.
    
    Args:
        url: The URL or local file path to download/read from.
            Can be:
            - http:// or https:// for web URLs
            - file:// for local files
            - Plain path for local files
            
    Returns:
        The binary content of the file.
        
    Raises:
        ValueError: If the URL scheme is not supported.
        requests.RequestException: If there's an error downloading from a web URL.
        IOError: If there's an error reading a local file.
    """
    parsed_url = urlparse(url)
    
    if parsed_url.scheme in ('http', 'https'):
        # Download from web URL
        logger.info(f"Downloading file from URL: {url}")
        response = requests.get(url)
        response.raise_for_status()
        return response.content
    elif parsed_url.scheme == 'file' or not parsed_url.scheme:
        # Read from local file
        file_path = parsed_url.path if parsed_url.scheme == 'file' else url
        logger.info(f"Reading local file: {file_path}")
        with open(file_path, 'rb') as f:
            return f.read()
    else:
        raise ValueError(f"Unsupported URL scheme: {parsed_url.scheme}")


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
        print(f"Generated {len(audio_data)} samples of audio at {sample_rate}Hz")
        print(f"Audio saved to: {os.path.abspath(output_path)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
