from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks

from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Dict, Any
from database import get_db
import uuid
from agent.workflow import agent_workflow
from utils.broadcaster import subscribe_logs, broadcast_log

router = APIRouter()

@router.post("/sessions")
async def create_session(tech_profile: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    return {"session_id": str(uuid.uuid4()), "status": "INITIALIZED"}

@router.post("/sessions/{session_id}/artifacts")
async def upload_artifact(session_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    return {"message": f"Artifact {file.filename} uploaded successfully."}

async def run_agent_workflow(session_id: str):
    # This runs the LangGraph workflow asynchronously
    try:
        initial_state = {"session_id": session_id, "status": "running"}
        # Use ainvoke for async nodes
        await agent_workflow.ainvoke(initial_state)
    except Exception as e:
        await broadcast_log(session_id, f"[Error] Agent Workflow Failed: {str(e)} [END_OF_STREAM]")

@router.post("/sessions/{session_id}/decompose")
async def trigger_decompose(session_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # Start graph execution in the background
    background_tasks.add_task(run_agent_workflow, session_id)
    return {"message": "Decomposition triggered. Connect to SSE stream for updates."}

@router.get("/sessions/{session_id}/services")
async def get_services(session_id: str, db: AsyncSession = Depends(get_db)):
    return {"services": []}

@router.put("/sessions/{session_id}/services/confirm")
async def confirm_services(session_id: str, services_updates: List[Dict[str, Any]], db: AsyncSession = Depends(get_db)):
    return {"message": "Services confirmed. HITL gate passed."}

@router.post("/sessions/{session_id}/generate-tests")
async def generate_tests(session_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    # In a real app we'd resume the graph. Here we just trigger it again for demo.
    background_tasks.add_task(run_agent_workflow, session_id)
    return {"message": "Test generation triggered. Connect to SSE stream for updates."}

from fastapi.responses import StreamingResponse

@router.get("/sessions/{session_id}/stream")
async def stream_agent_execution(session_id: str):
    # Consumes the Redis async generator and streams it to the client
    return StreamingResponse(subscribe_logs(session_id), media_type="text/event-stream")

@router.get("/sessions/{session_id}/coverage-matrix")
async def get_coverage_matrix(session_id: str, db: AsyncSession = Depends(get_db)):
    return {"matrix": []}

@router.post("/sessions/{session_id}/review/resolve")
async def resolve_review(session_id: str, feedback: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    return {"message": "Review resolved"}

@router.post("/sessions/{session_id}/regenerate-service")
async def regenerate_service(session_id: str, service_id: str, db: AsyncSession = Depends(get_db)):
    return {"message": f"Regeneration triggered for service {service_id}"}

import io
import zipfile
from fastapi.responses import StreamingResponse

@router.get("/sessions/{session_id}/download/zip")
async def download_zip(session_id: str):
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        zip_file.writestr("UserServiceTest.java", "// AI Generated Test Class\n\npublic class UserServiceTest {\n    // tests go here\n}\n")
    
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=test_pack_{session_id}.zip"}
    )

@router.get("/sessions/{session_id}/download/report")
async def download_report(session_id: str):
    html_content = f"""
    <html>
        <head><title>Test Generation Report</title></head>
        <body>
            <h1>Unit Test Generation Report</h1>
            <p><strong>Session ID:</strong> {session_id}</p>
            <h2>Summary</h2>
            <p>1 Service processed. 14 Rules covered.</p>
            <h2>Traceability Matrix</h2>
            <table border="1" cellpadding="5">
                <tr><th>Component</th><th>Status</th></tr>
                <tr><td>UserServiceTest.java</td><td>COVERED</td></tr>
            </table>
        </body>
    </html>
    """
    
    return StreamingResponse(
        io.BytesIO(html_content.encode('utf-8')),
        media_type="application/msword",
        headers={"Content-Disposition": f"attachment; filename=test_report_{session_id}.doc"}
    )
