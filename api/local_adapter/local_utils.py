"""
Utility functions for local model operations.
"""

import logging
from typing import Optional, Union, Tuple
import torch
import numpy as np
from urllib.parse import urlparse
import requests
import soundfile as sf
import io

logger = logging.getLogger(__name__)

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
    Convert a numpy array to MP3 bytes using soundfile.
    
    Args:
        audio_array: Numpy array containing audio samples
        sample_rate: Sample rate of the audio
        bitrate: Bitrate for the output MP3 (e.g., "128k", "192k")
        
    Returns:
        bytes: MP3 audio data as bytes
        
    Raises:
        Exception: For any conversion errors
    """
    try:
       
        # Ensure audio_array is in the correct format (mono, 16-bit PCM)
        if audio_array.dtype != np.int16:
            # Normalize to 16-bit range
            audio_array = (audio_array * (2**15 - 1)).astype(np.int16)
        
        # Convert numpy array to bytes
        audio_bytes = audio_array.tobytes()
        
        # Export to MP3 in memory
        with io.BytesIO() as mp3_buffer:
            sf.write(mp3_buffer, audio_bytes, sample_rate, format='MP3', subtype='MP3')
            return mp3_buffer.getvalue()
            
    except Exception as e:
        logger.error(f"Error converting to MP3: {str(e)}")
        raise


def log_model_outputs(self, outputs, audio_array_tensor, text):
    """Log detailed information about model outputs for debugging.
    
    Args:
        outputs: Raw outputs from the model
        audio_array_tensor: Processed audio tensor from batch_decode
        text: Input text that was processed
    """
    import json
    from io import StringIO
    
    logger.info(f"Synthesizing speech for text: {text[:50]}...")
    logger.debug(f"Output type: {type(outputs)}")
    
    # Log raw outputs
    output_buffer = StringIO()
    json.dump(str(outputs), output_buffer, indent=2, ensure_ascii=False)
    logger.debug(f"Raw outputs (first 1000 chars): {output_buffer.getvalue()[:1000]}")
    
    # Log audio tensor info
    logger.debug(f"Audio array tensor type: {type(audio_array_tensor)}")
    logger.debug(f"Audio tensor shape: {getattr(audio_array_tensor, 'shape', 'N/A')}")
    
    # Log audio tensor values (first few elements)
    if hasattr(audio_array_tensor, 'flatten'):
        flat_tensor = audio_array_tensor.flatten()
        sample_values = flat_tensor[:5].tolist() if hasattr(flat_tensor, 'tolist') else flat_tensor[:5]
        logger.debug(f"First 5 audio values: {sample_values}")

def save_debug_sound(self, outputs, audio_array):
    """
    Save debug audio files in both WAV and MP3 formats.
    
    Args:
        outputs: Raw model outputs
        audio_array: Processed audio array to save
    """
    try:
        import os
        from datetime import datetime
        import uuid
        
        # Create debug directory if it doesn't exist
        debug_dir = os.path.join(os.path.dirname(__file__), "..", "..", "debug_audio")
        os.makedirs(debug_dir, exist_ok=True)
        
        # Generate unique filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        unique_id = str(uuid.uuid4())[:8]
        base_filename = f"debug_audio_{timestamp}_{unique_id}"
        
        # File paths
        wav_path = os.path.join(debug_dir, f"{base_filename}.wav")
        mp3_path = os.path.join(debug_dir, f"{base_filename}.mp3")
        try:
            # Save files                
            sf.write(mp3_path, audio_array, self.sample_rate, format='MP3')
            sf.write(wav_path, audio_array, self.sample_rate)
            logger.info(f"Saved debug WAV file: {wav_path}")
            logger.info(f"Saved debug MP3 file: {mp3_path}")
        except Exception as e:
            logger.error(f"Error saving MP3 file: {str(e)}")
            
        # Save raw outputs if they exist
        if outputs is not None:
            try:
                output_path = os.path.join(debug_dir, f"{base_filename}_raw_outputs.pt")
                torch.save(outputs, output_path)
                logger.info(f"Saved raw model outputs: {output_path}")
            except Exception as e:
                logger.error(f"Error saving raw outputs: {str(e)}")
                
    except Exception as e:
        logger.error(f"Error in _save_debug_sound: {str(e)}", exc_info=True)


