import re
from typing import Any

def validate_scl(code: str, block_name: str | None = None, block_type: str = "FB") -> dict[str, Any]:
    """Basic SCL structure checks; not a TIA Portal compiler."""
    if not isinstance(code, str) or not code.strip():
        return {"valid": False, "errors": ["SCL code is empty."], "warnings": []}
    errors, warnings = [], []
    kind = (block_type or "FB").strip().upper()
    if kind not in {"FB", "FC"}:
        return {"valid": False, "errors": ["block_type must be FB or FC."], "warnings": []}
    cleaned = re.sub(r"//[^\n]*", "", code)
    cleaned = re.sub(r"\(\*.*?\*\)", "", cleaned, flags=re.S)
    if "```" in cleaned:
        errors.append("Markdown code fences are not valid SCL source.")
    start, end = ("FUNCTION_BLOCK", "END_FUNCTION_BLOCK") if kind == "FB" else ("FUNCTION", "END_FUNCTION")
    if block_name:
        name = re.escape(block_name.strip())
        if kind == "FB":
            match = re.search(r'\bFUNCTION_BLOCK\s+(?:"' + name + r'"|' + name + r')(?=\s|$)', cleaned, re.I)
        else:
            match = re.search(r'\bFUNCTION\s+(?:"' + name + r'"|' + name + r')\s*:', cleaned, re.I)
        if not match:
            errors.append(f"The source does not declare the requested {kind} '{block_name}'.")
    declarations = re.findall(r"\bFUNCTION_BLOCK\b|\bFUNCTION\b|\bORGANIZATION_BLOCK\b", cleaned, re.I)
    if len(declarations) != 1:
        errors.append(f"Expected exactly one supported block declaration; found {len(declarations)}.")
    if not re.search(rf"\b{start}\b", cleaned, re.I):
        errors.append(f"No {start} declaration was found.")
    if not re.search(rf"\b{end}\b", cleaned, re.I):
        errors.append(f"No matching {end} ending was found.")
    if not re.search(r"\bBEGIN\b", cleaned, re.I):
        errors.append("The source is missing the BEGIN implementation section.")
    for a, b in (("IF","END_IF"),("CASE","END_CASE"),("FOR","END_FOR"),("WHILE","END_WHILE"),("REPEAT","UNTIL")):
        ac = len(re.findall(rf"\b{a}\b", cleaned, re.I))
        bc = len(re.findall(rf"\b{b}\b", cleaned, re.I))
        if ac != bc:
            errors.append(f"{a}/{b} count mismatch: found {ac} start(s) and {bc} ending(s).")
    depth = 0
    for ch in cleaned:
        depth += (ch == "(") - (ch == ")")
        if depth < 0:
            errors.append("A closing parenthesis appears before its opening.")
            break
    if depth > 0:
        errors.append("One or more opening parentheses are not closed.")
    if re.search(r"\b(TODO|FIXME|PLACEHOLDER)\b", code, re.I):
        warnings.append("The source contains unfinished placeholders.")
    if "END_VAR" not in cleaned.upper():
        warnings.append("No END_VAR declaration found; confirm the block interface.")
    warnings += [
        "These are basic text checks, not TIA Portal compiler validation.",
        "Review declarations, data types, process behavior and interlocks in TIA Portal."
    ]
    return {"valid": not errors, "errors": errors, "warnings": warnings}

def validate_scl_structure(code: str, block_name: str | None = None, block_type: str = "FB") -> list[str]:
    """Compatibility wrapper used by main.py."""
    return validate_scl(code, block_name, block_type)["errors"]
