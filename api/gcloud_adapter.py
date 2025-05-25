import logging
import json
import base64
from google.cloud import aiplatform

logger = logging.getLogger(__name__)

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
    project_id: str,
    region: str,
    endpoint_id: str,
    input_text: str,
    cfg_scale: float = 0.3,
    temperature: float = 1.3,
    top_p: float = 0.95
) -> bytes | None:
    """
    Calls a Vertex AI custom model endpoint that expects text input and
    responds with binary voice data.
    Args:
        project_id (str): Your Google Cloud project ID.
        region (str): The region where your Vertex AI endpoint is deployed (e.g., "us-central1").
        endpoint_id (str): The ID of your Vertex AI endpoint.
        input_text (str): The text to be processed by the model.
        cfg_scale (float): Configuration scale parameter for the model.
        temperature (float): Temperature parameter for the model.
        top_p (float): Top_p parameter for the model.
    Returns:
        bytes | None: The binary voice data from the model response if successful,
                      otherwise None.
    Raises:
        Exception: If the API call fails or returns an unexpected status.
    """
    try:
        aiplatform.init(project=project_id, location=region)
        endpoint = aiplatform.Endpoint(endpoint_name=endpoint_id)
        logger.info(f"Successfully initialized endpoint: {endpoint.resource_name}")

        payload_dict = {
            "instances": [
                {"text": input_text}
            ],
            "parameters": {
                "cfg_scale": cfg_scale,
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
