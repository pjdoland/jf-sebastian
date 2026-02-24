"""GPU device auto-detection utilities."""

import logging

logger = logging.getLogger(__name__)


def detect_gpu_device() -> str:
    """
    Detect the best available GPU device for inference.

    Checks in order of preference: CUDA (NVIDIA) > MPS (Apple Silicon) > CPU.

    Returns:
        Device string: 'cuda', 'mps', or 'cpu'
    """
    try:
        import torch

        if torch.cuda.is_available():
            device_name = torch.cuda.get_device_name(0)
            logger.info(f"CUDA device detected: {device_name}")
            return "cuda"

        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            logger.info("MPS device detected (Apple Silicon)")
            return "mps"

    except ImportError:
        logger.debug("PyTorch not installed, defaulting to CPU")
    except Exception as e:
        logger.warning(f"Error detecting GPU device: {e}")

    logger.info("No GPU detected, using CPU")
    return "cpu"
