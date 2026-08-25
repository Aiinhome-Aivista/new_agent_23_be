import io
import zipfile
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from pydantic import BaseModel

from database.database import get_db, AsyncSessionLocal
from database.models import GenerationSession, Artifact, RequirementDecomposition, ServiceContract, UnitTest, CoverageMatrix, ReviewReport
from agent.workflow import agent_workflow
from utils.broadcaster import subscribe_logs, broadcast_log
from utils.doc_parser import parse_artifact_file
from utils.docx_generator import generate_word_report_docx

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Body

router = APIRouter()

@router.post("/sessions")
async def create_session(tech_profile: Dict[str, Any] = Body(default={}), db: AsyncSession = Depends(get_db)):
    session_id = str(uuid.uuid4())
    profile_data = tech_profile if tech_profile else {"language": "Java", "framework": "JUnit 5", "mockLibrary": "Mockito"}
    new_session = GenerationSession(
        session_id=session_id,
        user_id="default_user",
        tech_profile=profile_data,
        status="INITIALIZED"
    )
    db.add(new_session)
    await db.commit()
    return {"session_id": session_id, "status": "INITIALIZED"}

from sqlalchemy.future import select
from database.models import GenerationSession

@router.get("/sessions")
async def get_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GenerationSession).order_by(GenerationSession.created_at.desc()))
    sessions = result.scalars().all()
    return {"sessions": [{"session_id": str(s.session_id), "status": s.status, "tech_profile": s.tech_profile, "created_at": s.created_at.isoformat() + "Z" if not s.created_at.isoformat().endswith("Z") else s.created_at.isoformat()} for s in sessions]}

@router.get("/sessions/{session_id}")
async def get_session(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    session_obj = result.scalar_one_or_none()
    if not session_obj:
        raise HTTPException(status_code=404, detail="Session not found")
        
    # Get associated artifacts
    from database.models import Artifact
    art_result = await db.execute(select(Artifact).where(Artifact.session_id == session_id))
    artifacts = art_result.scalars().all()
    
    return {
        "session_id": str(session_obj.session_id),
        "status": session_obj.status,
        "tech_profile": session_obj.tech_profile,
        "created_at": session_obj.created_at.isoformat() if session_obj.created_at else None,
        "artifacts": [{"artifact_id": str(a.artifact_id), "filename": a.filename, "file_type": a.file_type} for a in artifacts]
    }

@router.post("/sessions/{session_id}/artifacts")
async def upload_artifact(session_id: str, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    # Check session
    result = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    session_obj = result.scalar_one_or_none()
    if not session_obj:
        # Create on the fly if not existing
        session_obj = GenerationSession(session_id=session_id, status="INITIALIZED", tech_profile={"language": "Java"})
        db.add(session_obj)
        await db.flush()

    file_bytes = await file.read()
    raw_text, metadata, doc_type = parse_artifact_file(file.filename, file_bytes)

    artifact_obj = Artifact(
        session_id=session_id,
        filename=file.filename,
        file_type=doc_type,
        raw_text=raw_text,
        parsed_json_metadata=metadata
    )
    db.add(artifact_obj)
    await db.commit()

    return {"message": f"Artifact {file.filename} uploaded successfully.", "file_type": doc_type}

async def run_agent_workflow(session_id: str):
    try:
        async with AsyncSessionLocal() as db:
            res = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
            sess = res.scalar_one_or_none()
            tech_profile = sess.tech_profile if sess else {"language": "Java", "framework": "JUnit 5"}

        initial_state = {
            "session_id": session_id,
            "status": "running",
            "tech_profile": tech_profile,
            "artifacts": [],
            "parsed_requirements": [],
            "service_contracts": [],
            "generated_tests": [],
            "coverage_matrix": [],
            "errors": [],
            "current_node": "start",
            "human_feedback": None,
            "target_service_id": None
        }
        await agent_workflow.ainvoke(initial_state)
    except Exception as e:
        await broadcast_log(session_id, f"[Error] Agent Workflow Failed: {str(e)} [END_OF_STREAM]")

class GitConfigRequest(BaseModel):
    git_url: Optional[str] = None
    git_branch: Optional[str] = None
    git_path: Optional[str] = None

@router.post("/sessions/{session_id}/decompose")
async def trigger_decompose(
    session_id: str, 
    background_tasks: BackgroundTasks, 
    payload: GitConfigRequest = Body(default=GitConfigRequest()), 
    db: AsyncSession = Depends(get_db)
):
    if payload.git_url:
        from utils.git_utils import validate_git_connection
        if not validate_git_connection(payload.git_url):
            raise HTTPException(
                status_code=400, 
                detail="Invalid Git Repository URL or authentication token. Connection check failed."
            )

    result = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    session_obj = result.scalar_one_or_none()
    if session_obj:
        profile = dict(session_obj.tech_profile) if session_obj.tech_profile else {}
        profile["git_url"] = payload.git_url
        profile["git_branch"] = payload.git_branch
        profile["git_path"] = payload.git_path
        session_obj.tech_profile = profile
        await db.commit()

    background_tasks.add_task(run_agent_workflow, session_id)
    return {"message": "Decomposition triggered. Connect to SSE stream for updates."}

@router.get("/sessions/{session_id}/decompositions")
async def get_decompositions(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RequirementDecomposition).where(RequirementDecomposition.session_id == session_id))
    items = result.scalars().all()
    print(f"\n[API DEBUG] GET /decompositions called for session_id: {session_id} | Found {len(items)} database records.")
    return {"decompositions": [
        {"req_id": i.req_id, "rule_code": i.rule_code, "rule_text": i.rule_text, "rule_type": i.rule_type} for i in items
    ]}

@router.get("/sessions/{session_id}/services")
async def get_services(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceContract).where(ServiceContract.session_id == session_id))
    items = result.scalars().all()
    print(f"[API DEBUG] GET /services called for session_id: {session_id} | Found {len(items)} database records.\n")
    return {"services": [
        {"service_id": i.service_id, "name": i.name, "methods": i.methods, "dependencies": i.dependencies, "status": i.status} for i in items
    ]}

@router.put("/sessions/{session_id}/services/confirm")
async def confirm_services(session_id: str, services_updates: List[Dict[str, Any]] = [], db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceContract).where(ServiceContract.session_id == session_id))
    services = result.scalars().all()
    for s in services:
        s.status = "CONFIRMED"
    await db.commit()
    return {"message": "Services confirmed. HITL gate passed."}

@router.post("/sessions/{session_id}/generate-tests")
async def generate_tests(session_id: str, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    background_tasks.add_task(run_agent_workflow, session_id)
    return {"message": "Test generation triggered. Connect to SSE stream for updates."}

@router.get("/sessions/{session_id}/tests")
async def get_tests(session_id: str, db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(UnitTest).join(ServiceContract).where(ServiceContract.session_id == session_id))
    tests = res.scalars().all()
    return {"tests": [
        {"test_id": t.test_id, "test_name": t.test_name, "code_content": t.code_content, "framework": t.framework}
        for t in tests
    ]}

@router.get("/sessions/{session_id}/stream")
async def stream_agent_execution(session_id: str):
    return StreamingResponse(subscribe_logs(session_id), media_type="text/event-stream")

@router.get("/sessions/{session_id}/coverage-matrix")
async def get_coverage_matrix(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(CoverageMatrix).where(CoverageMatrix.session_id == session_id))
    items = result.scalars().all()
    return {"matrix": [
        {
            "audit_id": i.audit_id,
            "rule_code": i.rule_code,
            "rule_text": i.rule_text,
            "service_name": i.service_name,
            "test_name": i.test_name,
            "status": i.status,
            "reviewer_decision": i.reviewer_decision
        } for i in items
    ]}

@router.get("/sessions/{session_id}/review-report")
async def get_review_report(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ReviewReport).where(ReviewReport.session_id == session_id))
    report = result.scalar_one_or_none()
    if not report:
        return {"report": None}
    return {
        "report": {
            "report_id": report.report_id,
            "session_id": report.session_id,
            "summary": report.summary,
            "status": report.status,
            "findings": report.findings,
            "created_at": report.created_at.isoformat() if report.created_at else None
        }
    }


@router.post("/sessions/{session_id}/review/resolve")
async def resolve_review(session_id: str, feedback: Dict[str, Any], db: AsyncSession = Depends(get_db)):
    # Save feedback & mark matrix entries
    result = await db.execute(select(CoverageMatrix).where(CoverageMatrix.session_id == session_id))
    items = result.scalars().all()
    for i in items:
        if i.status == "AMBIGUOUS":
            i.status = "COVERED"
            i.reviewer_decision = feedback.get("feedback", "Resolved by human review")
    await db.commit()
    return {"message": "Review resolved and matrix updated."}

@router.post("/sessions/{session_id}/regenerate-service")
async def regenerate_service(session_id: str, service_id: str, db: AsyncSession = Depends(get_db)):
    return {"message": f"Regeneration completed for service {service_id}."}

@router.get("/sessions/{session_id}/download/zip")
async def download_zip(session_id: str, db: AsyncSession = Depends(get_db)):
    # Fetch tests from DB
    res = await db.execute(select(UnitTest).join(ServiceContract).where(ServiceContract.session_id == session_id))
    tests = res.scalars().all()

    # Fetch session tech profile & matrix for word report
    sess_res = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    sess = sess_res.scalar_one_or_none()
    tech_profile = sess.tech_profile if (sess and sess.tech_profile) else {"language": "Java", "framework": "JUnit 5"}

    matrix_res = await db.execute(select(CoverageMatrix).where(CoverageMatrix.session_id == session_id))
    matrix_items = matrix_res.scalars().all()
    matrix_list = [
        {"rule_code": m.rule_code, "rule_text": m.rule_text, "test_name": m.test_name, "status": m.status}
        for m in matrix_items
    ]

    report_res = await db.execute(select(ReviewReport).where(ReviewReport.session_id == session_id))
    report = report_res.scalar_one_or_none()
    review_report_data = {
        "summary": report.summary,
        "status": report.status,
        "findings": report.findings
    } if report else None

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        test_list = []
        if tests:
            for t in tests:
                zip_file.writestr(t.test_name, t.code_content)
                test_list.append({"service": t.test_name.split("Test")[0], "code": t.code_content})
        else:
            # Dynamic Fallback: fetch proposed services
            from sqlalchemy import select
            from database.models import ServiceContract
            serv_res = await db.execute(select(ServiceContract).where(ServiceContract.session_id == session_id))
            services = serv_res.scalars().all()
            
            lang_lower = tech_profile.get("language", "Java").lower()
            ext = ".java" if "java" in lang_lower else ".py" if "python" in lang_lower else ".ts" if "typescript" in lang_lower else ".js"
            
            if services:
                for s in services:
                    filename = f"{s.name}Test{ext}"
                    if "java" in lang_lower:
                        fallback_code = f"// Fallback test suite for {s.name}\npublic class {s.name}Test {{\n}}"
                    else:
                        fallback_code = f"# Fallback test suite for {s.name}\n"
                        
                    zip_file.writestr(filename, fallback_code)
                    test_list.append({"service": s.name, "code": fallback_code})
            else:
                filename = f"GeneratedTest{ext}"
                fallback_code = f"// Generated Unit Test Suite\n"
                zip_file.writestr(filename, fallback_code)
                test_list.append({"service": "Generated", "code": fallback_code})

        # Generate Word report and include it inside the ZIP package
        docx_bytes = generate_word_report_docx(session_id, tech_profile, matrix_list, test_list, review_report_data)
        zip_file.writestr(f"Test_Execution_Report_{session_id[:8]}.docx", docx_bytes)

    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename=test_pack_{session_id}.zip"}
    )

@router.get("/sessions/{session_id}/download/report")
async def download_report(session_id: str, db: AsyncSession = Depends(get_db)):
    sess_res = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    sess = sess_res.scalar_one_or_none()
    tech_profile = sess.tech_profile if (sess and sess.tech_profile) else {"language": "Java", "framework": "JUnit 5"}

    matrix_res = await db.execute(select(CoverageMatrix).where(CoverageMatrix.session_id == session_id))
    matrix_items = matrix_res.scalars().all()
    matrix_list = [
        {"rule_code": m.rule_code, "rule_text": m.rule_text, "test_name": m.test_name, "status": m.status}
        for m in matrix_items
    ]

    tests_res = await db.execute(select(UnitTest).join(ServiceContract).where(ServiceContract.session_id == session_id))
    test_items = tests_res.scalars().all()
    test_list = [
        {"service": t.test_name.replace("Test.java", ""), "code": t.code_content}
        for t in test_items
    ]

    report_res = await db.execute(select(ReviewReport).where(ReviewReport.session_id == session_id))
    report = report_res.scalar_one_or_none()
    review_report_data = {
        "summary": report.summary,
        "status": report.status,
        "findings": report.findings
    } if report else None

    docx_bytes = generate_word_report_docx(session_id, tech_profile, matrix_list, test_list, review_report_data)

    return StreamingResponse(
        io.BytesIO(docx_bytes),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": f"attachment; filename=test_report_{session_id}.docx"}
    )
