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
DEFAULT_SAMPLE_RATE = 24000  # Common sample rate for TTS model
# Global instance and lock for thread-safe singleton
_tts_instance = None
_tts_lock = threading.Lock()

def get_tts_instance() -> 'TransformerTTS':
    """
    Get or create a thread-safe singleton instance of TransformerTTS.
    
    Returns:
        TransformerTTS: A shared instance of the TTS model
        
    Raises:
        RuntimeError: If model loading fails
    """
    global _tts_instance
    
    if _tts_instance is None:
        with _tts_lock:  # Ensure thread safety during initialization
            if _tts_instance is None:  # Double-checked locking pattern
                logger.info("Initializing TTS model...")
                _tts_instance = TransformerTTS()
                if not _tts_instance.load_model():
                    _tts_instance = None
                    raise RuntimeError("Failed to load TTS model")
                logger.info("TTS model initialized successfully")
    
    return _tts_instance

def cleanup_tts_instance():
    """
    Clean up the global TTS instance and free resources.
    """
    global _tts_instance
    
    if _tts_instance is not None:
        with _tts_lock:
            if _tts_instance is not None:
                logger.info("Cleaning up TTS model...")
                if hasattr(_tts_instance, 'model'):
                    # Move model to CPU and clear CUDA cache if using GPU
                    if torch.cuda.is_available():
                        _tts_instance.model.to('cpu')
                        torch.cuda.empty_cache()
                    del _tts_instance.model
                _tts_instance = None
                logger.info("TTS model cleaned up")

# Add cleanup on module unload
atexit.register(cleanup_tts_instance)

class TransformerTTS:
    """Base class for transformer-based text-to-speech synthesis."""
    
    def __init__(self, model_path: Optional[str] = None, device: str = None):
        """
        Initialize the TTS model.
        
        Note: Use get_tts_instance() instead of direct instantiation.
        """
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model_checkpoint = "nari-labs/Dia-1.6B-0626"
        self.model = None
        self.processor = None
        self.sample_rate = 24000
        self._lock = threading.Lock()  # Instance-level lock for thread safety
      
    
    def load_model(self) -> bool:
        """
        Load the TTS model and processor.
        
        Returns:
            bool: True if loading was successful, False otherwise
        """
        with self._lock:
            if self.model is not None:
                return True
                
            try:
                logger.info(f"Loading TTS model from {self.model_checkpoint}...")
                self.processor = AutoProcessor.from_pretrained(self.model_checkpoint)
                self.model = DiaForConditionalGeneration.from_pretrained(self.model_checkpoint).to(self.device)
                logger.info("TTS model and vocoder loaded successfully")
                return True
            except Exception as e:
                logger.error(f"Failed to load TTS model: {str(e)}")
                self.model = None
                self.processor = None
                return False
    
    def synthesize(
        self, 
        text: str,
        audio_prompt :str | torch.Tensor | None = None,
        clone_from_text :str = None,
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
            with self._lock:
                try:
                    if(audio_prompt):
                        inputs = self.processor(text=clone_from_text+text, audio_prompt = audio_prompt, padding=True, return_tensors="pt").to(self.device)
                    else:
                        inputs = self.processor(text = text, padding=True, return_tensors="pt").to(self.device)
                    outputs = self.model.generate(**inputs, max_new_tokens = max_new_tokens, guidance_scale = guidance_scale, temperature = temperature, top_p = top_p, top_k = top_k)
                    logger.info(f"Synthesizing speech for text: {text[:50]}...")
                    #audio_array = self.processor.batch_decode(outputs)
                    logger.debug(f"Output type: {type(outputs)}")
                    if(isinstance(outputs, torch.Tensor)):
                        if(outputs.data and isinstance(outputs.data, torch.Tensor)):
                            audio_array = outputs.data.cpu().numpy()
                            logger.debug(f"Audio array type: {type(audio_array)}")
                        else:
                            audio_array = outputs.cpu().numpy()
                            logger.debug(f"Audio array type: {type(audio_array)}")
                    elif(isinstance(outputs, np.ndarray)):  
                        audio_array = outputs
                        logger.debug(f"Audio array type: {type(audio_array)}")
                    elif(isinstance(outputs, list)):
                        audio_array = outputs[0].cpu().numpy()
                        logger.debug(f"Audio array type: {type(audio_array)}")
                    return audio_array, self.sample_rate 
                except Exception as e:
                    logger.error(f"Speech synthesis failed: {str(e)}")
                    raise

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
            text=text_to_synthesize,
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
        return None

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
    logger.info("Voice cloning not yet implemented - using default voice")
        
    # Generate audio (placeholder implementation)
    audio_array, sample_rate = tts.synthesize(
        text=input_text,
        temperature=temperature,
        guidance_scale=config_scale,
        top_p=top_p
    )

    logger.warning("Local DIA model implementation executed")
    return convertNPArraytoMP3(audio_array,sample_rate)

def _resolve_audio_prompt(audio_source: str | None) -> torch.Tensor | str | None:
    """
    Resolve an audio prompt from various sources (URL, file path, etc.) and return as a PyTorch tensor.
    
    Args:
        audio_source: The source of the audio (URL, file path, or None)
        
    Returns:
        torch.Tensor | None: The audio data as a PyTorch tensor with shape (num_channels, num_samples)
    """
    if not audio_source:
        return None
        
    try:
        parsed_url = urlparse(audio_source)
        
        # Handle web URL
        if parsed_url.scheme in ('http', 'https'):
            audio_bytes = download_file_from_url(audio_source)
            # Convert bytes to file-like object for soundfile
            with io.BytesIO(audio_bytes) as audio_file:
                audio_array, sample_rate = sf.read(audio_file, dtype='float32')
        
        # Handle local file path
        elif parsed_url.scheme == 'file' or not parsed_url.scheme:
            file_path = parsed_url.path if parsed_url.scheme == 'file' else audio_source
            return file_path if (file_path) else None
            #audio_array, sample_rate = sf.read(file_path, dtype='float32')
        else:
            logger.warning(f"Unsupported URL scheme: {parsed_url.scheme}")
            return None
        
        # Convert to mono if stereo
        if len(audio_array.shape) > 1:
            audio_array = np.mean(audio_array, axis=1)  # Convert to mono by averaging channels
            
        # Convert to PyTorch tensor and ensure proper shape (num_channels, num_samples)
        audio_tensor = torch.from_numpy(audio_array).float()
        if len(audio_tensor.shape) == 1:
            audio_tensor = audio_tensor.unsqueeze(0)  # Add channel dimension if mono
            
        return audio_tensor
        
    except Exception as e:
        logger.error(f"Error processing audio source {audio_source}: {str(e)}")
        return None

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

def convertNPArraytoMP3(audio_array: np.ndarray, sample_rate: int, bitrate: str = "128k") -> bytes:
    """
    Convert a numpy array to MP3 bytes using pydub.
    
    Args:
        audio_array: Numpy array containing audio samples
        sample_rate: Sample rate of the audio
        bitrate: Bitrate for the output MP3 (e.g., "128k", "192k")
        
    Returns:
        bytes: MP3 audio data as bytes
        
    Raises:
        ImportError: If pydub is not installed
        Exception: For any conversion errors
    """
    try:
       
        # Ensure audio_array is in the correct format (mono, 16-bit PCM)
        if audio_array.dtype != np.int16:
            # Normalize to 16-bit range
            audio_array = (audio_array * (2**15 - 1)).astype(np.int16)
        
        # Convert numpy array to AudioSegment
        audio_segment = AudioSegment(
            audio_array.tobytes(),
            frame_rate=sample_rate,
            sample_width=audio_array.dtype.itemsize,
            channels=1  # Assuming mono audio
        )
        
        # Export to MP3 in memory
        with io.BytesIO() as mp3_buffer:
            audio_segment.export(
                mp3_buffer,
                format="mp3",
                bitrate=bitrate,
                parameters=["-ac", "1"]  # Force mono output
            )
            return mp3_buffer.getvalue()
            
    except ImportError:
        logger.error("pydub is required for MP3 conversion. Install with: pip install pydub")
        raise
    except Exception as e:
        logger.error(f"Error converting to MP3: {str(e)}")
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
        print(f"Generated {len(audio_data)} samples of audio at {sample_rate}Hz")
        print(f"Audio saved to: {os.path.abspath(output_path)}")
        
    except Exception as e:
        print(f"Error: {str(e)}")
