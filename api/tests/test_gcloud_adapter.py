import os
import base64
import json
import unittest
from unittest.mock import patch, MagicMock
from ..gcloud_adapter import extract_audio_from_response

class TestExtractAudioFromResponse(unittest.TestCase):
    def setUp(self):
        # Sample test data
        self.valid_audio_data = b'test_audio_data'
        self.encoded_audio = base64.b64encode(self.valid_audio_data).decode('utf-8')
        
    def test_extract_audio_valid_response(self):
        # Test with valid response structure
        valid_response = {
            "predictions": [
                {"audio": self.encoded_audio}
            ]
        }
        response_text = json.dumps(valid_response)
        
        result = extract_audio_from_response(response_text)
        self.assertEqual(result, self.encoded_audio)
    
    def test_extract_audio_missing_predictions(self):
        # Test response missing predictions key
        invalid_response = {"wrong_key": []}
        response_text = json.dumps(invalid_response)
        
        with self.assertRaises(ValueError) as context:
            extract_audio_from_response(response_text)
        self.assertIn("Failed to extract audio data", str(context.exception))
    
    def test_extract_audio_empty_predictions(self):
        # Test empty predictions array
        invalid_response = {"predictions": []}
        response_text = json.dumps(invalid_response)
        
        with self.assertRaises(ValueError) as context:
            extract_audio_from_response(response_text)
        self.assertIn("Failed to extract audio data", str(context.exception))
    
    def test_extract_audio_missing_audio_key(self):
        # Test prediction missing audio key
        invalid_response = {
            "predictions": [
                {"wrong_key": "value"}
            ]
        }
        response_text = json.dumps(invalid_response)
        
        with self.assertRaises(ValueError) as context:
            extract_audio_from_response(response_text)
        self.assertIn("Failed to extract audio data", str(context.exception))
    
    def test_extract_audio_invalid_json(self):
        # Test with invalid JSON
        with self.assertRaises(ValueError) as context:
            extract_audio_from_response("not a valid json")
        self.assertIn("Failed to extract audio data", str(context.exception))

class TestCallVertexDiaModel(unittest.TestCase):
    def setUp(self):
        # Test configuration
        self.test_config = {
            'project_id': 'test-project',
            'region': 'us-central1',
            'endpoint_id': '1234567890',
            'input_text': 'This is a test message.',
            'output_file': 'test_output.wav',
            'cfg_scale': 0.3,
            'temperature': 1.3,
            'top_p': 0.95
        }
        
        # Sample binary audio data (simulated)
        self.sample_audio_data = b'RIFF$\x1e\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00D\xac\x00\x00\x88X\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00'
        
        # Mock response data
        self.mock_response_data = {
            'predictions': [
                {'audio': base64.b64encode(self.sample_audio_data).decode('utf-8')}
            ]
        }

    def tearDown(self):
        # Clean up: remove output file if it exists
        if os.path.exists(self.test_config['output_file']):
            os.remove(self.test_config['output_file'])

    @patch('app_dia.aiplatform')
    def test_call_vertex_dia_model_success(self, mock_aiplatform):
        # Setup mock endpoint and response
        mock_endpoint = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = json.dumps(self.mock_response_data)
        mock_endpoint.raw_predict.return_value = mock_response
        
        # Configure the mock
        mock_aiplatform.Endpoint.return_value = mock_endpoint
        
        # Call the function
        result = call_vertex_Dia_model(
            project_id=self.test_config['project_id'],
            region=self.test_config['region'],
            endpoint_id=self.test_config['endpoint_id'],
            input_text=self.test_config['input_text'],
            cfg_scale=self.test_config['cfg_scale'],
            temperature=self.test_config['temperature'],
            top_p=self.test_config['top_p']
        )
        
        # Assertions
        self.assertIsNotNone(result)
        self.assertEqual(result, self.sample_audio_data)
        
        # Verify the mock was called correctly
        mock_aiplatform.Endpoint.assert_called_once()
        mock_endpoint.raw_predict.assert_called_once()
        
        # Save the output to a file
        with open(self.test_config['output_file'], 'wb') as f:
            f.write(result)
            
        # Verify file was created and has content
        self.assertTrue(os.path.exists(self.test_config['output_file']))
        self.assertGreater(os.path.getsize(self.test_config['output_file']), 0)
        print(f"\nTest output saved to: {os.path.abspath(self.test_config['output_file'])}")

    @patch('app_dia.aiplatform')
    def test_call_vertex_dia_model_failure(self, mock_aiplatform):
        # Setup mock endpoint and error response
        mock_endpoint = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = 'Invalid request'
        mock_endpoint.raw_predict.return_value = mock_response
        
        # Configure the mock
        mock_aiplatform.Endpoint.return_value = mock_endpoint
        
        # Test that the function raises an exception on failure
        with self.assertRaises(Exception) as context:
            call_vertex_Dia_model(
                project_id=self.test_config['project_id'],
                region=self.test_config['region'],
                endpoint_id=self.test_config['endpoint_id'],
                input_text=self.test_config['input_text']
            )
        
        self.assertIn('Prediction failed with status code 400', str(context.exception))

if __name__ == '__main__':
    unittest.main()
