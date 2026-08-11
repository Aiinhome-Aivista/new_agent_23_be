import re
import ast

def scan_for_secrets(text: str) -> bool:
    """
    A basic regex and heuristic secrets scanner to redact API keys, 
    Bearer tokens, and passwords from uploaded artifacts.
    Returns True if a secret might be present.
    """
    secret_patterns = [
        r"(?i)api_?key\s*[:=]\s*['\"][a-zA-Z0-9_\-]+['\"]",
        r"(?i)bearer\s+[a-zA-Z0-9_\-\.]+",
        r"(?i)password\s*[:=]\s*['\"][^'\"]+['\"]"
    ]
    for pattern in secret_patterns:
        if re.search(pattern, text):
            return True
    return False

def redact_secrets(text: str) -> str:
    """
    Replaces matched secrets with [REDACTED].
    """
    secret_patterns = [
        r"(?i)(api_?key\s*[:=]\s*)['\"][a-zA-Z0-9_\-]+['\"]",
        r"(?i)(bearer\s+)[a-zA-Z0-9_\-\.]+",
        r"(?i)(password\s*[:=]\s*)['\"][^'\"]+['\"]"
    ]
    redacted_text = text
    for pattern in secret_patterns:
        redacted_text = re.sub(pattern, r"\1[REDACTED]", redacted_text)
    return redacted_text

def detect_prompt_injection(text: str) -> bool:
    """
    Prompt injection detector to neutralize jailbreak attempts.
    """
    jailbreak_keywords = [
        "ignore previous instructions",
        "forget all previous",
        "you are now",
        "system prompt",
        "override prompt"
    ]
    lower_text = text.lower()
    for keyword in jailbreak_keywords:
        if keyword in lower_text:
            return True
    return False
