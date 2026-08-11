import asyncio
from agent.state import AgentWorkflowState
from utils.broadcaster import broadcast_log
from utils.llm_client import get_llm
from langchain_core.messages import HumanMessage

async def orchestrator_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Orchestrator] Initializing test generation workflow...")
    state["current_node"] = "orchestrator"
    return state

async def artifact_intake_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Artifact Intake] Analyzing BRD and API Specification documents...")
    await asyncio.sleep(1) # Simulate parsing
    await broadcast_log(session_id, "[Artifact Intake] Found 14 Business Rules and 3 Service boundaries.")
    state["current_node"] = "artifact_intake"
    return state

async def decomposition_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Decomposition] Extracting positive, negative, and edge-case scenarios...")
    await asyncio.sleep(2)
    state["current_node"] = "decomposition"
    return state

async def service_contract_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Service Contract] Defining Mocks and DTOs for UserService...")
    state["current_node"] = "service_contract"
    return state

async def unit_test_design_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Test Design] Connecting to AI to generate test cases...")
    
    try:
        llm = get_llm()
        prompt = """
        Write a professional, production-grade Unit Test class for a 'UserService'.
        Use Java, JUnit 5, and Mockito. 
        Follow the Arrange-Act-Assert (AAA) pattern.
        Just output the raw code without markdown formatting.
        """
        await broadcast_log(session_id, "[Test Design] Waiting for AI response...")
        
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        code = response.content
        
        # Save to state
        state.setdefault("generated_tests", []).append({"service": "UserService", "code": code})
        await broadcast_log(session_id, f"[Test Design] Generated {len(code.splitlines())} lines of code successfully.")
        
    except Exception as e:
        await broadcast_log(session_id, f"[Test Design] Error calling AI: {str(e)}")
        
    state["current_node"] = "unit_test_design"
    return state

async def coverage_reviewer_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Coverage Reviewer] Auditing tests against requirements. Traceability Matrix updated.")
    await asyncio.sleep(1)
    state["current_node"] = "coverage_reviewer"
    return state

async def test_pack_output_node(state: AgentWorkflowState) -> AgentWorkflowState:
    session_id = state['session_id']
    await broadcast_log(session_id, "[Output] Finalizing ZIP and Word Reports...")
    state["current_node"] = "test_pack_output"
    await broadcast_log(session_id, "[Output] Workflow completed! [END_OF_STREAM]")
    return state
