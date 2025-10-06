import logging
from typing import Optional, Tuple, Dict, Any
import numpy as np
import threading
import atexit

import nemo.collections.asr as nemo_asr

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global instance and lock for thread-safe singleton
_transcribe_instance = None
_transcribe_lock = threading.Lock()

def get_transcribe_instance() -> 'Transcribe_Local_Model':
    """Get or create a thread-safe singleton instance of Parakeet_Local_Wrapper."""
    global _transcribe_instance
    
    if _transcribe_instance is None:
        with _transcribe_lock:
            if _transcribe_instance is None:
                logger.info("Initializing Parakeet local model...")
                _transcribe_instance = Transcribe_Local_Model()
                if not _transcribe_instance.load_model():
                    _transcribe_instance = None
                    raise RuntimeError("Failed to initialize Parakeet local model")
    return _transcribe_instance

def cleanup_transcribe_instance() -> None:
    """Clean up the global transcribe instance and free resources."""
    global _transcribe_instance
    if _transcribe_instance is not None:
        logger.info("Cleaning up Parakeet instance...")
        _transcribe_instance = None

# Add cleanup on module unload
atexit.register(cleanup_transcribe_instance)

class Transcribe_Local_Model:
    """
    A wrapper class for the local Parakeet speech-to-text model.
    This is a mock implementation that returns sample transcriptions.
    """
    
    def __init__(self, device: str = None):
        """Initialize the model."""
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Device is {self.device}")
        self.model = None
        self._lock = threading.Lock()
        self.sample_transcriptions = [
            "This is a sample transcription from the mock model.",
            "The quick brown fox jumps over the lazy dog.",
            "Speech recognition is a fascinating field of artificial intelligence.",
            "This is a test transcription from the Parakeet model.",
            "Hello, how can I help you today?"
        ]
        self.counter = 0

    def load_model(self) -> bool:
        """Mock model loading function."""
        with self._lock:
            if self.model is not None:
                return True
            
            logger.info("Loading Parakeet model...")
            # In a real implementation, this would load the actual model
            self.model = nemo_asr.models.ASRModel.from_pretrained(model_name="nvidia/parakeet-tdt-0.6b-v2")
            logger.info("Parakeet model loaded")
            return True

    def transcribe_voice(
        self,
        audio_data_path: str,
        sample_rate: int = 16000,
        **kwargs
    ) -> str:
        """
        Transcribe audio data to text.
        
        Args:
            audio_data_path: File path containing the wav file.
            sample_rate: Sample rate of the audio data
            **kwargs: Additional arguments for the transcription
            
        Returns:
            str: The transcribed text
        """
        if not self.model:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        # In a real implementation, this would process the audio_data
        # For now, just return a sample transcription
        with self._lock:
            transcription = self.model.transcribe(audio_data_path)
            self.counter += 1
            logger.info(f"Audio file {audio_data_path} Transcribed audio to: {transcription}")
            return transcription[0].text

# Global instance for convenience
transcribe_instance = get_transcribe_instance()
transcribe_voice = transcribe_instance.transcribe_voice
