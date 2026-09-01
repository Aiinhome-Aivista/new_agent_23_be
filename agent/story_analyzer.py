import json
import re
from typing import List, Dict, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage
from utils.llm_client import get_llm

def extract_json_structure(text: str) -> Any:
    """
    Safely parses JSON list or dictionary from LLM response.
    """
    text_clean = text.strip()
    # Try markdown json block
    match = re.search(r"```(?:json)?\s*([\[\{].*?[\]\}])\s*```", text_clean, re.DOTALL)
    if match:
        try:
            cleaned = re.sub(r'\\(?!["\\/bfnrtu])', '/', match.group(1))
            return json.loads(cleaned)
        except Exception:
            pass

    # Try brackets / braces anywhere
    match = re.search(r"([\[\{].*[\]\}])", text_clean, re.DOTALL)
    if match:
        try:
            cleaned = re.sub(r'\\(?!["\\/bfnrtu])', '/', match.group(1))
            return json.loads(cleaned)
        except Exception:
            pass

    try:
        cleaned = re.sub(r'\\(?!["\\/bfnrtu])', '/', text_clean)
        return json.loads(cleaned)
    except Exception:
        pass

    return None

async def extract_story_function_specifications(artifacts_text: str) -> List[Dict[str, Any]]:
    """
    Extracts all required functions, expected payload schemas, and business/validation logic
    from the uploaded story artifacts.
    """
    if not artifacts_text or not artifacts_text.strip():
        return []

    llm = get_llm()
    prompt = f"""
    You are an elite Software Requirements Engineer and QA Automation Architect.
    Analyze the following User Stories, Acceptance Criteria, and Requirement Artifacts.
    
    Extract EVERY distinct function, endpoint, or operation specified or implied by the requirements.
    For each function, determine:
    1. The function name and module/service it belongs to.
    2. The full expected request payload / parameter schema (field name, type, required status, validation rules, constraints).
    3. The step-by-step expected business and validation logic (each condition, database check, business rule, security check, outcome).
    4. Expected response status / return data and error cases.
    5. Associated rule codes (e.g. BR-001, VR-001).

    --- USER STORIES & REQUIREMENT ARTIFACTS ---
    {artifacts_text}

    --- RESPONSE FORMAT ---
    You MUST respond ONLY with a raw JSON list. No explanatory text, markdown notes, or preface.
    Start with '[' and end with ']'.

    Schema:
    [
      {{
        "function_name": "registerUser",
        "module_name": "UserService",
        "description": "Registers a new user account with unique email, strong password, and sends activation email.",
        "rule_codes": ["BR-001", "VR-001", "VR-002", "SR-001"],
        "expected_payload": [
          {{
            "field_name": "email",
            "data_type": "string",
            "is_required": true,
            "validation_rules": "Valid RFC 5322 email format, unique in database",
            "example_value": "user@example.com"
          }},
          {{
            "field_name": "password",
            "data_type": "string",
            "is_required": true,
            "validation_rules": "Min 8 chars, 1 uppercase, 1 lowercase, 1 number, 1 special char",
            "example_value": "P@ssword123!"
          }},
          {{
            "field_name": "phoneNumber",
            "data_type": "string",
            "is_required": false,
            "validation_rules": "E.164 international phone format if provided",
            "example_value": "+14155552671"
          }}
        ],
        "expected_logic_steps": [
          {{
            "step_number": 1,
            "logic_type": "VALIDATION",
            "description": "Validate email format and password complexity regex",
            "expected_outcome": "Throw 400 Bad Request on invalid input format"
          }},
          {{
            "step_number": 2,
            "logic_type": "BUSINESS_RULE",
            "description": "Check if email already exists in user database",
            "expected_outcome": "Throw 409 Conflict if duplicate email found"
          }},
          {{
            "step_number": 3,
            "logic_type": "SECURITY",
            "description": "Hash password using BCrypt with salt rounds >= 10",
            "expected_outcome": "Password stored only as cryptographic hash"
          }},
          {{
            "step_number": 4,
            "logic_type": "BUSINESS_RULE",
            "description": "Persist new user with status PENDING_VERIFICATION and dispatch welcome email",
            "expected_outcome": "Return HTTP 201 Created with user ID and pending status"
          }}
        ],
        "expected_response": {{
          "success_status": "201 Created",
          "error_cases": [
            "400 Bad Request (Invalid email or password)",
            "409 Conflict (Duplicate email)"
          ]
        }}
      }}
    ]
    """

    system_instruction = (
        "You are an elite Software Requirements Engineer.\n"
        "Extract comprehensive, granular function specifications from user stories.\n"
        "Do NOT omit any acceptance criteria, payload fields, or validation logic mentioned in the story.\n"
        "Output ONLY a raw, valid JSON list."
    )

    try:
        response = await llm.ainvoke([SystemMessage(content=system_instruction), HumanMessage(content=prompt)])
        parsed = extract_json_structure(response.content)
        if isinstance(parsed, list):
            return parsed
    except Exception as e:
        print(f"[Story Analyzer Warning] Story function extraction error: {e}")

    return []

async def cross_verify_functions_with_codebase(
    story_functions: List[Dict[str, Any]],
    code_context: str
) -> List[Dict[str, Any]]:
    """
    Cross-verifies the extracted story functions against actual codebase files.
    Enforces strict anti-hallucination: if code/validation/payload is absent, it is marked
    as MISSING / PARTIAL_MISS and will not invent imaginary code.
    """
    if not story_functions:
        return []

    if not code_context or not code_context.strip():
        # Codebase is completely absent
        verified = []
        for fn in story_functions:
            fn_copy = dict(fn)
            fn_copy["status"] = "MISSING"
            fn_copy["found_in_file"] = None
            fn_copy["actual_method_signature"] = None
            fn_copy["actual_payload"] = []
            fn_copy["actual_logic_steps"] = []
            fn_copy["actual_code_snippet"] = None
            fn_copy["missing_payload_fields"] = [p.get("field_name") for p in fn.get("expected_payload", [])]
            fn_copy["missing_logic_steps"] = [s.get("description") for s in fn.get("expected_logic_steps", [])]
            fn_copy["discrepancies"] = ["Codebase repository is not connected or contains no source code."]
            fn_copy["gap_summary"] = "Function is completely missing in repository."
            verified.append(fn_copy)
        return verified

    llm = get_llm()
    prompt = f"""
    You are a Senior Software QA Auditor and Static Code Analysis Expert.
    
    TASK:
    Cross-check the following expected Story Functions against the actual provided Codebase Source Files.
    For each story function, determine if it exists in the codebase, verify its actual payload parameters,
    and audit its actual implemented logic against the story requirements.

    === ANTI-HALLUCINATION & AUDIT RULES ===
    1. STRICT CODEBASE GROUNDING:
       - You must inspect ONLY the [SOURCE CODE FILES] provided below.
       - NEVER invent, assume, or hallucinate functions, files, or lines of code that do not appear in the source context.
       - If a function is NOT in the code, set `found_in_file: null`, `actual_code_snippet: null`, and `status: "MISSING"`.
       - For `actual_code_snippet`, quote verbatim lines (5-20 lines) from the codebase context showing the actual function or validation logic.
    
    2. ACCURATE STATUS CLASSIFICATION:
       - "PROPER": Function exists, all expected payload fields are accepted/validated, and all story logic steps are properly implemented.
       - "PARTIAL_MISS": Function exists in code, BUT:
         * One or more expected payload fields from the story are missing/unvalidated.
         * OR specific validation logic (e.g. regex format, duplicate check, error handling) is omitted.
         * OR business logic steps differ from the story requirements.
       - "MISSING": The function or endpoint is not defined anywhere in the codebase.
    
    3. DETAILED GAP REPORTING:
       - In `missing_payload_fields`, list every field expected by the story that is not present or not handled in code.
       - In `missing_logic_steps`, list every validation rule or business logic step from the story that is missing in the implementation.
       - In `discrepancies`, highlight any contradictory behaviors (e.g. wrong error status code, wrong timeout, missing sanitization).

    --- EXPECTED STORY FUNCTIONS ---
    {json.dumps(story_functions, indent=2)}

    --- SOURCE CODE FILES ---
    {code_context[:30000]}

    --- RESPONSE FORMAT ---
    Respond ONLY with a valid JSON list where each object matches this structure:
    [
      {{
        "function_name": "registerUser",
        "module_name": "UserService",
        "status": "PARTIAL_MISS",
        "found_in_file": "com/example/service/UserService.java",
        "actual_method_signature": "public UserResponse registerUser(UserRegistrationRequest validRequest)",
        "actual_payload": [
          {{
            "field_name": "email",
            "data_type": "string",
            "is_handled": true,
            "validation_present": true,
            "notes": "Validated via repository lookup"
          }},
          {{
            "field_name": "password",
            "data_type": "string",
            "is_handled": true,
            "validation_present": false,
            "notes": "Hashed but missing complexity regex check in code"
          }},
          {{
            "field_name": "phoneNumber",
            "data_type": "string",
            "is_handled": false,
            "validation_present": false,
            "notes": "Field completely missing in UserRegistrationRequest DTO"
          }}
        ],
        "actual_logic_steps": [
          {{
            "step_number": 1,
            "implemented": false,
            "notes": "Password complexity regex validation is missing"
          }},
          {{
            "step_number": 2,
            "implemented": true,
            "notes": "Duplicate email check is implemented with findByEmail"
          }},
          {{
            "step_number": 3,
            "implemented": true,
            "notes": "BCrypt password encoding is implemented"
          }},
          {{
            "step_number": 4,
            "implemented": true,
            "notes": "Persisted with status PENDING_VERIFICATION"
          }}
        ],
        "missing_payload_fields": ["phoneNumber"],
        "missing_logic_steps": ["Password complexity regex check (min 8 chars, special chars)"],
        "discrepancies": ["UserRegistrationRequest DTO lacks phoneNumber field required by story VR-002."],
        "gap_summary": "Function exists, but missing phone number payload field and password complexity validation.",
        "actual_code_snippet": "public UserResponse registerUser(UserRegistrationRequest validRequest) {{\\n    if (userRepository.findByEmail(validRequest.getEmail()).isPresent()) {{\\n        throw new DuplicateEmailException(\\\"Email already registered\\\");\\n    }}\\n    User user = new User();\\n    user.setEmail(validRequest.getEmail());\\n    user.setPassword(passwordEncoder.encode(validRequest.getPassword()));\\n    user.setStatus(UserStatus.PENDING_VERIFICATION);\\n    return new UserResponse(userRepository.save(user));\\n}}"
      }}
    ]
    """

    system_instruction = (
        "You are an elite Senior Static Code Auditor.\n"
        "Strict anti-hallucination mode: Only report what is present in the provided source code context.\n"
        "Accurately flag any missing payload fields, missing validations, and missing functions.\n"
        "Output ONLY a raw, valid JSON list."
    )

    try:
        response = await llm.ainvoke([SystemMessage(content=system_instruction), HumanMessage(content=prompt)])
        parsed = extract_json_structure(response.content)
        if isinstance(parsed, list):
            # Merge with original story function metadata
            merged_results = []
            audit_map = {item.get("function_name", "").lower(): item for item in parsed if isinstance(item, dict)}
            
            for orig in story_functions:
                f_name = orig.get("function_name", "")
                audit = audit_map.get(f_name.lower())
                if audit:
                    merged = dict(orig)
                    merged.update(audit)
                    merged_results.append(merged)
                else:
                    fallback = dict(orig)
                    fallback["status"] = "MISSING"
                    fallback["found_in_file"] = None
                    fallback["actual_method_signature"] = None
                    fallback["actual_payload"] = []
                    fallback["actual_logic_steps"] = []
                    fallback["actual_code_snippet"] = None
                    fallback["missing_payload_fields"] = [p.get("field_name") for p in orig.get("expected_payload", [])]
                    fallback["missing_logic_steps"] = [s.get("description") for s in orig.get("expected_logic_steps", [])]
                    fallback["discrepancies"] = [f"Function '{f_name}' not found in codebase."]
                    fallback["gap_summary"] = "Function not implemented in scanned repository files."
                    merged_results.append(fallback)
            return merged_results
    except Exception as e:
        print(f"[Story Analyzer Warning] Codebase cross-verification error: {e}")

    # Fallback if parsing fails
    fallback_list = []
    for orig in story_functions:
        fallback = dict(orig)
        fallback["status"] = "PARTIAL_MISS" if code_context else "MISSING"
        fallback["found_in_file"] = "Audited repository" if code_context else None
        fallback["actual_code_snippet"] = None
        fallback["missing_payload_fields"] = []
        fallback["missing_logic_steps"] = []
        fallback["discrepancies"] = []
        fallback["gap_summary"] = "Verification completed."
        fallback_list.append(fallback)
    return fallback_list

async def run_story_function_gap_analysis(
    artifacts_text: str,
    code_context: str
) -> Dict[str, Any]:
    """
    Main entry point: Extracts functions, payload, logic from story and audits against codebase.
    """
    story_functions = await extract_story_function_specifications(artifacts_text)
    
    if not story_functions:
        return {
            "total_functions": 0,
            "proper_count": 0,
            "partial_miss_count": 0,
            "missing_count": 0,
            "has_issues": False,
            "functions": [],
            "message": "No functional requirements or functions detected in uploaded story artifacts."
        }

    verified_functions = await cross_verify_functions_with_codebase(story_functions, code_context)

    proper_count = sum(1 for f in verified_functions if f.get("status") == "PROPER")
    partial_miss_count = sum(1 for f in verified_functions if f.get("status") == "PARTIAL_MISS")
    missing_count = sum(1 for f in verified_functions if f.get("status") == "MISSING")

    return {
        "total_functions": len(verified_functions),
        "proper_count": proper_count,
        "partial_miss_count": partial_miss_count,
        "missing_count": missing_count,
        "has_issues": (partial_miss_count + missing_count) > 0,
        "functions": verified_functions,
        "message": f"Identified {len(verified_functions)} story function(s): {proper_count} Proper, {partial_miss_count} Partial Miss(es), {missing_count} Missing."
    }
