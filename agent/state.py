from typing import TypedDict, List, Dict, Any, Optional

class AgentWorkflowState(TypedDict):
    session_id: str
    status: str
    artifacts: List[Dict[str, Any]]
    parsed_requirements: List[Dict[str, Any]]
    service_contracts: List[Dict[str, Any]]
    generated_tests: List[Dict[str, Any]]
    errors: List[str]
    current_node: str
    human_feedback: Optional[str]
