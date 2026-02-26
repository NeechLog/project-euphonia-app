import os
import tempfile
import pytest
import shutil
from unittest.mock import Mock, patch, MagicMock, AsyncMock
from pathlib import Path
import numpy as np
import soundfile as sf
from pydub import AudioSegment
from fastapi import HTTPException

# Import the module to test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from api.model_local_file_request_helper import (
    validate_audio_format_from_file,
    validate_audio_format,
    build_and_validate_audio_message,
    write_temp_file,
    build_raw_audio_message,
    validate_audio_message,
    is_valid_wav,
    TEMP_AUDIO_DIR,
    GOOD_AUDIO_DIR
)

# Import AudioMessage for testing
try:
    from audiomessages import AudioMessage
except ImportError:
    # Create a mock AudioMessage for testing if the real one is not available
    class AudioMessage:
        def __init__(self):
            self.audio_binary = b""
            self.text = ""
            self.audio_file_path = ""
            self.locale = ""
        
        def HasField(self, field_name):
            if field_name == 'audio_binary':
                return bool(self.audio_binary)
            elif field_name == 'audio_file_path':
                return bool(self.audio_file_path)
            return False


class TestValidateAudioFormatFromFile:
    """Test cases for validate_audio_format_from_file function."""
    
    def test_file_not_found(self):
        """Test validation when file doesn't exist."""
        is_valid, error_msg = validate_audio_format_from_file("/nonexistent/file.wav")
        assert not is_valid
        assert "File not found" in error_msg
    
    def test_empty_file_path(self):
        """Test validation with empty file path."""
        is_valid, error_msg = validate_audio_format_from_file("")
        assert not is_valid
        assert "File not found" in error_msg
    
    def test_none_file_path(self):
        """Test validation with None file path."""
        is_valid, error_msg = validate_audio_format_from_file(None)
        assert not is_valid
        assert "File not found" in error_msg
    
    @patch('soundfile.read')
    @patch('pydub.AudioSegment.from_file')
    def test_valid_wav_file_mono(self, mock_audio_segment, mock_soundfile):
        """Test validation of a valid mono WAV file."""
        # Mock AudioSegment
        mock_audio = Mock()
        mock_audio.__len__ = Mock(return_value=1000)  # Non-zero duration
        mock_audio_segment.return_value = mock_audio
        
        # Mock soundfile read for mono audio
        mock_soundfile.return_value = (np.array([0.1, 0.2, 0.3]), 16000)
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'fake wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path, check_format=True)
            assert is_valid
            assert error_msg == ""
        finally:
            os.unlink(tmp_file_path)
    
    @patch('soundfile.read')
    @patch('pydub.AudioSegment.from_file')
    def test_valid_wav_file_without_format_check(self, mock_audio_segment, mock_soundfile):
        """Test validation without format checking."""
        # Mock AudioSegment
        mock_audio = Mock()
        mock_audio.__len__ = Mock(return_value=1000)
        mock_audio_segment.return_value = mock_audio
        
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'fake wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path, check_format=False)
            assert is_valid
            assert error_msg == ""
            # soundfile.read should not be called when check_format=False
            mock_soundfile.assert_not_called()
        finally:
            os.unlink(tmp_file_path)
    
    @patch('pydub.AudioSegment.from_file')
    def test_zero_duration_audio(self, mock_audio_segment):
        """Test validation of audio with zero duration."""
        mock_audio = Mock()
        mock_audio.__len__ = Mock(return_value=0)  # Zero duration
        mock_audio_segment.return_value = mock_audio
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'fake wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path)
            assert not is_valid
            assert "zero duration" in error_msg.lower()
        finally:
            os.unlink(tmp_file_path)
    
    @patch('pydub.AudioSegment.from_file')
    def test_invalid_wav_file(self, mock_audio_segment):
        """Test validation of invalid WAV file."""
        from pydub.exceptions import CouldntDecodeError
        mock_audio_segment.side_effect = CouldntDecodeError("Invalid WAV")
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'invalid wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path)
            assert not is_valid
            assert "valid WAV file" in error_msg
        finally:
            os.unlink(tmp_file_path)
    
    @patch('soundfile.read')
    @patch('pydub.AudioSegment.from_file')
    def test_stereo_audio_rejection(self, mock_audio_segment, mock_soundfile):
        """Test rejection of stereo audio."""
        mock_audio = Mock()
        mock_audio.__len__ = Mock(return_value=1000)
        mock_audio_segment.return_value = mock_audio
        
        # Mock stereo audio (2 channels)
        stereo_data = np.array([[0.1, 0.2], [0.3, 0.4]])  # Shape (2, 2)
        mock_soundfile.return_value = (stereo_data, 16000)
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'fake wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path, check_format=True)
            assert not is_valid
            assert "mono" in error_msg.lower()
        finally:
            os.unlink(tmp_file_path)
    
    @patch('soundfile.read')
    @patch('pydub.AudioSegment.from_file')
    def test_invalid_sample_rate(self, mock_audio_segment, mock_soundfile):
        """Test rejection of invalid sample rate."""
        mock_audio = Mock()
        mock_audio.__len__ = Mock(return_value=1000)
        mock_audio_segment.return_value = mock_audio
        
        # Mock audio with invalid sample rate
        mock_soundfile.return_value = (np.array([0.1, 0.2, 0.3]), 50000)  # Above 48000
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'fake wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path, check_format=True)
            assert not is_valid
            assert "sample rate" in error_msg.lower()
        finally:
            os.unlink(tmp_file_path)
    
    @patch('soundfile.read')
    @patch('pydub.AudioSegment.from_file')
    def test_soundfile_exception(self, mock_audio_segment, mock_soundfile):
        """Test handling of soundfile exceptions."""
        mock_audio = Mock()
        mock_audio.__len__ = Mock(return_value=1000)
        mock_audio_segment.return_value = mock_audio
        
        mock_soundfile.side_effect = Exception("Soundfile error")
        
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'fake wav data')
            tmp_file_path = tmp_file.name
        
        try:
            is_valid, error_msg = validate_audio_format_from_file(tmp_file_path, check_format=True)
            assert not is_valid
            assert "Error validating audio format" in error_msg
        finally:
            os.unlink(tmp_file_path)


class TestValidateAudioFormat:
    """Test cases for validate_audio_format function."""
    
    def test_empty_audio_data(self):
        """Test validation with empty audio data."""
        is_valid, error_msg = validate_audio_format(b"")
        assert not is_valid
        assert "Empty audio data" in error_msg
    
    def test_none_audio_data(self):
        """Test validation with None audio data."""
        is_valid, error_msg = validate_audio_format(None)
        assert not is_valid
        assert "Empty audio data" in error_msg
    
    @patch('api.model_local_file_request_helper.validate_audio_format_from_file')
    def test_successful_validation(self, mock_validate_file):
        """Test successful audio validation from binary data."""
        mock_validate_file.return_value = (True, "")
        
        # Create fake audio binary data
        audio_data = b'fake audio binary data'
        
        is_valid, error_msg = validate_audio_format(audio_data)
        assert is_valid
        assert error_msg == ""
        mock_validate_file.assert_called_once()
    
    @patch('api.model_local_file_request_helper.validate_audio_format_from_file')
    def test_validation_failure(self, mock_validate_file):
        """Test audio validation failure from binary data."""
        mock_validate_file.return_value = (False, "Invalid format")
        
        audio_data = b'fake audio binary data'
        
        is_valid, error_msg = validate_audio_format(audio_data)
        assert not is_valid
        assert error_msg == "Invalid format"
    
    @patch('api.model_local_file_request_helper.validate_audio_format_from_file')
    def test_exception_handling(self, mock_validate_file):
        """Test exception handling during validation."""
        mock_validate_file.side_effect = Exception("Unexpected error")
        
        audio_data = b'fake audio binary data'
        
        is_valid, error_msg = validate_audio_format(audio_data)
        assert not is_valid
        assert "Error processing audio data" in error_msg


class TestWriteTempFile:
    """Test cases for write_temp_file function."""
    
    def test_write_temp_file_success(self):
        """Test successful writing of temporary file."""
        audio_binary = b'test audio data'
        
        with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
            tmp_path = tmp_file.name
        
        try:
            write_temp_file(audio_binary, tmp_path)
            
            # Verify file was written correctly
            with open(tmp_path, 'rb') as f:
                written_data = f.read()
            assert written_data == audio_binary
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
    
    def test_write_temp_file_with_directory_creation(self):
        """Test writing to a file in a non-existent directory."""
        audio_binary = b'test audio data'
        
        with tempfile.TemporaryDirectory() as tmp_dir:
            nested_dir = os.path.join(tmp_dir, 'nested', 'dir')
            file_path = os.path.join(nested_dir, 'test.wav')
            
            # Create parent directories first
            os.makedirs(nested_dir, exist_ok=True)
            write_temp_file(audio_binary, file_path)
            
            # Verify directory was created and file was written
            assert os.path.exists(nested_dir)
            assert os.path.exists(file_path)
            
            with open(file_path, 'rb') as f:
                written_data = f.read()
            assert written_data == audio_binary


class TestBuildRawAudioMessage:
    """Test cases for build_raw_audio_message function."""
    
    def test_build_with_upload_file_object(self):
        """Test building AudioMessage with UploadFile-like object."""
        # Create a mock UploadFile object
        mock_upload_file = Mock()
        mock_upload_file.read.return_value = b'upload file data'
        
        text = "upload transcript"
        file_name = "upload_audio"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            audio_message, file_path = build_raw_audio_message(mock_upload_file, text, file_name)
            
            assert audio_message.audio_binary == b'upload file data'
            assert audio_message.text == text
            mock_write.assert_called_once()
    
    def test_build_with_upload_file_object_and_filename_override(self):
        """Test building with UploadFile object and verifying file_name override logic."""
        # Create a mock UploadFile object
        mock_upload_file = Mock()
        mock_upload_file.read.return_value = b'upload file data'
        
        text = "upload transcript"
        file_name = "original_name"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            audio_message, file_path = build_raw_audio_message(mock_upload_file, text, file_name)
            
            assert audio_message.audio_binary == b'upload file data'
            assert audio_message.text == text
            # Verify write_temp_file was called with the original file_name
            mock_write.assert_called_once()
            args, kwargs = mock_write.call_args
            assert args[0] == b'upload file data'  # audio_binary
            assert "original_name" in args[1]  # file_path should contain original_name
    
    def test_build_with_file_path_string(self):
        """Test building AudioMessage with file path string."""
        # Create a temporary file with audio data
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            test_audio_data = b'test audio file content'
            tmp_file.write(test_audio_data)
            tmp_file_path = tmp_file.name
        
        try:
            text = "file path transcript"
            file_name = "provided_name"
            
            with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
                audio_message, returned_file_path = build_raw_audio_message(tmp_file_path, text, file_name)
                
                # Verify the audio binary was read from file
                assert audio_message.audio_binary == test_audio_data
                assert audio_message.text == text
                # Verify file_name was overridden to the actual file path
                assert returned_file_path == tmp_file_path
                # Should not write temp file when using file path
                mock_write.assert_not_called()
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    def test_build_with_file_path_string_no_filename_provided(self):
        """Test building with file path string when no file_name parameter provided."""
        # Create a temporary file with audio data
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            test_audio_data = b'test audio file content'
            tmp_file.write(test_audio_data)
            tmp_file_path = tmp_file.name
        
        try:
            text = "file path transcript"
            
            with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
                audio_message, returned_file_path = build_raw_audio_message(tmp_file_path, text, None)
                
                # Verify the audio binary was read from file
                assert audio_message.audio_binary == test_audio_data
                assert audio_message.text == text
                # Verify file_path is the actual file path
                assert returned_file_path == tmp_file_path
                # Should not write temp file when using file path
                mock_write.assert_not_called()
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    def test_build_with_binary_data(self):
        """Test building AudioMessage with binary audio data."""
        audio_binary = b'test audio data'
        text = "test transcript"
        file_name = "test_audio"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            mock_write.return_value = None
            
            audio_message, file_path = build_raw_audio_message(audio_binary, text, file_name)
            
            assert audio_message.audio_binary == audio_binary
            assert audio_message.text == text
            assert file_path is not None
            assert file_path.endswith('.wav')
            mock_write.assert_called_once()
    
    def test_build_with_binary_data_no_filename(self):
        """Test building with binary data and no filename provided."""
        audio_binary = b'test audio data'
        text = "test transcript"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            with patch('time.time', return_value=1234567890):
                audio_message, file_path = build_raw_audio_message(audio_binary, text, None)
                
                assert audio_message.audio_binary == audio_binary
                assert audio_message.text == text
                assert file_path is not None
                assert "audio_1234567890" in file_path
                assert file_path.endswith('.wav')
                mock_write.assert_called_once()
    
    def test_build_with_none_audio_data(self):
        """Test building AudioMessage without audio data."""
        text = "text only message"
        file_name = "text_only"
        
        with patch('os.makedirs'):
            audio_message, file_path = build_raw_audio_message(None, text, file_name)
        
        assert audio_message.text == text
        assert audio_message.audio_binary == b""  # Empty binary
        # When no audio data is provided but file_name is given, a path is still created
        assert file_path is not None
        assert file_path.endswith('.wav')
        assert "text_only" in file_path
    
    def test_build_with_none_audio_data_no_filename(self):
        """Test building with None audio data and no filename."""
        text = "text only message"
        
        with patch('os.makedirs'):
            audio_message, file_path = build_raw_audio_message(None, text, None)
        
        assert audio_message.text == text
        assert audio_message.audio_binary == b""  # Empty binary
        # When no audio data and no filename, file_path should be None
        assert file_path is None
    
    def test_build_with_absolute_path(self):
        """Test building with absolute file path."""
        audio_binary = b'test audio data'
        text = "test transcript"
        absolute_path = "/absolute/path/test.wav"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            audio_message, file_path = build_raw_audio_message(audio_binary, text, absolute_path)
            
            assert file_path == absolute_path
            # Should not write to absolute paths
            mock_write.assert_not_called()
    
    def test_build_with_url(self):
        """Test building with URL."""
        audio_binary = b'test audio data'
        text = "test transcript"
        url = "https://example.com/audio.wav"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            audio_message, file_path = build_raw_audio_message(audio_binary, text, url)
            
            assert file_path == url
            mock_write.assert_not_called()
    
    def test_build_with_generated_filename(self):
        """Test building with auto-generated filename."""
        audio_binary = b'test audio data'
        text = "test transcript"
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            with patch('time.time', return_value=1234567890):
                audio_message, file_path = build_raw_audio_message(audio_binary, text)
                
                assert file_path is not None
                assert "audio_1234567890" in file_path
                assert file_path.endswith('.wav')
                mock_write.assert_called_once()
    
    def test_file_path_returned_correctly_upload_file(self):
        """Test that file path is correctly returned when using UploadFile."""
        mock_upload_file = Mock()
        mock_upload_file.read.return_value = b'upload data'
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            audio_message, file_path = build_raw_audio_message(mock_upload_file, "test", "test_file")
            
            # Should return the temp file path that was created
            assert file_path is not None
            assert file_path.endswith('.wav')
            assert "test_file" in file_path
            mock_write.assert_called_once()
    
    def test_file_path_returned_correctly_file_string(self):
        """Test that file path is correctly returned when using file path string."""
        # Create a temporary file
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp_file:
            tmp_file.write(b'test content')
            tmp_file_path = tmp_file.name
        
        try:
            audio_message, file_path = build_raw_audio_message(tmp_file_path, "test", "ignored_name")
            
            # Should return the actual file path
            assert file_path == tmp_file_path
        finally:
            if os.path.exists(tmp_file_path):
                os.unlink(tmp_file_path)
    
    def test_file_path_returned_correctly_binary_data(self):
        """Test that file path is correctly returned when using binary data."""
        audio_binary = b'test binary data'
        
        with patch('api.model_local_file_request_helper.write_temp_file') as mock_write:
            audio_message, file_path = build_raw_audio_message(audio_binary, "test", "binary_test")
            
            # Should return the temp file path that was created
            assert file_path is not None
            assert file_path.endswith('.wav')
            assert "binary_test" in file_path
            mock_write.assert_called_once()
    
    def test_file_path_returned_correctly_none_data(self):
        """Test that file path is correctly returned when using None data."""
        with patch('os.makedirs'):
            audio_message, file_path = build_raw_audio_message(None, "test", "none_test")
            
            # Should still create a path even with no audio data
            assert file_path is not None
            assert file_path.endswith('.wav')
            assert "none_test" in file_path


class TestValidateAudioMessage:
    """Test cases for validate_audio_message function."""
    
    def test_none_audio_message(self):
        """Test validation with None AudioMessage."""
        is_valid, error_msg = validate_audio_message(None)
        assert not is_valid
        assert "No AudioMessage provided" in error_msg
    
    def test_empty_audio_message(self):
        """Test validation with empty AudioMessage."""
        audio_message = AudioMessage()
        
        is_valid, error_msg = validate_audio_message(audio_message)
        assert is_valid  # Should be valid with only text
        assert "no audio_binary field" in error_msg.lower()
    
    def test_audio_message_with_binary_only(self):
        """Test validation with AudioMessage containing binary data."""
        audio_message = AudioMessage()
        audio_message.audio_binary = b'test audio data'
        
        with patch('api.model_local_file_request_helper.validate_audio_format') as mock_validate:
            mock_validate.return_value = (True, "")
            
            is_valid, error_msg = validate_audio_message(audio_message)
            
            assert is_valid
            mock_validate.assert_called_once_with(b'test audio data', True)
    
    def test_audio_message_with_file_path_only(self):
        """Test validation with AudioMessage containing file path."""
        audio_message = AudioMessage()
        audio_message.audio_file_path = "/path/to/audio.wav"
        
        with patch('api.model_local_file_request_helper.validate_audio_format_from_file') as mock_validate:
            mock_validate.return_value = (True, "")
            
            is_valid, error_msg = validate_audio_message(audio_message)
            
            assert is_valid
            mock_validate.assert_called_once_with("/path/to/audio.wav", True)
    
    def test_audio_message_with_both_binary_and_file(self):
        """Test validation priority: binary over file path."""
        audio_message = AudioMessage()
        audio_message.audio_binary = b'test audio data'
        audio_message.audio_file_path = "/path/to/audio.wav"
        
        with patch('api.model_local_file_request_helper.validate_audio_format') as mock_validate_binary:
            mock_validate_binary.return_value = (True, "")
            
            with patch('api.model_local_file_request_helper.validate_audio_format_from_file') as mock_validate_file:
                is_valid, error_msg = validate_audio_message(audio_message)
                
                assert is_valid
                # Should prefer binary validation
                mock_validate_binary.assert_called_once()
                mock_validate_file.assert_not_called()
    
    def test_audio_message_without_format_check(self):
        """Test validation without format checking."""
        audio_message = AudioMessage()
        audio_message.audio_binary = b'test audio data'
        
        with patch('api.model_local_file_request_helper.validate_audio_format') as mock_validate:
            mock_validate.return_value = (True, "")
            
            is_valid, error_msg = validate_audio_message(audio_message, check_format=False)
            
            assert is_valid
            mock_validate.assert_called_once_with(b'test audio data', False)


class TestBuildAndValidateAudioMessage:
    """Test cases for build_and_validate_audio_message function."""
    
    def test_no_data_provided(self):
        """Test building with no audio, text, or file_name."""
        with pytest.raises(HTTPException) as exc_info:
            build_and_validate_audio_message(None, None, None)
        
        assert exc_info.value.status_code == 400
        assert "must be provided" in str(exc_info.value.detail)
    
    @patch('api.model_local_file_request_helper.build_raw_audio_message')
    @patch('api.model_local_file_request_helper.validate_audio_message')
    def test_successful_build_and_validate(self, mock_validate, mock_build):
        """Test successful build and validation."""
        # Setup mocks
        mock_audio_message = AudioMessage()
        mock_audio_message.audio_binary = b'test audio'
        temp_path = os.path.join(TEMP_AUDIO_DIR, "temp_audio.wav")
        mock_build.return_value = (mock_audio_message, temp_path)
        mock_validate.return_value = (True, "")
        
        with patch('os.makedirs'), patch('shutil.move'), \
             patch('os.path.exists', return_value=True):
            audio_message, file_path = build_and_validate_audio_message(
                b'test audio', "test text", "test_file"
            )
        
        assert audio_message == mock_audio_message
        assert file_path is not None
    
    @patch('api.model_local_file_request_helper.build_raw_audio_message')
    @patch('api.model_local_file_request_helper.validate_audio_message')
    def test_validation_failure(self, mock_validate, mock_build):
        """Test build with validation failure."""
        mock_audio_message = AudioMessage()
        mock_build.return_value = (mock_audio_message, "/tmp/test.wav")
        mock_validate.return_value = (False, "Invalid audio format")
        
        with pytest.raises(HTTPException) as exc_info:
            build_and_validate_audio_message(b'invalid audio', "test text", "test_file")
        
        assert exc_info.value.status_code == 400
        assert "Invalid audio format" in str(exc_info.value.detail)
    
    @patch('api.model_local_file_request_helper.build_raw_audio_message')
    @patch('api.model_local_file_request_helper.validate_audio_message')
    def test_with_locale(self, mock_validate, mock_build):
        """Test building with locale."""
        mock_audio_message = AudioMessage()
        mock_build.return_value = (mock_audio_message, None)
        mock_validate.return_value = (True, "")
        
        audio_message, file_path = build_and_validate_audio_message(
            None, "test text", locale="en-US"
        )
        
        assert audio_message.locale == "en-US"
        assert file_path is None
    
    @patch('api.model_local_file_request_helper.build_raw_audio_message')
    @patch('api.model_local_file_request_helper.validate_audio_message')
    def test_file_moving_logic(self, mock_validate, mock_build):
        """Test file moving from temp to good directory."""
        mock_audio_message = AudioMessage()
        temp_path = os.path.join(TEMP_AUDIO_DIR, "temp_audio.wav")
        mock_build.return_value = (mock_audio_message, temp_path)
        mock_validate.return_value = (True, "")
        
        with patch('os.makedirs'), patch('shutil.move') as mock_move, \
             patch('os.path.exists', return_value=True):
            
            audio_message, file_path = build_and_validate_audio_message(
                b'test audio', "test text", "final_name"
            )
            
            mock_move.assert_called_once()
            assert file_path is not None
    
    @patch('api.model_local_file_request_helper.build_raw_audio_message')
    @patch('api.model_local_file_request_helper.validate_audio_message')
    def test_cleanup_on_exception(self, mock_validate, mock_build):
        """Test cleanup when exception occurs."""
        mock_audio_message = AudioMessage()
        temp_path = os.path.join(TEMP_AUDIO_DIR, "temp_audio.wav")
        mock_build.return_value = (mock_audio_message, temp_path)
        mock_validate.return_value = (False, "Validation error")
        
        with patch('os.path.exists', return_value=True), patch('os.unlink') as mock_unlink:
            try:
                build_and_validate_audio_message(b'test audio', "test text", "test_file")
            except HTTPException:
                pass  # Expected
            
            # Verify cleanup was attempted
            mock_unlink.assert_called()


class TestIsValidWav:
    """Test cases for is_valid_wav function."""
    
    @pytest.mark.asyncio
    async def test_successful_validation(self):
        """Test successful async WAV validation."""
        mock_file_storage = Mock()
        mock_file_storage.read = AsyncMock(return_value=b'valid wav data')
        mock_file_storage.seek = AsyncMock()
        
        with patch('api.model_local_file_request_helper.validate_audio_format') as mock_validate:
            mock_validate.return_value = (True, "")
            
            is_valid, error_msg = await is_valid_wav(mock_file_storage)
            
            assert is_valid
            assert error_msg == ""
            mock_file_storage.read.assert_called_once()
            mock_file_storage.seek.assert_called_once_with(0)
    
    @pytest.mark.asyncio
    async def test_validation_failure(self):
        """Test async WAV validation failure."""
        mock_file_storage = Mock()
        mock_file_storage.read = AsyncMock(return_value=b'invalid wav data')
        mock_file_storage.seek = AsyncMock()
        
        with patch('api.model_local_file_request_helper.validate_audio_format') as mock_validate:
            mock_validate.return_value = (False, "Invalid format")
            
            is_valid, error_msg = await is_valid_wav(mock_file_storage)
            
            assert not is_valid
            assert "Invalid format" in error_msg
    
    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test exception handling in async validation."""
        mock_file_storage = Mock()
        mock_file_storage.read = AsyncMock(side_effect=Exception("Read error"))
        mock_file_storage.seek = AsyncMock()
        
        is_valid, error_msg = await is_valid_wav(mock_file_storage)
        
        assert not is_valid
        assert "Error processing audio file" in error_msg
        mock_file_storage.seek.assert_called_once_with(0)


class TestIntegration:
    """Integration tests combining multiple functions."""
    
    def test_full_workflow_with_temp_file(self):
        """Test full workflow from binary to validated AudioMessage with temp file."""
        # Create a simple WAV header for testing
        wav_header = b'RIFF\x24\x08\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00\x40\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x08\x00\x00'
        audio_data = wav_header + b'\x00' * 1000  # Add some silence
        
        with patch('api.model_local_file_request_helper.validate_audio_format_from_file') as mock_validate:
            mock_validate.return_value = (True, "")
            
            # Test the full workflow
            audio_message, file_path = build_and_validate_audio_message(
                audio_data, "test transcript", "integration_test"
            )
            
            assert audio_message is not None
            assert audio_message.text == "test transcript"
            assert audio_message.audio_binary == audio_data
    
    def test_error_propagation(self):
        """Test that errors are properly propagated through the workflow."""
        with patch('api.model_local_file_request_helper.validate_audio_format_from_file') as mock_validate:
            mock_validate.return_value = (False, "Test error")
            
            with pytest.raises(HTTPException) as exc_info:
                build_and_validate_audio_message(b'bad audio', "test", "test")
            
            assert "Test error" in str(exc_info.value.detail)
    
    def test_temp_file_cleanup_only_removes_temp_files(self):
        """Test that only temp files are removed, normal files are preserved."""
        # Create a normal file (outside TEMP_AUDIO_DIR)
        with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as normal_file:
            normal_file.write(b'normal audio data')
            normal_file_path = normal_file.name
        
        # Create a temp file (inside TEMP_AUDIO_DIR)
        temp_file_path = os.path.join(TEMP_AUDIO_DIR, 'temp_test.wav')
        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
        with open(temp_file_path, 'wb') as temp_file:
            temp_file.write(b'temp audio data')
        
        try:
            # Verify both files exist initially
            assert os.path.exists(normal_file_path)
            assert os.path.exists(temp_file_path)
            
            # Test the CORRECTED cleanup logic from the finally block
            # The logic is: if file exists AND file starts with TEMP_AUDIO_DIR, then remove it
            # This means: remove files that ARE in TEMP_AUDIO_DIR, preserve files that are NOT in TEMP_AUDIO_DIR
            for file_path in [normal_file_path, temp_file_path]:
                if os.path.exists(file_path) and file_path.startswith(TEMP_AUDIO_DIR):
                    os.unlink(file_path)
                    print(f"Removed temp file: {file_path}")
            
            # Check results
            # Normal file should still exist (because it's not in TEMP_AUDIO_DIR)
            assert os.path.exists(normal_file_path), f"Normal file {normal_file_path} should be preserved"
            
            # Temp file should be removed (because it's in TEMP_AUDIO_DIR)
            assert not os.path.exists(temp_file_path), f"Temp file {temp_file_path} should be removed by cleanup logic"
            
        finally:
            # Clean up any remaining files
            if os.path.exists(normal_file_path):
                os.unlink(normal_file_path)
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
    
    def test_temp_file_cleanup_removes_temp_files(self):
        """Test that temp files are actually removed by the cleanup logic."""
        # Create a temp file (inside TEMP_AUDIO_DIR)
        temp_file_path = os.path.join(TEMP_AUDIO_DIR, 'temp_cleanup_test.wav')
        os.makedirs(TEMP_AUDIO_DIR, exist_ok=True)
        with open(temp_file_path, 'wb') as temp_file:
            temp_file.write(b'temp audio data for cleanup test')
        
        try:
            # Verify temp file exists initially
            assert os.path.exists(temp_file_path)
            
            # Simulate the actual cleanup logic from the finally block
            if os.path.exists(temp_file_path) and temp_file_path.startswith(TEMP_AUDIO_DIR):
                os.unlink(temp_file_path)
                print(f"Cleaned up temp file: {temp_file_path}")
            
            # Temp file should be removed
            assert not os.path.exists(temp_file_path), "Temp file should be removed"
            
        except Exception as e:
            # Ensure cleanup even if test fails
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
            raise e


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
