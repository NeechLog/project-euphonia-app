import os
import logging
import threading
import atexit
from typing import Optional, Tuple, Union

import torch
import numpy as np
from transformers import AutoProcessor, AutoModelForConditionalGeneration

# Configure logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('dia_tts.log')
    ]
)
logger = logging.getLogger(__name__)

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
        self.sample_rate = 44100
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
        text_to_speak: str,
        audio_prompt :str | torch.Tensor | None = None,
        clone_from_text :str = None,
        max_new_tokens: int = 16384,
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
                    start_time = time.time()
                    if(audio_prompt):
                        inputs = self.processor(text=clone_from_text+text_to_speak, audio_prompt = audio_prompt, padding=True, return_tensors="pt").to(self.device)
                    else:
                        inputs = self.processor(text = text_to_speak, padding=True, return_tensors="pt").to(self.device)
                    outputs = self.model.generate(**inputs, max_new_tokens = max_new_tokens, guidance_scale = guidance_scale, temperature = temperature, top_p = top_p, top_k = top_k)
                    end_time = time.time()
                    execution_time = end_time - start_time
                    logger.info(f"Model outputs in {execution_time:.2f} seconds")
                    audio_array_tensor = self.processor.batch_decode(outputs)
                    end_time = time.time()
                    execution_time = end_time - start_time
                    logger.info(f"Model and audio array tensor decoding in {execution_time:.2f} seconds")
     
                    log_model_outputs(outputs, audio_array_tensor, text_to_speak)
                    save_debug_sound([outputs,audio_array], sample_rate=self.sample_rate)


                    if(isinstance(audio_array_tensor, torch.Tensor)):
                        audio_array = audio_array_tensor.cpu().numpy()
                        logger.debug(f"Audio array type: {type(audio_array)}")
                    elif(isinstance(audio_array_tensor, np.ndarray)):  
                        audio_array = audio_array_tensor
                        logger.debug(f"Audio array type: {type(audio_array)}")
                    elif(isinstance(audio_array_tensor, list)):
                        audio_array = audio_array_tensor[0].cpu().numpy()
                        logger.debug(f"Audio array type: {type(audio_array)}")
                    return audio_array, self.sample_rate 
                except Exception as e:
                    logger.error(f"Speech synthesis failed: {str(e)}")
                    raise
