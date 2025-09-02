"""
E2E Cloud Models adapter with mock implementations.
"""
import logging
from typing import Dict, Any, Optional, List, Union, BinaryIO
import uuid
import time

# Mock logger
logger = logging.getLogger(__name__)

# Mock model registry
_mock_models = {}
_mock_predictions = {}

class MockModel:
    """Mock model class for E2E Cloud."""
    
    def __init__(self, model_id: str, model_name: str):
        self.model_id = model_id
        self.model_name = model_name
        self.version = '1.0.0'
        self.created_at = time.time()
        self.status = 'READY'
        self.metadata = {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary."""
        return {
            'model_id': self.model_id,
            'model_name': self.model_name,
            'version': self.version,
            'created_at': self.created_at,
            'status': self.status,
            'metadata': self.metadata
        }

def create_model(model_name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Mock implementation of create_model."""
    model_id = f"model_{str(uuid.uuid4())[:8]}"
    model = MockModel(model_id, model_name)
    model.metadata = metadata or {}
    _mock_models[model_id] = model
    logger.info(f"[MOCK] Created model {model_name} with ID {model_id}")
    return model.to_dict()

def get_model(model_id: str) -> Optional[Dict[str, Any]]:
    """Mock implementation of get_model."""
    model = _mock_models.get(model_id)
    if model:
        return model.to_dict()
    return None

def list_models() -> List[Dict[str, Any]]:
    """Mock implementation of list_models."""
    return [model.to_dict() for model in _mock_models.values()]

async def predict(
    model_id: str,
    input_data: Union[Dict[str, Any], List[Any], str, bytes],
    parameters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Mock implementation of predict."""
    if model_id not in _mock_models:
        raise ValueError(f"Model {model_id} not found")
    
    prediction_id = f"pred_{str(uuid.uuid4())[:8]}"
    
    # Store prediction
    _mock_predictions[prediction_id] = {
        'model_id': model_id,
        'input': input_data,
        'parameters': parameters or {},
        'timestamp': time.time()
    }
    
    # Generate mock prediction
    return {
        'prediction_id': prediction_id,
        'model_id': model_id,
        'predictions': [{
            'label': 'mock_label',
            'score': 0.95,
            'details': {
                'model': _mock_models[model_id].model_name,
                'version': _mock_models[model_id].version,
                'timestamp': time.time()
            }
        }],
        'metadata': {}
    }

def get_prediction(prediction_id: str) -> Optional[Dict[str, Any]]:
    """Mock implementation of get_prediction."""
    return _mock_predictions.get(prediction_id)

def clear_mock_models():
    """Clear the mock models and predictions. Useful for testing."""
    global _mock_models, _mock_predictions
    _mock_models = {}
    _mock_predictions = {}
    logger.info("[MOCK] Models and predictions cleared")
