"""
Remote adapter for voice cloning services.
This module provides interfaces to remote voice cloning services via gRPC.
"""

from .vibe_remote_model import synthesize_speech_with_cloned_voice, call_voice_model

__all__ = [
    "synthesize_speech_with_cloned_voice",
    "call_voice_model"
]
