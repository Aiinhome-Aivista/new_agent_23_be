from typing import TypedDict, List, Dict, Any, Optional

class AgentWorkflowState(TypedDict):
    session_id: str
    status: str
    tech_profile: Optional[Dict[str, Any]]
    artifacts: List[Dict[str, Any]]
    parsed_requirements: List[Dict[str, Any]]
    service_contracts: List[Dict[str, Any]]
    generated_tests: List[Dict[str, Any]]
    coverage_matrix: List[Dict[str, Any]]
    errors: List[str]
    current_node: str
    human_feedback: Optional[str]
    target_service_id: Optional[str]
    review_report: Optional[Dict[str, Any]]

