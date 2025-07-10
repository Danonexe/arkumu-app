"""
Centralized mapping validation service.

This module provides a single source of truth for all mapping-related validation logic.
"""

from .validator import MappingValidator

__all__ = ['MappingValidator']