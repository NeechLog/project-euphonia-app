import logging
import json
import base64
from google.cloud import aiplatform

# --- CONFIGURATION ---
PROJECT_ID = "673305860828"  # Replace with your Project ID
REGION = "us-central1"    # e.g., "us-central1"
ENDPOINT_ID = "5388067671474438144"    # Replace with your Endpoint ID
## Mark it True if vertex is up. But for only GCP_storage commands keep it false.
DIADeployed = True
SAMPLE_TEXT = "[S1] Dia is an open weights text to dialogue model. [S2] You get full control over scripts and voices. [S1] Wow. Amazing. (laughs) [S2] Try it now on Git hub or Hugging Face."
config_SCALE_PARAM = 0.3
TEMPERATURE_PARAM = 1.3
TOP_P_PARAM = 0.95

logger = logging.getLogger(__name__)
try:

    if(DIADeployed):
        aiplatform.init(project=PROJECT_ID, location=REGION)
        endpoint = aiplatform.Endpoint(endpoint_name=ENDPOINT_ID)
        logger.info(f"Successfully initialized endpoint: {endpoint.resource_name}")
except Exception as e:
    logger.error(f"Failed to initialize endpoint: {e}")
    raise

def extract_audio_from_response(response_text: str):
    """
    Extracts audio data from a JSON response text.
    Args:
        response_text (str): The JSON string response from the API
    Returns:
        str: The base64 encoded audio data from the first prediction
    Raises:
        ValueError: If the response doesn't contain the expected data structure
    """
    try:
        response_data = json.loads(response_text)
        return response_data["predictions"][0]["audio"]
    except (json.JSONDecodeError, KeyError, IndexError) as e:
        raise ValueError(f"Failed to extract audio data from response: {e}")

def call_vertex_Dia_model(
    input_text: str = SAMPLE_TEXT,
    config_scale: float = config_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM
) -> bytes | None:
    """
    Calls a Vertex AI custom model endpoint that expects text input and
    responds with binary voice data.
    Args:
        input_text (str): The text to be processed by the model.
        config_scale (float): Configuration scale parameter for the model.
        temperature (float): Temperature parameter for the model.
        top_p (float): Top_p parameter for the model.
    Returns:
        bytes | None: The binary voice data from the model response if successful,
                      otherwise None.
    Raises:
        Exception: If the API call fails or returns an unexpected status.
    """
    try:

        payload_dict = {
            "instances": [
                {"text": input_text}
            ],
            "parameters": {
                "config_scale": config_scale,
                "temperature": temperature,
                "top_p": top_p
            }
        }
        http_body = json.dumps(payload_dict).encode('utf-8')
        logger.info(f"Request payload (first 100 chars): {http_body[:100]}...")

        headers = {"Content-Type": "application/json"}
        logger.info("Sending prediction request to endpoint...")
        response = endpoint.raw_predict(body=http_body, headers=headers)
        logger.info(f"Received response with status code: {response.status_code}")
        logger.debug(f"Response payload: {response.text}")

        if response.status_code == 200:
            audio_data = extract_audio_from_response(response.text)
            binary_voice_data = base64.b64decode(audio_data)
            logger.info(f"Successfully received binary data of length: {len(binary_voice_data)} bytes.")
            return binary_voice_data
        else:
            error_message = f"Prediction failed with status code {response.status_code}: {response.text}"
            logger.error(error_message)
            raise Exception(error_message)

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise


# It's assumed that 'endpoint' is an object that has a .predict() method
# and is initialized elsewhere in your code.
# For example, if using Google Cloud Vertex AI:
# from google.cloud import aiplatform
# endpoint = aiplatform.Endpoint("projects/YOUR_PROJECT/locations/YOUR_LOCATION/endpoints/YOUR_ENDPOINT_ID")

def synthesize_speech_with_cloned_voice(
    text_to_synthesize: str,
    clone_from_audio_gcs_url: str,
    clone_from_text_transcript: str,
    config_scale: float = config_SCALE_PARAM,
    temperature: float = TEMPERATURE_PARAM,
    top_p: float = TOP_P_PARAM
) -> bytes | None:
    """
    Generates speech audio by cloning a voice from an audio sample and its transcript
    using a provided prediction endpoint.

    Args:
        text_to_synthesize: The text to be converted into speech.
        clone_from_audio_gcs_url: GCS URL to the audio file to clone the voice from
                                  (e.g., "gs://bucket/your_audio.wav").
        clone_from_text_transcript: The transcript of the audio provided for cloning.
        temperature: Controls randomness in generation. Higher is more random.
                     (Default: 1.3)
        top_p: Nucleus sampling parameter. (Default: 0.95)
        config_scale: Configuration scale. (Default: 0.3)

    Returns:
        Decoded audio bytes if successful, otherwise None.
    """
    try:
        # 1. Construct the instances payload for the prediction request
        instances = [{
            "text": text_to_synthesize,
            "clone_from_audio": clone_from_audio_gcs_url,
            "clone_from_text": clone_from_text_transcript,
        }]
        
        # 2. Construct the parameters payload for the prediction request
        parameters_dict = {
            "config_scale": config_scale,
            "temperature": temperature,
            "top_p": top_p
        }

        logger.info(f"Sending prediction request to endpoint...")
        logger.info(f"Instances: {json.dumps(instances, indent=2)}") # Using json.dumps for pretty print if needed
        logger.info(f"Parameters: {parameters_dict}")

        # 3. Make the prediction call
        response = endpoint.predict(instances=instances, parameters=parameters_dict)
        
        # 4. Process the prediction response
        # Assuming the response structure matches the user's example:
        # response.predictions is a list, and the first item has an "audio" key
        # containing base64 encoded audio data.
        if response.predictions and \
           isinstance(response.predictions, list) and \
           len(response.predictions) > 0 and \
           isinstance(response.predictions[0], dict) and \
           "audio" in response.predictions[0]:
            
            audio_base64 = response.predictions[0]["audio"]
            if audio_base64:
                audio_bytes = base64.b64decode(audio_base64)
                logger.info("Successfully received and decoded audio from prediction.")
                return audio_bytes
            else:
                logger.error("Error: Prediction response contained an empty audio field.")
                return None
        else:
            logger.error("Error: Prediction response did not contain the expected audio data structure.")
            # Log the actual response structure for debugging if possible
            # Be cautious about logging potentially large or sensitive response data directly in production
            try:
                logger.error(f"Full response predictions: {response.predictions}")
            except Exception:
                logger.error("Could not print full response predictions.")
            return None

    except Exception as e:
        logger.error(f"An error occurred during speech synthesis prediction: {e}")
        # Depending on the type of endpoint, specific exceptions might be caught here
        # e.g., from google.api_core.exceptions for Google Cloud services
        return None
