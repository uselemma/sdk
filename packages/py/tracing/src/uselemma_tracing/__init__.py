from .client import Lemma, SpanHandle, TraceContext, active
from .experiment_mode import (
    disable_experiment_mode,
    enable_experiment_mode,
    is_experiment_mode_enabled,
)
from .debug_mode import (
    disable_debug_mode,
    enable_debug_mode,
    is_debug_mode_enabled,
)

__all__ = [
    "Lemma",
    "SpanHandle",
    "TraceContext",
    "active",
    # Mode flags
    "enable_experiment_mode",
    "disable_experiment_mode",
    "is_experiment_mode_enabled",
    "enable_debug_mode",
    "disable_debug_mode",
    "is_debug_mode_enabled",
]
