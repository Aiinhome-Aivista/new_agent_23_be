import json
import yaml
import os
from typing import Dict, Any, Tuple

def parse_artifact_file(filename: str, file_bytes: bytes) -> Tuple[str, Dict[str, Any], str]:
    """
    Parses uploaded artifact files (MD, TXT, JSON, YAML, SQL) and extracts raw text, 
    metadata dictionary, and document type.
    """
    ext = os.path.splitext(filename)[1].lower()
    text_content = ""
    metadata = {"filename": filename, "extension": ext, "size_bytes": len(file_bytes)}
    doc_type = "UNKNOWN"

    try:
        raw_decoded = file_bytes.decode('utf-8', errors='ignore')
    except Exception:
        raw_decoded = ""

    if ext in ['.json']:
        try:
            data = json.loads(raw_decoded)
            text_content = json.dumps(data, indent=2)
            metadata["parsed_structure"] = "JSON"
            if "openapi" in data or "swagger" in data or "paths" in data:
                doc_type = "API_SPEC"
            else:
                doc_type = "STRUCTURED_DATA"
        except Exception:
            text_content = raw_decoded
            doc_type = "RAW_TEXT"

    elif ext in ['.yaml', '.yml']:
        try:
            data = yaml.safe_load(raw_decoded)
            text_content = yaml.dump(data, default_flow_style=False)
            metadata["parsed_structure"] = "YAML"
            if isinstance(data, dict) and ("openapi" in data or "swagger" in data or "paths" in data):
                doc_type = "API_SPEC"
            else:
                doc_type = "STRUCTURED_SPEC"
        except Exception:
            text_content = raw_decoded
            doc_type = "RAW_TEXT"

    elif ext in ['.md', '.markdown']:
        text_content = raw_decoded
        doc_type = "BUSINESS_REQUIREMENT"
        metadata["format"] = "MARKDOWN"

    elif ext in ['.sql']:
        text_content = raw_decoded
        doc_type = "DATABASE_SCHEMA"
        metadata["format"] = "SQL"

    elif ext in ['.docx']:
        # Basic text extraction from docx raw XML / text
        text_content = raw_decoded
        doc_type = "BUSINESS_REQUIREMENT"
        metadata["format"] = "DOCX"

    else:
        text_content = raw_decoded
        doc_type = "GENERAL_DOCUMENT"
        metadata["format"] = "TEXT"

    return text_content, metadata, doc_type
