from .register import create_lemma_span_processor, register_otel
from .trace_wrapper import TraceContext, TraceResult, agent, wrap_agent, RunContext, lemma_run
from .span_helpers import trace, tool, llm, retrieval
from .instrument_anthropic import instrument_anthropic
from .instrument_openai import instrument_openai
from .instrument_openai_agents import instrument_openai_agents
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
    "create_lemma_span_processor",
    "register_otel",
    # Primary API
    "agent",
    "TraceContext",
    "TraceResult",
    "RunContext",
    "trace",
    "tool",
    "llm",
    "retrieval",
    # Deprecated aliases
    "wrap_agent",
    "lemma_run",
    # Instrumentation helpers
    "instrument_anthropic",
    "instrument_openai",
    "instrument_openai_agents",
    # Mode flags
    "enable_experiment_mode",
    "disable_experiment_mode",
    "is_experiment_mode_enabled",
    "enable_debug_mode",
    "disable_debug_mode",
    "is_debug_mode_enabled",
]
