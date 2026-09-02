"""Narrow serialization compatibility for Agent Kernel 0.8.1 LangGraph sessions."""

from __future__ import annotations

import copyreg
from collections.abc import Callable
from typing import Any

from agentkernel.framework.langgraph.langgraph import CheckPointer


def _restore_checkpointer(storage: dict[str, Any], writes: dict[str, Any]) -> CheckPointer:
    """Rebuild LangGraph's runtime serializer instead of loading its unpicklable closure."""
    checkpointer = CheckPointer()
    vars(checkpointer)["_storage"] = storage
    vars(checkpointer)["_writes"] = writes
    return checkpointer


def _reduce_checkpointer(checkpointer: CheckPointer) -> tuple[Callable[..., CheckPointer], tuple[Any, ...]]:
    """Persist checkpoint state without LangGraph's process-local serializer callback."""
    state = vars(checkpointer)
    return _restore_checkpointer, (state.get("_storage", {}), state.get("_writes", {}))


def install_langgraph_session_serialization_compatibility() -> None:
    """Register the scoped reducer before Agent Kernel persists a LangGraph session."""
    copyreg.pickle(CheckPointer, _reduce_checkpointer)
