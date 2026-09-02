"""Regression tests for persistent LangGraph sessions."""

import pickle

from agentkernel.framework.langgraph.langgraph import CheckPointer

from session_compat import install_langgraph_session_serialization_compatibility


def test_langgraph_checkpointer_round_trips_without_serializing_runtime_callbacks() -> None:
    install_langgraph_session_serialization_compatibility()
    checkpointer = CheckPointer()
    vars(checkpointer)["_storage"] = {"thread": {"": {"checkpoint": {"id": "checkpoint-1"}}}}
    vars(checkpointer)["_writes"] = {("thread", "checkpoint-1"): [("task", "messages", "hello")]}

    restored = pickle.loads(pickle.dumps(checkpointer))

    assert isinstance(restored, CheckPointer)
    assert vars(restored)["_storage"] == vars(checkpointer)["_storage"]
    assert vars(restored)["_writes"] == vars(checkpointer)["_writes"]
    assert "serde" in vars(restored)
