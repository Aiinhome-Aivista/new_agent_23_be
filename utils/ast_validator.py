import ast

def validate_python_syntax(code: str) -> bool:
    """
    AST/Syntax tree validation to guarantee generated Python code is syntactically correct.
    """
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False

def validate_java_syntax(code: str) -> bool:
    """
    Stub for Java syntax validation. In a real scenario, could use a python-tree-sitter integration
    or an external linter/compiler check.
    """
    # Placeholder: Assuming True for now.
    return True

def validate_csharp_syntax(code: str) -> bool:
    """
    Stub for C# syntax validation.
    """
    # Placeholder: Assuming True for now.
    return True

def validate_syntax(code: str, language: str) -> bool:
    language = language.lower()
    if language == "python":
        return validate_python_syntax(code)
    elif language == "java":
        return validate_java_syntax(code)
    elif language in ["c#", "csharp"]:
        return validate_csharp_syntax(code)
    else:
        # Fallback for unknown languages
        return True
