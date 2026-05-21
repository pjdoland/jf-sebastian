"""
Teddy Ruxpin AI Conversation System
Real-time voice conversation with ChatGPT through 1985 Teddy Ruxpin animatronic.
"""

# Reduce CUDA caching-allocator fragmentation before anything in the package
# (transitively) imports torch. PyTorch reads this env var when it initializes
# the CUDA context; setting it after import has no effect. setdefault preserves
# any override from run.sh / the supervisor unit.
import os
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

__version__ = "1.0.0"
