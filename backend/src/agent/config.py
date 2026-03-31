from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Dict, List
from .types import AgentRole


@dataclass
class AgentConfig:
    """智能体配置对象，适用于主智能体与子智能体。"""

    agent_id: str
    role: AgentRole
    role_description: str
    goal: str
    constraints: List[str]
    allowed_tools: List[str]
    max_iterations: int = 25
    can_delegate: bool = True
    initial_context: List[Dict[str, Any]] = field(default_factory=list)
    memory_access: Dict[str, bool] = field(
        default_factory=lambda: {
            "agent_memory": True,
            "user_memory": True,
            "session_memory": True,
        }
    )
