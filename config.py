"""
Backward-compatible configuration module.

New code should import from core.config.
"""

from core.config import Settings, settings

__all__ = ["Settings", "settings"]
