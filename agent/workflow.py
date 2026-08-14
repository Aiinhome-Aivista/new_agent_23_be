from langgraph.graph import StateGraph, END
from agent.state import AgentWorkflowState
from agent.nodes import (
    orchestrator_node,
    artifact_intake_node,
    decomposition_node,
    service_contract_node,
    unit_test_design_node,
    review_agent_node,
    coverage_reviewer_node,
    test_pack_output_node
)

def build_workflow():
    workflow = StateGraph(AgentWorkflowState)

    workflow.add_node("orchestrator", orchestrator_node)
    workflow.add_node("artifact_intake", artifact_intake_node)
    workflow.add_node("decomposition", decomposition_node)
    workflow.add_node("service_contract", service_contract_node)
    workflow.add_node("unit_test_design", unit_test_design_node)
    workflow.add_node("review_agent", review_agent_node)
    workflow.add_node("coverage_reviewer", coverage_reviewer_node)
    workflow.add_node("test_pack_output", test_pack_output_node)

    workflow.set_entry_point("orchestrator")

    # For now, simple sequential flow. 
    # In reality, conditional edges based on HITL gates.
    workflow.add_edge("orchestrator", "artifact_intake")
    workflow.add_edge("artifact_intake", "decomposition")
    workflow.add_edge("decomposition", "service_contract")
    workflow.add_edge("service_contract", "unit_test_design") # Usually pauses before this
    workflow.add_edge("unit_test_design", "review_agent")
    workflow.add_edge("review_agent", "coverage_reviewer")
    workflow.add_edge("coverage_reviewer", "test_pack_output")
    workflow.add_edge("test_pack_output", END)

    app = workflow.compile()
    return app

agent_workflow = build_workflow()
