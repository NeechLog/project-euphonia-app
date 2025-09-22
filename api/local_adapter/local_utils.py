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
import traceback

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

def convertNPArraytoMP3(audio_array, sample_rate=24000) -> bytes:
    """
    Convert a numpy array to MP3 bytes using pydub.
    
    Args:
        audio_array: NumPy array containing audio data
        sample_rate: Sample rate of the audio (default: 24000)
        
    Returns:
        bytes: MP3 audio data as bytes
        
    Raises:
        Exception: For any conversion errors
    """
    try:
        from pydub import AudioSegment
        import numpy as np
        
        # Ensure audio_array is 1D (mono)
        if len(audio_array.shape) > 1:
            audio_array = audio_array.squeeze()
            
        # Normalize to 16-bit range if needed
        if np.issubdtype(audio_array.dtype, np.floating):
            audio_array = (audio_array * 32767).astype(np.int16)
        elif audio_array.dtype != np.int16:
            audio_array = audio_array.astype(np.int16)
        
        # Create AudioSegment from numpy array
        audio_segment = AudioSegment(
            audio_array.tobytes(),
            frame_rate=sample_rate,
            sample_width=audio_array.dtype.itemsize,
            channels=1
        )
        
        # Export to MP3 in memory
        with io.BytesIO() as mp3_buffer:
            audio_segment.export(mp3_buffer, format="mp3", bitrate="128k")
            mp3_buffer.seek(0)
            return mp3_buffer.getvalue()
            
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in convertNPArraytoMP3: {str(e)}")
        logger.error(f"Audio array shape: {audio_array.shape if hasattr(audio_array, 'shape') else 'N/A'}")
        logger.error(f"Audio array dtype: {audio_array.dtype if hasattr(audio_array, 'dtype') else 'N/A'}")
        logger.error(f"Stack trace:\n{error_trace}")
        raise

def log_model_outputs(outputs, audio_array_tensor, text):
    """Log detailed information about model outputs for debugging.
    
    Args:
        outputs: Raw outputs from the model
        audio_array_tensor: Processed audio tensor from batch_decode
        text: Input text that was processed
    """
    try:
        import json
        from io import StringIO
        
        logger.info(f"Synthesizing speech for text: {text[:50]}...")
        logger.debug(f"Output type: {type(outputs)}")
        
        # Log raw outputs
        output_buffer = StringIO()
        json.dump(str(outputs), output_buffer, indent=2, ensure_ascii=False)
        logger.debug(f"Raw outputs (first 100000 chars): {output_buffer.getvalue()[:100000]}")
        if(audio_array_tensor):
            # Log audio tensor info
            logger.debug(f"Audio array tensor type: {type(audio_array_tensor)}")
            logger.debug(f"Audio tensor shape: {getattr(audio_array_tensor, 'shape', 'N/A')}")
            
            # Log audio tensor values (first few elements)
            if hasattr(audio_array_tensor, 'flatten'):
                flat_tensor = audio_array_tensor.flatten()
                sample_values = flat_tensor[:5].tolist() if hasattr(flat_tensor, 'tolist') else flat_tensor[:5]
                logger.debug(f"First 5 audio values: {sample_values}")
            
    except Exception as e:
        error_trace = traceback.format_exc()
        logger.error(f"Error in log_model_outputs: {str(e)}")
        logger.error(f"Stack trace:\n{error_trace}")


def save_debug_sound(audio_arrays, sample_rate=24000):
    """
    Save debug audio files in WAV, MP3, and PyTorch formats.
    
    Args:
        audio_arrays: Single numpy array or list of numpy arrays to save
        sample_rate: Sample rate of the audio (default: 24000)
    """
    try:
        import os
        import torch
        import soundfile as sf
        from pydub import AudioSegment
        import numpy as np
        from datetime import datetime
        
        # Create debug directory if it doesn't exist
        debug_dir = "debug_audio"
        os.makedirs(debug_dir, exist_ok=True)
        
        # Get current timestamp for unique filenames
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Convert single array to list for uniform processing
        if not isinstance(audio_arrays, (list, tuple)):
            audio_arrays = [audio_arrays]
            
        # Save each audio array
        for idx, audio_array in enumerate(audio_arrays):
            if not isinstance(audio_array, np.ndarray):
                logger.warning(f"Skipping non-array at index {idx}")
                continue
                
            # Generate base filename
            base_filename = f"audio_{timestamp}_{idx}"
            
            # Save as WAV
            wav_path = os.path.join(debug_dir, f"{base_filename}.wav")
            sf.write(wav_path, audio_array, sample_rate)
            
            # Save as MP3
            try:
                mp3_path = os.path.join(debug_dir, f"{base_filename}.mp3")
                audio_segment = AudioSegment(
                    audio_array.tobytes(),
                    frame_rate=sample_rate,
                    sample_width=audio_array.dtype.itemsize,
                    channels=1  # Assuming mono audio
                )
                audio_segment.export(mp3_path, format="mp3")
            except Exception as e:
                logger.error(f"Error saving MP3: {str(e)}")
            
            # Save as PyTorch tensor
            try:
                pt_path = os.path.join(debug_dir, f"{base_filename}.pt")
                torch.save(torch.from_numpy(audio_array), pt_path)
            except Exception as e:
                logger.error(f"Error saving PyTorch tensor: {str(e)}")
            
            logger.info(f"Saved debug audio files with prefix: {base_filename}")
            
    except Exception as e:
        logger.error(f"Error in save_debug_sound: {str(e)}", exc_info=True)
        error_trace = traceback.format_exc()
        logger.error(f"Error in saving files: {str(e)}")
        logger.error(f"Stack trace:\n{error_trace}")


