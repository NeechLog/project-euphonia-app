#!/usr/bin/env python3
"""
Local Sample Manager - A command-line utility for managing voice and text samples locally
and interacting with the local Dia text-to-speech model.

This script provides commands to:
- Upload and download voice/text sample pairs to/from local storage
- Generate speech using the local Dia text-to-speech model
- Clone voices from existing samples
"""

import debugpy
debugpy.listen(("0.0.0.0", 5678))
debugpy.wait_for_client()
import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Local imports
from local_storage import (
    upload_or_update_data_local,
    download_data_from_local,
    get_oldest_blob_pairs,
    list_all_hash_identifiers,
    get_oldest_training_data
)
from local_model import (
    synthesize_speech_with_cloned_voice,
    call_vertex_Dia_model
)

# Default configuration
DEFAULT_BASE_DIR = os.path.join(os.path.dirname(__file__), "..", "/Users/gagan/projects/work/samples/")

def upload_sample_pair(
    base_dir: str,
    hash_id: str,
    text_file: str,
    voice_file: str,
    random_num: Optional[int] = None
) -> Tuple[bool, str]:
    """Upload a text and voice sample pair to local storage.
    
    Args:
        base_dir: Base directory for storage
        hash_id: Unique identifier for the sample pair
        text_file: Path to the text file
        voice_file: Path to the voice file
        random_num: Optional random number for the upload (auto-generated if None)
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Read files
        text_content = Path(text_file).read_text(encoding='utf-8')
        voice_content = Path(voice_file).read_bytes()
        
        # Upload using local_storage
        text_url, voice_url = upload_or_update_data_local(
            base_dir=base_dir,
            hash_identifier=hash_id,
            text_data=text_content,
            voice_data_bytes=voice_content,
            random_num=random_num,
            text_filename=os.path.basename(text_file),
            audio_filename=os.path.basename(voice_file)
        )
        
        if text_url and voice_url:
            return True, f"Successfully uploaded sample pair.\n  Text: {text_url}\n  Voice: {voice_url}"
        else:
            return False, "Failed to upload sample pair"
            
    except Exception as e:
        return False, f"Upload failed: {str(e)}"

def download_sample_pair(
    base_dir: str,
    hash_id: str,
    output_dir: str = ".",
    random_num: Optional[int] = None
) -> Tuple[bool, str]:
    """Download a text and voice sample pair from local storage.
    
    Args:
        base_dir: Base directory for storage
        hash_id: Unique identifier for the sample pair
        output_dir: Directory to save downloaded files (default: current directory)
        random_num: Optional random number to identify specific sample pair
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Prepare output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Get the data using local_storage
        text_data, text_blob_name, voice_data, voice_blob_name = download_data_from_local(
            base_dir=base_dir,
            hash_identifier=hash_id,
            random_num=random_num
        )
        
        if not text_data or not voice_data or not text_blob_name or not voice_blob_name:
            return False, f"Failed to download data for hash: {hash_id}"
        
        # Extract filenames from blob names
        text_filename = Path(text_blob_name).name
        voice_filename = Path(voice_blob_name).name
        
        # Save the files with their original names
        text_file = output_path / text_filename
        voice_file = output_path / voice_filename
        
        with open(text_file, 'w', encoding='utf-8') as f:
            f.write(text_data)
            
        with open(voice_file, 'wb') as f:
            f.write(voice_data)
        
        return True, f"Successfully downloaded files to {output_path}:\n  - {text_filename}\n  - {voice_filename}"
        
    except Exception as e:
        return False, f"Download failed: {str(e)}"

def list_samples(base_dir: str, hash_id: str) -> Tuple[bool, str]:
    """List available sample pairs for a specific hash ID in the storage.
    
    Args:
        base_dir: Base directory for storage
        hash_id: Hash ID to list versions for
        
    Returns:
        Tuple of (success, message)
    """
    try:
        pairs = get_oldest_blob_pairs(base_dir, hash_id)
        if not pairs:
            return False, f"No samples found for hash: {hash_id}"
            
        result = [f"Available samples for {hash_id}:"]
        for i, pair in enumerate(pairs, 1):
            result.append(f"{i}. Text: {pair.get('text_url', 'N/A')}")
            result.append(f"   Voice: {pair.get('voice_url', 'N/A')}")
            
        return True, "\n".join(result)
        
    except Exception as e:
        return False, f"Failed to list samples: {str(e)}"

def list_all_hashes(base_dir: str) -> Tuple[bool, str]:
    """List all unique hash identifiers in the specified storage directory."""
    try:
        hashes = list_all_hash_identifiers(base_dir)
        if not hashes:
            return False, "No hash identifiers found in storage."
            
        return True, "Available hash identifiers:\n" + "\n".join(f"- {h}" for h in hashes)
        
    except Exception as e:
        return False, f"Failed to list hash identifiers: {str(e)}"

def generate_speech(
    text: str,
    output_file: str,
    config_scale: float = 0.3,
    temperature: float = 1.3,
    top_p: float = 0.95
) -> Tuple[bool, str]:
    """Generate speech from text using the local Dia model.
    
    Args:
        text: The text to convert to speech
        output_file: Path to save the generated audio
        config_scale: Configuration scale parameter
        temperature: Temperature parameter for generation
        top_p: Top-p sampling parameter
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Call the local model function
        audio_data = call_vertex_Dia_model(
            text=text,
            config_scale=config_scale,
            temperature=temperature,
            top_p=top_p
        )
        
        if not audio_data:
            return False, "Failed to generate speech: No audio data returned"
            
        # Save the audio file
        with open(output_file, 'wb') as f:
            f.write(audio_data)
            
        return True, f"Successfully generated speech and saved to {output_file}"
        
    except Exception as e:
        return False, f"Speech generation failed: {str(e)}"

def clone_voice(
    text: str,
    audio_file: str,
    transcript: str,
    output_file: str,
    config_scale: float = 0.3,
    temperature: float = 1.3,
    top_p: float = 0.95
) -> Tuple[bool, str]:
    """Generate speech with a cloned voice from a local audio file.
    
    Args:
        text: Text to convert to speech
        audio_file: Path to the audio file to clone voice from
        transcript: Transcript of the audio file
        output_file: Path to save the generated audio
        config_scale: Configuration scale parameter
        temperature: Temperature parameter for generation
        top_p: Top-p sampling parameter
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # Call the local voice cloning function
        audio_data = synthesize_speech_with_cloned_voice(
            text_to_synthesize=text,
            clone_from_audio_gcs_url=audio_file,  # Using local path directly
            clone_from_text_transcript=transcript,
            config_scale=config_scale,
            temperature=temperature,
            top_p=top_p
        )
        
        if not audio_data:
            return False, "Failed to clone voice: No audio data returned"
            
        # Save the audio file
        with open(output_file, 'wb') as f:
            f.write(audio_data)
            
        return True, f"Successfully generated speech with cloned voice and saved to {output_file}"
        
    except Exception as e:
        return False, f"Voice cloning failed: {str(e)}"

def get_base_dir(args_base_dir: Optional[str] = None) -> str:
    """Get base directory from args or use default."""
    if args_base_dir:
        return args_base_dir
    return os.environ.get("LOCAL_STORAGE_DIR", DEFAULT_BASE_DIR)

def main():
    """Main entry point for the command-line interface."""
    parser = argparse.ArgumentParser(description="Local Sample Manager for Dia TTS")
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    # Upload command
    upload_parser = subparsers.add_parser('upload', help='Upload a sample pair')
    upload_parser.add_argument('hash_id', help='Unique identifier for the sample pair')
    upload_parser.add_argument('text_file', help='Path to the text file')
    upload_parser.add_argument('voice_file', help='Path to the voice file')
    upload_parser.add_argument('--random', type=int, help='Random number for the upload')
    upload_parser.add_argument('--base-dir', help='Base directory for storage')
    
    # Download command
    download_parser = subparsers.add_parser('download', help='Download a sample pair')
    download_parser.add_argument('hash_id', help='Unique identifier for the sample pair')
    download_parser.add_argument('--output-dir', default='.', help='Directory to save downloaded files')
    download_parser.add_argument('--random', type=int, help='Random number of the specific version to download')
    download_parser.add_argument('--base-dir', help='Base directory for storage')
    
    # List command
    list_parser = subparsers.add_parser('list', help='List sample versions')
    list_parser.add_argument('hash_id', help='Hash ID to list versions for')
    list_parser.add_argument('--base-dir', help='Base directory for storage')
    
    # List hashes command
    list_hashes_parser = subparsers.add_parser('list-hashes', help='List all hash identifiers')
    list_hashes_parser.add_argument('--base-dir', help='Base directory for storage')
    
    # Generate command
    generate_parser = subparsers.add_parser('generate', help='Generate speech from text')
    generate_parser.add_argument('text', help='Text to convert to speech')
    generate_parser.add_argument('output_file', help='Path to save the generated audio')
    generate_parser.add_argument('--config-scale', type=float, default=0.3, help='Configuration scale parameter')
    generate_parser.add_argument('--temperature', type=float, default=1.3, help='Temperature parameter')
    generate_parser.add_argument('--top-p', type=float, default=0.95, help='Top-p sampling parameter')
    
    # Clone voice command
    clone_parser = subparsers.add_parser('clone-voice', help='Generate speech with a cloned voice')
    clone_parser.add_argument('text', help='Text to convert to speech')
    clone_parser.add_argument('audio_file', help='Path to the audio file to clone voice from')
    clone_parser.add_argument('transcript', help='Transcript of the audio file')
    clone_parser.add_argument('output_file', help='Path to save the generated audio')
    clone_parser.add_argument('--config-scale', type=float, default=0.3, help='Configuration scale parameter')
    clone_parser.add_argument('--temperature', type=float, default=1.3, help='Temperature parameter')
    clone_parser.add_argument('--top-p', type=float, default=0.95, help='Top-p sampling parameter')
    
    args = parser.parse_args()
    
    try:
        base_dir = get_base_dir(getattr(args, 'base_dir', None))
        
        if args.command == 'upload':
            success, message = upload_sample_pair(
                base_dir=base_dir,
                hash_id=args.hash_id,
                text_file=args.text_file,
                voice_file=args.voice_file,
                random_num=args.random
            )
            
        elif args.command == 'download':
            success, message = download_sample_pair(
                base_dir=base_dir,
                hash_id=args.hash_id,
                output_dir=args.output_dir,
                random_num=args.random
            )
            
        elif args.command == 'list':
            success, message = list_samples(
                base_dir=base_dir,
                hash_id=args.hash_id
            )
            
        elif args.command == 'list-hashes':
            success, message = list_all_hashes(
                base_dir=base_dir
            )
            
        elif args.command == 'generate':
            success, message = generate_speech(
                text=args.text,
                output_file=args.output_file,
                config_scale=args.config_scale,
                temperature=args.temperature,
                top_p=args.top_p
            )
            
        elif args.command == 'clone-voice':
            success, message = clone_voice(
                text=args.text,
                audio_file=args.audio_file,
                transcript=args.transcript,
                output_file=args.output_file,
                config_scale=args.config_scale,
                temperature=args.temperature,
                top_p=args.top_p
            )
            
        else:
            parser.print_help()
            return
            
        if success:
            logger.info(message)
        else:
            logger.error(message)
            sys.exit(1)
            
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()
