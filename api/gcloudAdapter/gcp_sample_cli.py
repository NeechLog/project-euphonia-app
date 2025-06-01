#!/usr/bin/env python3
"""
GCP Sample Manager - A command-line utility for managing voice and text samples in Google Cloud Storage
and interacting with the Dia text-to-speech model on Google Cloud Vertex AI.

This script provides commands to:
- Upload and download voice/text sample pairs to/from GCS
- Generate speech using the Dia text-to-speech model
- Clone voices from existing samples
"""

import argparse
import base64
import json
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

from google.cloud import aiplatform
from gcp_storage import upload_or_update_data_gcs, download_data_from_gcs, get_oldest_blob_pairs
from gcp_models import (
    call_vertex_Dia_model,
    synthesize_speech_with_cloned_voice,
    PROJECT_ID,
    REGION,
    ENDPOINT_ID,
    config_SCALE_PARAM,
    TEMPERATURE_PARAM,
    TOP_P_PARAM
)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Vertex AI
try:
    #ensure_gcloud_credentials()
    aiplatform.init(project=PROJECT_ID, location=REGION)
    endpoint = aiplatform.Endpoint(endpoint_name=ENDPOINT_ID)
    logger.info(f"Successfully initialized Vertex AI endpoint: {endpoint.resource_name}")
except Exception as e:
    logger.error(f"Failed to initialize Vertex AI endpoint: {e}")
    endpoint = None

# Default configuration
DEFAULT_BUCKET = "euphonia-dia"
ENV_BUCKET_VAR = "EUPHONIA_DIA_GCS_BUCKET"

def ensure_gcloud_credentials() -> bool:
    """
    Checks if Google Cloud credentials are loaded via environment variable.
    If not, attempts to set it using the default path for application default credentials.
    Logs the status of the GOOGLE_APPLICATION_CREDENTIALS environment variable.
    
    Returns:
        bool: True if valid credentials are found or set, False otherwise
    """
    env_var_name = "GOOGLE_APPLICATION_CREDENTIALS"
    creds_path = os.environ.get(env_var_name)
    
    if creds_path:
        logger.info(f"Using credentials from: {creds_path}")
        if not os.path.exists(creds_path):
            logger.warning(f"Warning: Credentials file does not exist: {creds_path}")
        return True
    
    # Try to use default application credentials
    default_creds_path = os.path.expanduser('~/.config/gcloud/application_default_credentials.json')
    if os.path.exists(default_creds_path):
        os.environ[env_var_name] = default_creds_path
        logger.info(f"Using default application credentials from: {default_creds_path}")
        return True
    
    logger.warning("No Google Cloud credentials found. Please set GOOGLE_APPLICATION_CREDENTIALS environment variable or run 'gcloud auth application-default login'")
    return False



def upload_sample_pair(
    bucket_name: str,
    hash_id: str,
    text_file: str,
    voice_file: str,
    random_num: Optional[int] = None
) -> Tuple[bool, str]:
    """Upload a text and voice sample pair to GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
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
        
        # Upload using gcp_storage
        text_url, voice_url = upload_or_update_data_gcs(
            bucket_name=bucket_name,
            hash_identifier=hash_id,
            text_data=text_content,
            voice_data_bytes=voice_content,
            random_num=random_num,
            text_filename=os.path.basename(text_file),
            audio_filename=os.path.basename(voice_file)
        )
        
        if text_url and voice_url:
            return True, f"Successfully uploaded sample pair. Text: {text_url}, Voice: {voice_url}"
        else:
            return False, "Failed to upload sample pair"
            
    except Exception as e:
        return False, f"Upload failed: {str(e)}"


def download_sample_pair(
    bucket_name: str,
    hash_id: str,
    output_dir: str = ".",
    random_num: Optional[int] = None
) -> Tuple[bool, str]:
    """Download a text and voice sample pair from GCS.
    
    Args:
        bucket_name: Name of the GCS bucket
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
        
        # Get the data using gcp_storage
        text_data, text_blob_name, voice_data, voice_blob_name = download_data_from_gcs(
            bucket_name=bucket_name,
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


def list_samples(bucket_name: str, hash_id: str) -> Tuple[bool, str]:
    """List available sample pairs for a specific hash ID in the bucket.
    
    Args:
        bucket_name: Name of the GCS bucket
        hash_id: Hash ID to list versions for
        
    Returns:
        Tuple of (success, message)
    """
    try:
        # List samples for the specified hash ID
        blob_pairs = get_oldest_blob_pairs(bucket_name, hash_id)
        
        if not blob_pairs:
            return True, f"No samples found for hash: {hash_id}"
        
        # Format the output
        output = [f"\nSamples for hash '{hash_id}':"]
        for pair in blob_pairs:
            output.append(f"\nSuffix: {pair['suffix']}")
            output.append(f"  Text URL:  {pair['text_url']}")
            output.append(f"  Voice URL: {pair['voice_url']}")
        
        return True, "\n".join(output)
        
    except Exception as e:
        return False, f"Failed to list samples: {str(e)}"


def get_bucket_name(args_bucket: Optional[str] = None) -> str:
    """Get bucket name from args or environment variable."""
    if args_bucket:
        return args_bucket
    
    bucket_name = os.environ.get(ENV_BUCKET_VAR)
    if not bucket_name:
        print(f"Warning: Using default bucket name '{DEFAULT_BUCKET}'. "
              f"Set {ENV_BUCKET_VAR} environment variable to override.",
              file=sys.stderr)
        bucket_name = DEFAULT_BUCKET
    
    return bucket_name


def generate_speech(
    text: str,
    output_file: str,
    config_scale: float = config_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM
) -> Tuple[bool, str]:
    """Generate speech from text using the Dia model.
    
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
        logger.info(f"Generating speech for text: {text[:100]}...")
        audio_data = call_vertex_Dia_model(
            input_text=text,
            config_scale=config_SCALE_PARAM,
            temperature=temperature,
            top_p=top_p
        )
        
        if audio_data:
            with open(output_file, 'wb') as f:
                f.write(audio_data)
            return True, f"Successfully generated speech and saved to {output_file}"
        else:
            return False, "Failed to generate speech: No audio data returned"
    except Exception as e:
        return False, f"Speech generation failed: {str(e)}"


def clone_voice(
    text: str,
    audio_gcs_url: str,
    transcript: str,
    output_file: str,
    config_scale: float = config_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM
) -> Tuple[bool, str]:
    """Generate speech with a cloned voice.
    
    Args:
        text: Text to convert to speech
        audio_gcs_url: GCS URL to the audio file to clone voice from
        transcript: Transcript of the audio file
        output_file: Path to save the generated audio
        config_scale: Configuration scale parameter
        temperature: Temperature parameter for generation
        top_p: Top-p sampling parameter
        
    Returns:
        Tuple of (success, message)
    """
    try:
        logger.info(f"Cloning voice from {audio_gcs_url}...")
        audio_data = synthesize_speech_with_cloned_voice(
            text_to_synthesize=text,
            clone_from_audio_gcs_url=audio_gcs_url,
            clone_from_text_transcript=transcript,
            config_scale=config_scale,
            temperature=temperature,
            top_p=top_p
        )
        
        if audio_data:
            with open(output_file, 'wb') as f:
                f.write(audio_data)
            return True, f"Successfully generated speech with cloned voice and saved to {output_file}"
        else:
            return False, "Failed to generate speech: No audio data returned"
    except Exception as e:
        return False, f"Voice cloning failed: {str(e)}"


def main():
    """Main entry point for the command-line interface.
    
    Examples:
        # Upload a sample pair
        gcp_sample_cli.py upload sample123 transcript.txt recording.wav
        
        # Upload with a specific random number
        gcp_sample_cli.py upload sample123 transcript.txt recording.wav --random 123456
        
        # Download the latest version of a sample
        gcp_sample_cli.py download sample123 --output-dir ./downloads
        
        # Download a specific version
        gcp_sample_cli.py download sample123 --random 123456
        
        # List all available hash IDs
        gcp_sample_cli.py list
        
        # List versions for a specific hash ID
        gcp_sample_cli.py list sample123
        
        # Generate speech from text
        gcp_sample_cli.py generate "Hello, world!" output.wav
        
        # Generate speech with custom parameters
        gcp_sample_cli.py generate "Hello, world!" output.wav --temperature 0.8 --top-p 0.9
        
        # Clone a voice from a GCS audio file
        gcp_sample_cli.py clone-voice "Hello, world!" gs://bucket/audio.wav "Transcription" output.wav
    """
    parser = argparse.ArgumentParser(
        description='''Manage voice samples and generate speech using Google Cloud services.
        
This tool provides commands to manage voice samples in Google Cloud Storage and interact with
the Dia text-to-speech model on Google Cloud Vertex AI.
        ''',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Environment Variables:
  EUPHONIA_DIA_GCS_BUCKET  Default GCS bucket if --bucket is not provided
  GOOGLE_APPLICATION_CREDENTIALS  Path to service account key file for authentication
        '''
    )
    
    # Common arguments
    parser.add_argument(
        '--bucket',
        help='GCS bucket name (default: from EUPHONIA_DIA_GCS_BUCKET env var or euphonia-dia)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )
    
    # Create subparsers for different commands
    subparsers = parser.add_subparsers(
        dest='command',
        help='Command to run',
        required=False,  # Make subparsers optional to show help by default
        title='commands',
        description='Available commands:'
    )
    
    # Add a default help action when no command is provided
    parser.set_defaults(func=lambda _: parser.print_help())
    
    # Upload command
    upload_parser = subparsers.add_parser(
        'upload',
        help='Upload a text and voice sample pair',
        description='Upload a text file and its corresponding voice sample to GCS.',
        epilog='''Examples:
  # Basic upload
  %(prog)s --bucket my-bucket sample123 transcript.txt recording.wav
  
  # Upload with specific random number
  %(prog)s --bucket my-bucket sample123 transcript.txt recording.wav --random 123456
        '''
    )
    upload_parser.add_argument('hash_id', help='Unique identifier for the sample pair')
    upload_parser.add_argument('text_file', help='Path to the text file')
    upload_parser.add_argument('voice_file', help='Path to the voice file')
    upload_parser.add_argument('--random', type=int, help='Optional random number for the upload')
    
    # Download command
    download_parser = subparsers.add_parser(
        'download',
        help='Download a text and voice sample pair',
        description='Download a text file and its corresponding voice sample from GCS.',
        epilog='''Examples:
  # Download latest version to current directory
  %(prog)s --bucket my-bucket sample123
  
  # Download to specific directory
  %(prog)s --bucket my-bucket sample123 --output-dir ./downloads
  
  # Download specific version
  %(prog)s --bucket my-bucket sample123 --random 123456
        '''
    )
    download_parser.add_argument('hash_id', help='Unique identifier for the sample pair')
    download_parser.add_argument('--output-dir', default='.', help='Directory to save downloaded files')
    download_parser.add_argument('--random', type=int, help='Optional random number for specific version')
    
    # List command
    list_parser = subparsers.add_parser(
        'list',
        help='List versions of a specific sample',
        description='List all versions of a specific sample in the bucket.',
        epilog='''Examples:
  # List all versions of a specific sample
  %(prog)s --bucket my-bucket sample123
        '''
    )
    list_parser.add_argument('hash_id', help='Hash ID of the sample to list versions for')
    
    # Generate speech command
    generate_parser = subparsers.add_parser(
        'generate',
        help='Generate speech from text',
        description='Generate speech from text using the default voice model.',
        epilog='''Examples:
  # Basic text-to-speech generation
  %(prog)s "Hello, world!" output.wav
  
  # With custom parameters
  %(prog)s "Hello, world!" output.wav --temperature 0.7 --top-p 0.9
        '''
    )
    generate_parser.add_argument('text', help='Text to convert to speech')
    generate_parser.add_argument('output_file', help='Path to save the generated audio')
    generate_parser.add_argument('--config-scale', type=float, default=config_SCALE_PARAM,
                                help=f'Configuration scale (default: {config_SCALE_PARAM})')
    generate_parser.add_argument('--temperature', type=float, default=TEMPERATURE_PARAM,
                                help=f'Temperature for generation (default: {TEMPERATURE_PARAM})')
    generate_parser.add_argument('--top-p', type=float, default=TOP_P_PARAM,
                                help=f'Top-p sampling (default: {TOP_P_PARAM})')
    
    # Clone voice command
    clone_parser = subparsers.add_parser(
        'clone-voice',
        help='Clone voice from a sample',
        description='Generate speech in a voice similar to the provided audio sample.',
        epilog='''Examples:
  # Basic voice cloning
  %(prog)s "Hello, world!" gs://my-bucket/voice_samples/sample1.wav "This is a test recording." output.wav
  
  # With custom parameters
  %(prog)s "Hello, world!" gs://my-bucket/voice_samples/sample1.wav \
    "This is a test recording." output.wav --temperature 0.7 --top-p 0.9
        '''
    )
    clone_parser.add_argument('text', help='Text to convert to speech')
    clone_parser.add_argument('audio_gcs_url', help='GCS URL to the audio file to clone voice from')
    clone_parser.add_argument('transcript', help='Transcript of the audio file')
    clone_parser.add_argument('output_file', help='Path to save the generated audio')
    clone_parser.add_argument('--config-scale', type=float, default=config_SCALE_PARAM,
                            help=f'Configuration scale (default: {config_SCALE_PARAM})')
    clone_parser.add_argument('--temperature', type=float, default=TEMPERATURE_PARAM,
                            help=f'Temperature for generation (default: {TEMPERATURE_PARAM})')
    clone_parser.add_argument('--top-p', type=float, default=TOP_P_PARAM,
                            help=f'Top-p sampling (default: {TOP_P_PARAM})')
    
    
    # Parse arguments and execute command
    args = parser.parse_args()
    
    # Set up logging level
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # Execute the appropriate command or show help
    try:
        if not hasattr(args, 'command') or args.command is None:
            parser.print_help()
            sys.exit(0)
            
        if args.command == 'upload':
            bucket_name = get_bucket_name(args.bucket)
            success, message = upload_sample_pair(
                bucket_name=bucket_name,
                hash_id=args.hash_id,
                text_file=args.text_file,
                voice_file=args.voice_file,
                random_num=args.random
            )
        elif args.command == 'download':
            bucket_name = get_bucket_name(args.bucket)
            success, message = download_sample_pair(
                bucket_name=bucket_name,
                hash_id=args.hash_id,
                output_dir=args.output_dir,
                random_num=args.random
            )
        elif args.command == 'list':
            bucket_name = get_bucket_name(args.bucket)
            success, message = list_samples(bucket_name, args.hash_id)
        elif args.command == 'generate':
            if endpoint is None:
                logger.error("Failed to initialize Vertex AI endpoint for generate command. Check your configuration and ensure Vertex AI API is enabled.")
                sys.exit(1)
            success, message = generate_speech(
                text=args.text,
                output_file=args.output_file,
                config_scale=args.config_scale,
                temperature=args.temperature,
                top_p=args.top_p
            )
        elif args.command == 'clone-voice':
            if endpoint is None:
                logger.error("Failed to initialize Vertex AI endpoint for clone-voice command. Check your configuration and ensure Vertex AI API is enabled.")
                sys.exit(1)
            success, message = clone_voice(
                text=args.text,
                audio_gcs_url=args.audio_gcs_url,
                transcript=args.transcript,
                output_file=args.output_file,
                config_scale=args.config_scale,
                temperature=args.temperature,
                top_p=args.top_p
            )
        else:
            success, message = False, f"Unknown command: {args.command}"
        
        # Print the result
        if success:
            print(message)
        else:
            print(f"Error: {message}", file=sys.stderr)
            sys.exit(1)
            
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
