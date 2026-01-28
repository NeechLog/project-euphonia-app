import logging
import os
import traceback
from typing import Optional, Union
import grpc
from audiocloneclient.client import AudioCloneClient
from audiocloneclient import clone_interface_pb2
from audiomessages import AudioMessage

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DEFAULT_VIBEVASERVER_ADDRESS = "localhost:50051"
GUIDANCE_SCALE_PARAM = 4.0
TEMPERATURE_PARAM = 1.8
TOP_P_PARAM = 0.95

def get_vibevaserver_client() -> AudioCloneClient:
    """
    Initialize and return a gRPC client for vibeVAServer.
    
    Returns:
        AudioCloneClient: Configured gRPC client instance
    """
    server_address = os.getenv('VIBEVASERVER_ADDRESS', DEFAULT_VIBEVASERVER_ADDRESS)
    
    try:
        # Create gRPC client
        client = AudioCloneClient(server_address)
        
        logger.info(f"Connected to vibeVAServer at {server_address}")
        return client
        
    except Exception as e:
        logger.error(f"Failed to connect to vibeVAServer at {server_address}: {str(e)}")
        raise

def synthesize_speech_with_cloned_voice(
    text_to_synthesize: str,
    clone_from_audio_gcs_url: str,
    clone_from_text_transcript: str,
    config_scale: float = 3.0,
    temperature: float = 1.8,
    top_p: float = 0.90,
    use_streaming: bool = False
) -> bytes | None:
    """
    Generates speech audio by cloning a voice from an audio sample using remote vibeVAServer.
    
    This function routes voice cloning calls to vibeVAServer using audiocloneclient with gRPC.
    
    Args:
        text_to_synthesize: The text to be converted into speech.
        clone_from_audio_gcs_url: Path or URL to the audio file to clone the voice from.
        clone_from_text_transcript: The transcript of the audio provided for cloning.
        config_scale: Configuration scale for voice cloning (Default: 3.0).
        temperature: Controls randomness in generation. Higher is more random (Default: 1.8).
        top_p: Nucleus sampling parameter (Default: 0.90).
        use_streaming: Whether to use streaming interface (Default: False).
    
    Returns:
        bytes: Audio data in bytes if successful, otherwise None.
    """
    logger.info(
        f"Remote voice cloning synthesis requested. Text length: {len(text_to_synthesize)}, "
        f"Audio source: {clone_from_audio_gcs_url}, Streaming: {use_streaming}"
    )
    
    try:
        # Initialize the gRPC client
        client = get_vibevaserver_client()
        
        if use_streaming:
            return _handle_streaming_request(client, text_to_synthesize, clone_from_audio_gcs_url, clone_from_text_transcript)
        else:
            return _handle_unary_request(client, text_to_synthesize, clone_from_audio_gcs_url, clone_from_text_transcript)
            
    except grpc.RpcError as e:
        logger.error(f"gRPC error during voice cloning: {e.code()}, {e.details()}")
        raise
    except Exception as e:
        logger.error(f"Voice cloning failed: {str(e)}")
        error_trace = traceback.format_exc()
        logger.error(f"Stack trace:\n{error_trace}")
        raise

def _handle_unary_request(client, text_to_synthesize: str, clone_from_audio_gcs_url: str = None, clone_from_text_transcript: str = None) -> bytes | None:
    """Handle unary clone/synthesis request."""
    # Create the request
    request = clone_interface_pb2.CloneRequest()
    
    # Set request audio message with text to synthesize
    request.request_audio_message.text = text_to_synthesize
    
    # Set sample audio message (for cloning) or empty (for synthesis)
    if clone_from_audio_gcs_url and clone_from_text_transcript:
        # Voice cloning case
        request.sample_audio_message.audio_file_path = clone_from_audio_gcs_url
        request.sample_audio_message.text = clone_from_text_transcript
        logger.info("Setting up voice cloning with reference audio")
    else:
        # Regular synthesis case
        request.sample_audio_message.text = ""  # Empty for no cloning
        logger.info("Setting up regular voice synthesis (no cloning)")
    
    # Set model name
    request.model_name = "default-v1"
    
    logger.info("Sending unary request to vibeVAServer")
    
    # Send request to remote server
    response = client.clone(request)
    
    if response and response.cloned_audio_message and response.cloned_audio_message.audio_binary:
        logger.info(f"Successfully received {len(response.cloned_audio_message.audio_binary)} bytes of audio data")
        return response.cloned_audio_message.audio_binary
    else:
        logger.error("No audio data received from vibeVAServer")
        return None

def _handle_streaming_request(client, text_to_synthesize: str, clone_from_audio_gcs_url: str = None, clone_from_text_transcript: str = None) -> bytes | None:
    """Handle streaming clone/synthesis request."""
    logger.info("Sending streaming request to vibeVAServer")
    
    def request_generator():
        # Send the request with text and sample audio (if provided)
        request = clone_interface_pb2.CloneRequest()
        request.request_audio_message.text = text_to_synthesize
        
        if clone_from_audio_gcs_url and clone_from_text_transcript:
            # Voice cloning case
            request.sample_audio_message.audio_file_path = clone_from_audio_gcs_url
            request.sample_audio_message.text = clone_from_text_transcript
        else:
            # Regular synthesis case
            request.sample_audio_message.text = ""  # Empty for no cloning
        
        request.model_name = "default-v1"
        yield request
    
    # Collect all streaming responses
    audio_chunks = []
    try:
        responses = client.stream_clone(request_generator())
        for response in responses:
            if response and response.cloned_audio_message and response.cloned_audio_message.audio_binary:
                audio_chunks.append(response.cloned_audio_message.audio_binary)
                logger.info(f"Received audio chunk: {len(response.cloned_audio_message.audio_binary)} bytes")
        
        if audio_chunks:
            # Combine all chunks
            combined_audio = b''.join(audio_chunks)
            logger.info(f"Successfully combined {len(audio_chunks)} chunks, total size: {len(combined_audio)} bytes")
            return combined_audio
        else:
            logger.error("No audio data received from streaming responses")
            return None
            
    except grpc.RpcError as e:
        logger.error(f"Streaming gRPC error: {e.code()}, {e.details()}")
        raise

def call_voice_model(
    input_text: str,
    config_scale: float = GUIDANCE_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM,
    use_streaming: bool = False
) -> bytes | None:
    """
    Generates speech using the remote voice model on vibeVAServer.
    
    This function routes voice synthesis calls to vibeVAServer using audiocloneclient with gRPC.
    For regular voice synthesis (without cloning), we send null sample_audio_message.
    
    Args:
        input_text: The text to be converted into speech.
        config_scale: Configuration scale for voice synthesis (Default: 4.0).
        temperature: Controls randomness in generation. Higher is more random (Default: 1.8).
        top_p: Nucleus sampling parameter (Default: 0.95).
        use_streaming: Whether to use streaming interface (Default: False).
    
    Returns:
        bytes: Audio data in bytes if successful, otherwise None.
    """
    logger.info(f"Remote voice synthesis requested. Text length: {len(input_text)}, Streaming: {use_streaming}")
    
    try:
        # Initialize the gRPC client
        client = get_vibevaserver_client()
        
        if use_streaming:
            return _handle_streaming_request(client, input_text)
        else:
            return _handle_unary_request(client, input_text)
            
    except grpc.RpcError as e:
        logger.error(f"gRPC error during voice synthesis: {e.code()}, {e.details()}")
        raise
    except Exception as e:
        logger.error(f"Voice synthesis failed: {str(e)}")
        error_trace = traceback.format_exc()
        logger.error(f"Stack trace:\n{error_trace}")
        raise

if __name__ == "__main__":
    # Example usage
    try:
        # Test voice cloning (unary)
        cloned_audio = synthesize_speech_with_cloned_voice(
            text_to_synthesize="This is a test of the remote voice cloning system.",
            clone_from_audio_gcs_url="https://example.com/reference_audio.wav",
            clone_from_text_transcript="This is the reference audio transcript.",
            temperature=1.8,
            top_p=0.95,
            config_scale=3.0,
            use_streaming=False
        )
        
        if cloned_audio:
            logger.info(f"Voice cloning successful: {len(cloned_audio)} bytes")
        
        # Test voice synthesis (streaming)
        synthesized_audio = call_voice_model(
            input_text="This is a test of the remote voice synthesis system.",
            temperature=1.8,
            top_p=0.95,
            config_scale=4.0,
            use_streaming=True
        )
        
        if synthesized_audio:
            logger.info(f"Voice synthesis successful: {len(synthesized_audio)} bytes")
            
    except Exception as e:
        logger.error(f"Example usage failed: {str(e)}")
