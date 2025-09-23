import logging
from typing import Optional, Tuple, Union, Dict, Any
import torch
import numpy as np
from pathlib import Path
import os
import threading
import atexit
import soundfile as sf
import time
from dataclasses import dataclass
from dia.model import Dia
from local_utils import log_model_outputs , save_debug_sound

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
SAMPLE_TEXT = "[S1] Dia is an open weights text to dialogue model. [S2] You get full control over scripts and voices. [S1] Wow. Amazing. (laughs) [S2] Try it now on Git hub or Hugging Face."
GUIDANCE_SCALE_PARAM = 3.0
TEMPERATURE_PARAM = 1.8
TOP_P_PARAM = 0.95
DEFAULT_SAMPLE_RATE = 44100

# Global instance and lock for thread-safe singleton
_tts_instance = None
_tts_lock = threading.Lock()

def get_tts_instance() -> 'Dia_Local_Wrapper':
    """Get or create a thread-safe singleton instance of Dia_Local_wrapper."""
    global _tts_instance
    
    if _tts_instance is None:
        with _tts_lock:
            if _tts_instance is None:
                logger.info("Initializing  Dia local model...")
                _tts_instance = Dia_Local_Wrapper()
                if not _tts_instance.load_model():
                    _tts_instance = None
                    raise RuntimeError("Failed to initialize Dia local model")
    return _tts_instance

def cleanup_tts_instance() -> None:
    """Clean up the global TTS instance and free resources."""
    global _tts_instance
    if _tts_instance is not None:
        logger.info("Cleaning up mock TTS instance...")
        _tts_instance = None

# Add cleanup on module unload
atexit.register(cleanup_tts_instance)


class Dia_Local_Wrapper:
    
    def __init__(self, model_path: Optional[str] = None, device: str = None):
        """Initialize the model."""
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        logger.info(f"Devie is {self.device}")
        dtype_map = {
            "cpu": "float32",
            "mps": "float32",  # Apple M series – better with float32
            "cuda": "float16",  # NVIDIA – better with float16
        }
        self.dtype = dtype_map.get(device, "float16")
        logger.info(f"Device type is {self.dtype}")
        self.model = None
        self.processor = None
        self.sample_rate = DEFAULT_SAMPLE_RATE
        self._lock = threading.Lock()

        
    def load_model(self) -> bool:
        
        with self._lock:
            if self.model is not None:
                return True
        logger.info("Loading mock DIA model...")
        self.model = Dia.from_pretrained("nari-labs/Dia-1.6B-0626", compute_dtype=self.dtype, device=self.device)
        logger.info(f"Model loaded {self.model}")
        return True
    
    def synthesize(
        self, 
        text_to_speak: str,
        audio_prompt: Union[str, torch.Tensor, None] = None,
        clone_from_text: str = None,
        max_new_tokens: int = 16384,
        guidance_scale: float = 3.0,
        temperature: float = 1.8,
        top_p: float = 0.90,
        top_k: int = 45,
        **kwargs
    ) -> Tuple[np.ndarray, int]:

       
            try:
                start_time = time.time()
                with self._lock:
                    if(audio_prompt):
                        outputs = self.model.generate(
                            text=clone_from_text+text_to_speak, 
                            audio_prompt=audio_prompt,
                            use_torch_compile=False, 
                            verbose=True,
                            cfg_scale=4.0,
                            temperature=1.8,
                            top_p=0.90,
                            cfg_filter_top_k=50
                        )
                    else:
                        outputs = self.model.generate(
                            text=text_to_speak,
                            use_torch_compile=False,
                            verbose=True,
                            cfg_scale=4.0,
                            temperature=1.8,
                            top_p=0.90,
                            cfg_filter_top_k=50
                        )
                end_time = time.time()
                execution_time = end_time - start_time
                logger.info(f"Model outputs in {execution_time:.2f} seconds")
                
                # Convert to numpy array, handling both tensor and numpy array cases
                # if isinstance(outputs, (list, tuple)) and len(outputs) > 0:
                #     audio_data = outputs[0]
                #     if hasattr(audio_data, 'cpu'):  # If it's a PyTorch tensor
                #         audio_array = audio_data.cpu().numpy()
                #     else:  # If it's already a numpy array
                #         audio_array = np.array(audio_data)
                # else:
                #     audio_array = np.array(outputs)  # Fallback for other cases
                
                # end_time = time.time()
                # execution_time = end_time - start_time
                # logger.info(f"Model and audio array tensor decoding in {execution_time:.2f} seconds")
                
                log_model_outputs(outputs=outputs, audio_array_tensor=None, text=text_to_speak)
                save_debug_sound([outputs], sample_rate=self.sample_rate)
                self.model.save_audio("damm_odd.mp3", outputs)
                return outputs, self.sample_rate
            except Exception as e:
                logger.error(f"Error in synthesize: {str(e)}", exc_info=True)
                raise
            

        

    
    
