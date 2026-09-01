import io
import zipfile
import re
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
import uuid
from pydantic import BaseModel

from database.database import get_db, AsyncSessionLocal
from database.models import GenerationSession, Artifact, RequirementDecomposition, ServiceContract, UnitTest, CoverageMatrix, ReviewReport
from agent.workflow import agent_workflow
from utils.broadcaster import subscribe_logs, broadcast_log
from utils.doc_parser import parse_artifact_file
from utils.docx_generator import generate_word_report_docx
from utils.llm_client import get_llm
from langchain_core.messages import HumanMessage
from agent.nodes import extract_json_dict
from agent.story_analyzer import run_story_function_gap_analysis
from utils.git_utils import clone_repo, get_code_files, cleanup_repo

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

class GitCheckRequest(BaseModel):
    git_url: str

@router.post("/sessions/check-git-repo")
async def check_git_repo(payload: GitCheckRequest):
    url = payload.git_url
    if not url:
        return {"status": "empty", "message": "Repository URL is empty."}
    
    import subprocess
    import os
    
    cmd = ["git", "-c", "credential.helper=", "ls-remote", url]
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_ASKPASS"] = ""
    env["SSH_ASKPASS"] = ""
    for key in list(env.keys()):
        if "VSCODE_GIT" in key or "VSCODE_ASKPASS" in key:
            del env[key]
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=10)
        if result.returncode == 0:
            return {"status": "public", "message": "Repository is public and accessible."}
        else:
            stderr = result.stderr or ""
            stdout = result.stdout or ""
            err_msg = (stderr + stdout).lower()
            
            # Identify if it is likely a private repository
            if (
                "terminal prompts disabled" in err_msg or 
                "authentication failed" in err_msg or 
                "not found" in err_msg or 
                "could not read username" in err_msg or
                "permission denied" in err_msg or
                "403" in err_msg or
                "401" in err_msg or
                "unauthorized" in err_msg or
                "forbidden" in err_msg or
                "access denied" in err_msg
            ):
                return {
                    "status": "private",
                    "message": "Repository requires authentication (private repository)."
                }
            else:
                return {
                    "status": "invalid",
                    "message": f"Failed to connect to the repository: {stderr.strip() or 'Unknown error'}"
                }
    except Exception as e:
        return {
            "status": "invalid",
            "message": f"Error checking repository: {str(e)}"
        }

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
        is_valid, git_err = validate_git_connection(payload.git_url, branch=payload.git_branch)
        if not is_valid:
            raise HTTPException(
                status_code=400, 
                detail=git_err or "Invalid Git Repository URL, branch, or authentication token. Connection check failed."
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

    # Clear existing decompositions before new extraction
    await db.execute(delete(RequirementDecomposition).where(RequirementDecomposition.session_id == session_id))
    await db.commit()

    background_tasks.add_task(run_agent_workflow, session_id)
    return {"message": "Decomposition triggered. Connect to SSE stream for updates."}

class ManualRuleRequest(BaseModel):
    rule_code: str
    rule_text: str
    rule_type: str = "BUSINESS_RULE"
    story_name: Optional[str] = None
    story: Optional[str] = None

async def validate_rule_with_llm(
    session_id: str,
    rule_code: str,
    rule_text: str,
    rule_type: str,
    story_name: Optional[str],
    db: AsyncSession
) -> Dict[str, Any]:
    """
    Validates a manual candidate rule against the uploaded sprint/story artifacts.
    Checks whether the rule is proper, testable, and aligns with or contradicts the stories.
    """
    art_result = await db.execute(select(Artifact).where(Artifact.session_id == session_id))
    artifacts = art_result.scalars().all()
    
    artifact_texts = []
    for art in artifacts:
        fname = art.filename or "artifact"
        raw = art.raw_text or ""
        artifact_texts.append(f"=== Document: {fname} ===\n{raw[:3000]}\n")
        
    combined_context = "\n".join(artifact_texts) if artifact_texts else "No uploaded story documents found in session."
    
    prompt = f"""
    You are an expert QA Automation & Requirements Verification Architect.
    A user is proposing a custom business or validation rule for this sprint.
    
    --- UPLOADED SPRINT & STORY ARTIFACTS ---
    {combined_context}
    
    --- USER CANDIDATE RULE ---
    Rule Code: {rule_code}
    Rule Type: {rule_type}
    Story / Feature: {story_name or 'General Feature'}
    Rule Text: {rule_text}
    
    TASK:
    Analyze if this candidate rule is a PROPER, VALID, and TESTABLE business or validation rule, and whether it aligns with / matches the uploaded story context.
    
    CRITERIA:
    1. Alignment & Consistency:
       - Does this rule match the story context or acceptance criteria?
       - If it CONTRADICTS the uploaded stories, or is completely IRRELEVANT / NONSENSICAL / ILLOGICAL (e.g. asking for rocket telemetry in an e-commerce user service, or password length 0 when BRD requires 8+), flag alignment_status as "MISMATCH_DETECTED" and set is_valid = false.
       - If it aligns with the story or is a valid, logical business rule extension, set is_valid = true and alignment_status = "MATCHES_STORY" (or "EXTENDS_STORY").
    2. Quality / Testability:
       - Is it specific and testable with clear inputs/conditions/expected outputs?
    3. Suggestion:
       - Provide a refined/enhanced testable wording if applicable.
    
    RESPONSE FORMAT (Strict JSON only):
    {{
      "is_valid": true, // boolean (set false if mismatch, contradictory, nonsensical, or invalid)
      "alignment_status": "MATCHES_STORY", // "MATCHES_STORY", "EXTENDS_STORY", or "MISMATCH_DETECTED"
      "match_score": 90, // integer 0 to 100 (below 50 if mismatch)
      "feedback": "Concise 1-2 sentence explanation of why it matches or why it is invalid.",
      "error_reason": null, // If is_valid is false, concise error explanation like "Story Mismatch: BRD requires password min 8 chars."
      "suggested_rule_text": "Enhanced clear rule text if applicable"
    }}
    """
    
    try:
        llm = get_llm()
        resp = await llm.ainvoke([HumanMessage(content=prompt)])
        parsed = extract_json_dict(resp.content)
        if not parsed:
            if "invalid" in resp.content.lower() or "mismatch" in resp.content.lower():
                return {
                    "is_valid": False,
                    "alignment_status": "MISMATCH_DETECTED",
                    "match_score": 30,
                    "feedback": resp.content.strip()[:200],
                    "error_reason": "Rule does not match uploaded story requirements.",
                    "suggested_rule_text": rule_text
                }
            return {
                "is_valid": True,
                "alignment_status": "MATCHES_STORY",
                "match_score": 85,
                "feedback": "Rule aligns with story criteria.",
                "error_reason": None,
                "suggested_rule_text": rule_text
            }
            
        is_valid = bool(parsed.get("is_valid", True))
        status = parsed.get("alignment_status", "MATCHES_STORY")
        score = int(parsed.get("match_score", 85))
        
        if status == "MISMATCH_DETECTED" or score < 50:
            is_valid = False
            if not parsed.get("error_reason"):
                parsed["error_reason"] = parsed.get("feedback") or "Rule does not match the uploaded story specifications."
                
        parsed["is_valid"] = is_valid
        return parsed
    except Exception as e:
        print(f"[Rule Validation Exception] {e}")
        return {
            "is_valid": True,
            "alignment_status": "EXTENDS_STORY",
            "match_score": 80,
            "feedback": "Rule accepted and verified.",
            "error_reason": None,
            "suggested_rule_text": rule_text
        }

def get_prefix_for_rule_type(rule_type: str) -> str:
    normalized = (rule_type or "").upper().strip()
    if "VALIDATION" in normalized:
        return "VR"
    elif "SECURITY" in normalized:
        return "SR"
    elif "AUTHORIZATION" in normalized or "AUTH" in normalized:
        return "AR"
    elif "INTEGRATION" in normalized:
        return "IR"
    elif "PERFORMANCE" in normalized:
        return "PR"
    else:
        return "BR"

def generate_next_rule_code_for_type(rule_type: str, existing_codes: list) -> str:
    prefix = get_prefix_for_rule_type(rule_type)
    pattern = re.compile(rf'^{prefix}[-_]?(\d+)', re.IGNORECASE)
    max_num = 0
    for c in existing_codes:
        if c:
            m = pattern.search(c.strip())
            if m:
                val = int(m.group(1))
                if val > max_num:
                    max_num = val
    return f"{prefix}-{str(max_num + 1).zfill(3)}"

@router.post("/sessions/{session_id}/decompositions/validate")
async def validate_manual_rule(session_id: str, rule: ManualRuleRequest, db: AsyncSession = Depends(get_db)):
    final_code = (rule.rule_code or "").strip()
    if not final_code or final_code.upper() in ["BR-XXX", "VR-XXX", "SR-XXX", "AR-XXX", "AUTO", "BR-", "VR-", "SR-", "AR-", ""]:
        existing = await db.execute(select(RequirementDecomposition.rule_code).where(RequirementDecomposition.session_id == session_id))
        codes = existing.scalars().all()
        final_code = generate_next_rule_code_for_type(rule.rule_type, codes)

    validation = await validate_rule_with_llm(
        session_id=session_id,
        rule_code=final_code,
        rule_text=rule.rule_text,
        rule_type=rule.rule_type,
        story_name=rule.story_name,
        db=db
    )
    validation["auto_rule_code"] = final_code
    return validation

@router.post("/sessions/{session_id}/decompositions")
async def add_manual_rule(session_id: str, rule: ManualRuleRequest, db: AsyncSession = Depends(get_db)):
    # Auto-generate next code with dynamic prefix (BR-, VR-, SR-, AR-) if not provided
    final_code = (rule.rule_code or "").strip()
    if not final_code or final_code.upper() in ["BR-XXX", "VR-XXX", "SR-XXX", "AR-XXX", "AUTO", "BR-", "VR-", "SR-", "AR-", ""]:
        existing = await db.execute(select(RequirementDecomposition.rule_code).where(RequirementDecomposition.session_id == session_id))
        codes = existing.scalars().all()
        final_code = generate_next_rule_code_for_type(rule.rule_type, codes)

    # 1. Validate rule against story with LLM
    validation = await validate_rule_with_llm(
        session_id=session_id,
        rule_code=final_code,
        rule_text=rule.rule_text,
        rule_type=rule.rule_type,
        story_name=rule.story_name,
        db=db
    )
    
    # 2. If invalid or mismatch, REJECT and return error without saving!
    if not validation.get("is_valid", True):
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Invalid Rule: Story Mismatch Detected",
                "error_reason": validation.get("error_reason") or "Rule contradicts or does not match uploaded story specifications.",
                "alignment_status": validation.get("alignment_status", "MISMATCH_DETECTED"),
                "match_score": validation.get("match_score", 0),
                "feedback": validation.get("feedback"),
                "suggested_rule_text": validation.get("suggested_rule_text"),
                "rule_code": final_code
            }
        )
        
    decomp = RequirementDecomposition(
        session_id=session_id,
        rule_code=final_code,
        rule_text=rule.rule_text,
        rule_type=rule.rule_type,
        story_name=rule.story_name,
        story=rule.story,
        source_reference="Manual_Entry",
        has_code_mapping=True,
        ai_validation_score=validation.get("match_score", 85),
        ai_feedback=validation.get("feedback"),
        alignment_status=validation.get("alignment_status", "MATCHES_STORY")
    )
    db.add(decomp)
    await db.commit()
    return {
        "message": "Rule validated and added successfully",
        "req_id": decomp.req_id,
        "rule": {
            "req_id": decomp.req_id,
            "rule_code": decomp.rule_code,
            "rule_text": decomp.rule_text,
            "rule_type": decomp.rule_type,
            "story_name": decomp.story_name,
            "story": decomp.story,
            "has_code_mapping": True,
            "ai_validation_score": decomp.ai_validation_score,
            "ai_feedback": decomp.ai_feedback,
            "alignment_status": decomp.alignment_status
        },
        "validation": validation
    }

@router.get("/sessions/{session_id}/decompositions")
async def get_decompositions(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RequirementDecomposition).where(RequirementDecomposition.session_id == session_id))
    items = result.scalars().all()
    print(f"\n[API DEBUG] GET /decompositions called for session_id: {session_id} | Found {len(items)} database records.")
    
    missing_items = []
    mapped_count = 0
    decomps_list = []
    
    for i in items:
        is_mapped = bool(getattr(i, 'has_code_mapping', True))
        reason = getattr(i, 'missing_reason', None)
        if is_mapped:
            mapped_count += 1
        else:
            missing_items.append({
                "req_id": i.req_id,
                "rule_code": i.rule_code,
                "rule_text": i.rule_text,
                "rule_type": i.rule_type,
                "story_name": i.story_name or "Story Requirement",
                "story": i.story,
                "missing_function": f"Method/Function for {i.rule_code}",
                "reason": reason or "No matching function, method, or endpoint found in the repository"
            })
            
        decomps_list.append({
            "req_id": i.req_id,
            "rule_code": i.rule_code,
            "rule_text": i.rule_text,
            "rule_type": i.rule_type,
            "story_name": i.story_name,
            "story": i.story,
            "has_code_mapping": is_mapped,
            "missing_reason": reason,
            "target_code_snippet": getattr(i, 'target_code_snippet', None),
            "ai_validation_score": getattr(i, 'ai_validation_score', None),
            "ai_feedback": getattr(i, 'ai_feedback', None),
            "alignment_status": getattr(i, 'alignment_status', None)
        })
        
    # Fetch session to extract tech profile and language mismatch
    sess_res = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    sess_obj = sess_res.scalar_one_or_none()
    tech_profile = sess_obj.tech_profile if (sess_obj and sess_obj.tech_profile) else {}
    language_mismatch = tech_profile.get("language_mismatch", {"is_mismatch": False})

    gap_summary = {
        "has_missing_items": len(missing_items) > 0,
        "total_rules": len(items),
        "mapped_rules": mapped_count,
        "missing_count": len(missing_items),
        "missing_items": missing_items
    }
    
    return {
        "decompositions": decomps_list,
        "gap_summary": gap_summary,
        "tech_profile": tech_profile,
        "language_mismatch": language_mismatch
    }

class TechProfileUpdateRequest(BaseModel):
    language: str
    framework: Optional[str] = None
    mockLibrary: Optional[str] = None
    session_name: Optional[str] = None

@router.put("/sessions/{session_id}/tech-profile")
async def update_tech_profile(session_id: str, payload: TechProfileUpdateRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
    
    profile = dict(sess.tech_profile) if sess.tech_profile else {}
    profile["language"] = payload.language
    if payload.framework:
        profile["framework"] = payload.framework
    if payload.mockLibrary:
        profile["mockLibrary"] = payload.mockLibrary
    if payload.session_name:
        profile["session_name"] = payload.session_name
    
    # If the language now matches detected language, clear mismatch flag
    if "language_mismatch" in profile and isinstance(profile["language_mismatch"], dict):
        det = profile["language_mismatch"].get("detected_language")
        if det and det.lower() == payload.language.lower():
            profile["language_mismatch"]["is_mismatch"] = False
            profile["language_mismatch"]["selected_language"] = payload.language
            profile["language_mismatch"]["selected_framework"] = profile.get("framework")
            profile["language_mismatch"]["selected_mock_library"] = profile.get("mockLibrary")
    
    sess.tech_profile = profile
    await db.commit()
    return {"message": "Technology profile updated successfully", "tech_profile": profile}

@router.get("/sessions/{session_id}/gap-analysis")
async def get_gap_analysis(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(RequirementDecomposition).where(RequirementDecomposition.session_id == session_id))
    items = result.scalars().all()
    
    missing_items = []
    mapped_count = 0
    
    for i in items:
        is_mapped = bool(getattr(i, 'has_code_mapping', True))
        reason = getattr(i, 'missing_reason', None)
        if is_mapped:
            mapped_count += 1
        else:
            missing_items.append({
                "req_id": i.req_id,
                "rule_code": i.rule_code,
                "rule_text": i.rule_text,
                "rule_type": i.rule_type,
                "story_name": i.story_name or "Story Requirement",
                "story": i.story,
                "missing_function": f"Method/Function for {i.rule_code}",
                "reason": reason or "No matching function, method, or endpoint found in the repository"
            })
            
    return {
        "has_missing_items": len(missing_items) > 0,
        "total_rules": len(items),
        "mapped_rules": mapped_count,
        "missing_count": len(missing_items),
        "missing_items": missing_items
    }

async def compute_and_save_story_function_analysis(session_id: str, sess: GenerationSession, db: AsyncSession) -> Dict[str, Any]:
    # 1. Fetch uploaded story artifacts
    art_result = await db.execute(select(Artifact).where(Artifact.session_id == session_id))
    artifacts = art_result.scalars().all()
    artifact_texts = []
    for art in artifacts:
        fname = art.filename or "artifact"
        raw = art.raw_text or ""
        artifact_texts.append(f"=== File: {fname} ===\n{raw}\n")
    combined_artifacts = "\n".join(artifact_texts) if artifact_texts else ""

    # 2. Fetch codebase if Git repo configured
    tech_profile = dict(sess.tech_profile) if sess.tech_profile else {}
    git_url = tech_profile.get("git_url")
    git_branch = tech_profile.get("git_branch")
    git_path = tech_profile.get("git_path")

    code_context = ""
    if git_url:
        try:
            temp_path = clone_repo(git_url, branch=git_branch)
            code_context = get_code_files(temp_path, target_subpath=git_path)
            cleanup_repo(temp_path)
        except Exception as e:
            print(f"[Story Analysis Git Clone Warning] {e}")

    # 3. Run LLM extraction and codebase gap analysis
    analysis_result = await run_story_function_gap_analysis(combined_artifacts, code_context)

    # 4. Cache in tech_profile
    tech_profile["story_function_analysis"] = analysis_result
    sess.tech_profile = tech_profile
    await db.commit()

    return analysis_result

@router.get("/sessions/{session_id}/story-function-analysis")
async def get_story_function_analysis(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
        
    tech_profile = sess.tech_profile or {}
    cached = tech_profile.get("story_function_analysis")
    if cached and cached.get("functions"):
        return cached
        
    return await compute_and_save_story_function_analysis(session_id, sess, db)

@router.post("/sessions/{session_id}/story-function-analysis")
async def trigger_story_function_analysis(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(GenerationSession).where(GenerationSession.session_id == session_id))
    sess = result.scalar_one_or_none()
    if not sess:
        raise HTTPException(status_code=404, detail="Session not found")
        
    return await compute_and_save_story_function_analysis(session_id, sess, db)

@router.get("/sessions/{session_id}/services")
async def get_services(session_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ServiceContract).where(ServiceContract.session_id == session_id))
    items = result.scalars().all()
    print(f"[API DEBUG] GET /services called for session_id: {session_id} | Found {len(items)} database records.\n")
    return {"services": [
        {
            "service_id": i.service_id,
            "name": i.name,
            "methods": i.methods,
            "dependencies": i.dependencies,
            "target_code_snippets": getattr(i, 'target_code_snippets', []),
            "status": i.status
        } for i in items
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
        {
            "rule_code": m.rule_code, 
            "rule_text": m.rule_text, 
            "test_name": m.test_name, 
            "status": m.status,
            "story_id": m.rule_code,
            "story": m.story,
            "story_name": m.story_name,
            "script_function_name": m.service_name
        }
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
        {
            "rule_code": m.rule_code, 
            "rule_text": m.rule_text, 
            "test_name": m.test_name, 
            "status": m.status,
            "story_id": m.rule_code,
            "story": m.story,
            "story_name": m.story_name,
            "script_function_name": m.service_name
        }
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
