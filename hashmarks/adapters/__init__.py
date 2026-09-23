"""Adapters for qualified external observation artifacts."""

from .maven_dependency import maven_dependency_observation
from .uv_dependency import uv_lock_dependency_observation

__all__ = ["maven_dependency_observation", "uv_lock_dependency_observation"]
