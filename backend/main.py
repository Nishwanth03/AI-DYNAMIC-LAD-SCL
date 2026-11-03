from pathlib import Path
import json
import os
import re
import subprocess

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from scl_validator import validate_scl, validate_scl_structure


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

BASE_DIR = Path(os.getenv("AI_PLC_AGENT_DIR", str(Path(__file__).resolve().parents[1]))).resolve()
OUTPUT_DIR = BASE_DIR / "generated"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OLLAMA_URL = os.getenv(
    "OLLAMA_URL", "http://127.0.0.1:11434"
).rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

TIA_WORKER_EXE = os.getenv(
    "TIA_WORKER_EXE",
    str(BASE_DIR / "tia-bridge" / "TIAOpennessWorker" / "bin" / "Debug" / "TIAOpennessWorker.exe"),
)
# Project and PLC are selected dynamically from open TIA Portal instances.
# No project or PLC is selected by default.

app = FastAPI(
    title="AI PLC Agent",
    description="Local AI-assisted Siemens TIA Portal V19 SCL and LAD workflow",
    version="1.2.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------
# Request / response models
# ---------------------------------------------------------

class LogicRequest(BaseModel):
    requirement: str = Field(min_length=10, max_length=5000)
    block_name: str = "FB_PumpControl"
    block_type: str = "FB"


class LogicResponse(BaseModel):
    status: str
    block_name: str
    requirement: str
    assumptions: list[str]
    scl_code: str
    warnings: list[str]


class ImportRequest(BaseModel):
    block_name: str = Field(min_length=1, max_length=60)
    block_type: str = "FB"
    # Either import the exact selected file from OUTPUT_DIR, or import reviewed
    # source text supplied by the current editor. Existing callers remain supported.
    source_file: str | None = Field(default=None, max_length=260)
    scl_code: str | None = Field(default=None, max_length=100000)
    project_path: str = Field(min_length=1, max_length=1000)
    plc_name: str = Field(min_length=1, max_length=128)


# ---------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------

def validate_block_name(name: str) -> str:
    name = name.strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]{0,59}", name):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid block_name. Start with a letter or underscore; "
                "use only letters, numbers, underscores or hyphens."
            ),
        )
    return name


def validate_block_type(block_type: str) -> str:
    block_type = block_type.strip().upper()
    if block_type not in {"FB", "FC"}:
        raise HTTPException(
            status_code=422,
            detail="block_type must be 'FB' or 'FC'.",
        )
    return block_type


# ---------------------------------------------------------
# Ollama SCL generation
# ---------------------------------------------------------

SYSTEM_PROMPT = """
You are an industrial PLC programming assistant specializing in Siemens
TIA Portal V19 SCL.

Generate one DRAFT PLC block from the process requirement.

Return exactly one JSON object with these keys:
- scl_code: complete SCL source as a string
- assumptions: array of strings
- warnings: array of strings

MANDATORY BLOCK-NAME RULES:
1. Use the exact requested block name and requested block type.
2. Never rename, shorten, translate, or replace the requested block name.
3. For FB use FUNCTION_BLOCK "REQUESTED_NAME".
4. For FC use FUNCTION "REQUESTED_NAME" : VOID.
5. The opening declaration and closing block statement must match.

SCL RULES:
1. Use the exact requested block name and requested type (FB or FC).
2. Use Siemens SCL syntax compatible with TIA Portal V19.
3. Include a correct block header, VERSION where appropriate, variable sections,
   BEGIN, implementation statements, and matching END_FUNCTION_BLOCK or END_FUNCTION.
4. Use VAR_INPUT, VAR_OUTPUT, VAR_IN_OUT, VAR, and VAR_TEMP only when needed.
   Keep declarations in the declaration section before BEGIN. Put executable
   statements only after BEGIN.
5. For an FB, use VAR for retained instance state where appropriate. Do not confuse
   VAR declarations with executable logic.
6. Declare every symbol used. Use BOOL for Boolean signals and suitable types for
   numeric/time values. Do not invent physical addresses or hardware configuration.
7. For start/stop latch logic, give Stop and specified fault/interlock conditions
   priority over Start. If Start and Stop are both true in a scan, stop wins.
8. Do not add unrequested assumptions such as inputs being mutually exclusive.
   If an important detail is ambiguous, list the assumption explicitly.
9. Do not claim code is compiled, simulated, certified, or tested.
10. Do not create PLC download commands or automatic deployment logic.
11. Safety-related logic must use the appropriate Siemens safety engineering workflow;
    ordinary generated logic is not a substitute for certified safety logic.
12. Return only JSON; no Markdown fences around JSON or SCL.
13. Do not generate METHOD or END_METHOD declarations.
14.Generate one standard FUNCTION_BLOCK with VAR_INPUT,
    VAR_OUTPUT, VAR, BEGIN, and END_FUNCTION_BLOCK as needed.
15. Put all executable logic inside the main BEGIN ... END_FUNCTION_BLOCK body.
16. Define inputs, outputs, permissives, fault conditions,
    and expected behavior explicitly from the user's requirement.
17. Do not invent hardware addresses or assume unspecified
    permissives or fault signals.
18. Stop, active faults, and missing required permissives must
    have priority over Start when specified by the requirement.
"""


def generate_scl_with_ollama(request: LogicRequest) -> LogicResponse:
    block_name = validate_block_name(request.block_name)
    block_type = validate_block_type(request.block_type)

    user_prompt = f"""
Generate one complete Siemens TIA Portal V19 SCL block.

MANDATORY:
Requested block name: "{block_name}"
Requested block type: {block_type}

The first block declaration MUST use exactly the requested name.
For FB, declare FUNCTION_BLOCK "{block_name}".
For FC, declare FUNCTION "{block_name}" : VOID.
Do not substitute another name.

Process requirement:
{request.requirement}

Return JSON containing scl_code, assumptions and warnings.
"""

    payload = {
        "model": OLLAMA_MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "options": {"temperature": 0.1},
    }

    try:
        response = httpx.post(
            f"{OLLAMA_URL}/api/chat",
            json=payload,
            timeout=300.0,
        )
        response.raise_for_status()
    except httpx.ConnectError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot connect to Ollama. Confirm Ollama is running "
                f"and {OLLAMA_MODEL} is installed."
            ),
        ) from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(
            status_code=504,
            detail="Ollama timed out. Try a shorter requirement.",
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                f"Ollama returned HTTP {exc.response.status_code}: "
                f"{exc.response.text[:1000]}"
            ),
        ) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Error communicating with Ollama: {exc}",
        ) from exc

    try:
        ollama_data = response.json()
        content = ollama_data["message"]["content"]
        generated = json.loads(content)

        scl_code = generated.get("scl_code", "")
        assumptions = generated.get("assumptions", [])
        warnings = generated.get("warnings", [])

        if not isinstance(scl_code, str):
            raise ValueError("scl_code must be a string")
        if not isinstance(assumptions, list):
            assumptions = []
        if not isinstance(warnings, list):
            warnings = []

        assumptions = [str(item) for item in assumptions]
        warnings = [str(item) for item in warnings]

    except (ValueError, TypeError, KeyError) as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Could not parse Ollama response as the expected JSON. "
                "Try generating again."
            ),
        ) from exc

    # Validate the source against the exact name and requested block type.
    validation = validate_scl(
        scl_code,
        block_name=block_name,
        block_type=block_type,
    )
    problems = validation["errors"]
    warnings.extend(validation["warnings"])

    warnings.extend([
        "AI-generated draft: review process behavior and variable declarations.",
        "Basic checks are not TIA Portal compiler or semantic validation.",
        "Compile and test in a TIA Portal test project before use.",
        "No PLC download or automatic deployment is performed.",
    ])

    req_lower = request.requirement.lower()
    if any(word in req_lower for word in ("overload", "fault", "trip", "interlock")):
        warnings.append(
            "Verify fault/interlock priority and reset behavior."
        )
    if "stop" in req_lower and "start" in req_lower:
        warnings.append(
            "Verify Stop priority when Start and Stop are true in the same PLC scan."
        )

    status = "draft" if not problems else "validation_failed"

    # Save valid source immediately; invalid source is not importable.
    if status == "draft" and scl_code.strip():
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        output_path = OUTPUT_DIR / f"{block_name}.scl"
        output_path.write_text(
            scl_code.strip() + "\n",
            encoding="utf-8-sig",
        )
        print(f"[AI PLC Agent] SCL saved: {output_path}")
    else:
        print("[AI PLC Agent] SCL validation failed:")
        for problem in problems:
            print(f" - {problem}")

    return LogicResponse(
        status=status,
        block_name=block_name,
        requirement=request.requirement,
        assumptions=assumptions,
        scl_code=scl_code.strip(),
        warnings=warnings + problems,
    )


# ---------------------------------------------------------
# Health
# ---------------------------------------------------------

@app.get("/health")
def health():
    try:
        response = httpx.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
        response.raise_for_status()
        models = [
            model.get("name", "")
            for model in response.json().get("models", [])
        ]
        available = any(
            model == OLLAMA_MODEL or model.startswith(OLLAMA_MODEL + ":")
            for model in models
        )
        worker_exists = Path(TIA_WORKER_EXE).is_file()

        return {
            "status": "ok" if available else "model_not_found",
            "service": "AI PLC Agent",
            "mode": "ollama",
            "model": OLLAMA_MODEL,
            "ollama_connected": True,
            "model_available": available,
            "tia_worker_configured": worker_exists,
            "tia_worker_path": TIA_WORKER_EXE if worker_exists else None,
            "project_selection": "dynamic",
            "plc_selection": "dynamic",
            "generated_directory": str(OUTPUT_DIR),
            "installed_models": models,
        }
    except (httpx.HTTPError, ValueError):
        return {
            "status": "ollama_unavailable",
            "service": "AI PLC Agent",
            "mode": "ollama",
            "model": OLLAMA_MODEL,
            "ollama_connected": False,
            "model_available": False,
            "tia_worker_configured": Path(TIA_WORKER_EXE).is_file(),
            "project_selection": "dynamic",
            "plc_selection": "dynamic",
            "generated_directory": str(OUTPUT_DIR),
        }


# ---------------------------------------------------------
# SCL generation / export / import
# ---------------------------------------------------------

@app.post("/api/generate", response_model=LogicResponse)
def generate_logic(request: LogicRequest):
    return generate_scl_with_ollama(request)


@app.post("/api/export")
def export_scl(request: LogicRequest):
    result = generate_scl_with_ollama(request)

    if result.status != "draft" or not result.scl_code:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Export stopped because SCL checks failed.",
                "warnings": result.warnings,
                "scl_code": result.scl_code,
            },
        )

    safe_name = validate_block_name(request.block_name)
    output_path = OUTPUT_DIR / f"{safe_name}.scl"

    return FileResponse(
        path=output_path,
        filename=f"{safe_name}.scl",
        media_type="text/plain",
    )


@app.post("/api/import")
def import_scl(request: ImportRequest):
    """Import a selected generated SCL file or reviewed editor source.

    The selected-file route reads the exact file from OUTPUT_DIR and never
    rewrites it. The editor-source route preserves the previous API behavior.
    No PLC download is performed.
    """
    block_name = validate_block_name(request.block_name)
    block_type = validate_block_type(request.block_type)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if request.source_file:
        # Accept only a simple filename directly inside generated/.
        requested_name = Path(request.source_file).name
        if requested_name != request.source_file or not requested_name.lower().endswith(".scl"):
            raise HTTPException(
                status_code=422,
                detail="source_file must be an SCL filename directly inside the generated directory.",
            )
        source_path = (OUTPUT_DIR / requested_name).resolve()
        if source_path.parent != OUTPUT_DIR.resolve() or not source_path.is_file():
            raise HTTPException(
                status_code=404,
                detail=f"Selected SCL file was not found in generated directory: {requested_name}",
            )
        filename_block_name = validate_block_name(source_path.stem)
        if filename_block_name != block_name:
            raise HTTPException(
                status_code=422,
                detail="block_name must match the selected SCL filename (without .scl).",
            )
        code = source_path.read_text(encoding="utf-8-sig").strip()
    else:
        if not request.scl_code or not request.scl_code.strip():
            raise HTTPException(
                status_code=422,
                detail="Provide source_file or non-empty scl_code.",
            )
        code = request.scl_code.strip()
        source_path = OUTPUT_DIR / f"{block_name}.scl"

    problems = validate_scl_structure(code, block_name, block_type)
    if problems:
        raise HTTPException(
            status_code=422,
            detail={
                "message": "Source did not pass basic checks; import cancelled.",
                "problems": problems,
            },
        )

    worker_path = Path(TIA_WORKER_EXE)
    if not worker_path.is_file():
        raise HTTPException(
            status_code=503,
            detail=(
                "TIA OpennessWorker executable was not found. "
                "Check TIA_WORKER_EXE and restart FastAPI."
            ),
        )

    # For older API clients that submit edited source text, persist it before
    # invoking the worker. For selected files, preserve the original file.
    if not request.source_file:
        source_path.write_text(code.rstrip() + "\n", encoding="utf-8-sig")

    command = [
        str(worker_path),
        "SCL",
        request.project_path,
        request.plc_name,
        block_name,
        str(OUTPUT_DIR),
        str(source_path),
    ]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=180,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail="TIA OpennessWorker timed out. Check TIA Portal.",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not start TIA OpennessWorker: {exc}",
        ) from exc

    output = (completed.stdout or "") + (
        "\n" + completed.stderr if completed.stderr else ""
    )

    if completed.returncode != 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "TIA import did not complete. No PLC download was performed.",
                "exit_code": completed.returncode,
                "worker_output": output[-12000:],
            },
        )

    return {
        "status": "imported",
        "block_name": block_name,
        "source_file": source_path.name,
        "target_project": request.project_path,
        "target_plc": request.plc_name,
        "worker_output": output[-12000:],
        "plc_download_performed": False,
        "note": (
            "Worker returned success. Review and compile the block in TIA Portal. "
            "No PLC download was performed."
        ),
    }


# ---------------------------------------------------------
# TIA worker helper and configuration
# ---------------------------------------------------------

class LadImportRequest(BaseModel):
    block_name: str = Field(min_length=1, max_length=60)
    xml_file: str = Field(min_length=1, max_length=260)
    project_path: str = Field(min_length=1, max_length=1000)
    plc_name: str = Field(min_length=1, max_length=128)


class TiaConfigRequest(BaseModel):
    worker_exe: str
    project_path: str
    plc_name: str


def _run_worker(args: list[str], timeout: int = 180):
    worker = Path(TIA_WORKER_EXE)
    if not worker.is_file():
        raise HTTPException(
            status_code=503,
            detail=f"TIA worker executable not found: {worker}",
        )

    try:
        process = subprocess.run(
            [str(worker), *args],
            capture_output=True,
            text=True,
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except subprocess.TimeoutExpired as exc:
        raise HTTPException(
            status_code=504,
            detail="TIA worker timed out. Check TIA Portal.",
        ) from exc
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not start TIA worker: {exc}",
        ) from exc

    output = (process.stdout or "") + (
        "\n" + process.stderr if process.stderr else ""
    )

    if process.returncode != 0:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "TIA Openness operation failed. No PLC download was performed.",
                "exit_code": process.returncode,
                "worker_output": output[-15000:],
            },
        )

    return output


@app.get("/api/tia/projects")
def discover_tia_projects():
    """Read-only discovery of projects currently open in all TIA instances."""
    output = _run_worker(["DISCOVER"], timeout=120)
    projects = []
    for line in output.splitlines():
        if not line.startswith("PROJECT\t"):
            continue
        parts = line.split("\t", 3)
        if len(parts) != 4:
            continue
        _, name, path, plc_csv = parts
        projects.append({
            "name": name,
            "path": path,
            "plcs": [value for value in plc_csv.split(",") if value],
        })
    return {
        "projects": projects,
        "count": len(projects),
        "selection_required": True,
        "message": "Select a project and PLC. No project is selected automatically.",
    }


@app.get("/api/tia/config")
def get_tia_config():
    return {
        "worker_exe": TIA_WORKER_EXE,
        "project_selection": "dynamic",
        "plc_selection": "dynamic",
        "worker_exists": Path(TIA_WORKER_EXE).is_file(),
        "generated_directory": str(OUTPUT_DIR),
        "download_enabled": False,
    }


@app.post("/api/tia/test")
def test_tia_connection():
    checks = {
        "worker_exists": Path(TIA_WORKER_EXE).is_file(),
        "generated_directory_exists": OUTPUT_DIR.is_dir(),
    }
    return {
        "checks": checks,
        "ready": all(checks.values()),
        "message": (
            "Path checks passed. Actual Openness attachment is verified "
            "during an import/export operation."
        ),
        "download_enabled": False,
    }


# ---------------------------------------------------------
# LAD import / generated files
# ---------------------------------------------------------

@app.post("/api/lad/import")
def import_lad(request: LadImportRequest):
    block_name = validate_block_name(request.block_name)

    xml_path = (OUTPUT_DIR / Path(request.xml_file).name).resolve()
    if xml_path.parent != OUTPUT_DIR.resolve() or not xml_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="LAD XML must exist directly in the generated directory.",
        )

    if xml_path.suffix.lower() != ".xml":
        raise HTTPException(
            status_code=422,
            detail="LAD import requires a .xml file.",
        )

    output = _run_worker([
        "LAD",
        request.project_path,
        request.plc_name,
        block_name,
        str(OUTPUT_DIR),
        str(xml_path),
    ])

    return {
        "status": "imported",
        "block_name": block_name,
        "target_project": request.project_path,
        "target_plc": request.plc_name,
        "worker_output": output[-15000:],
        "plc_download_performed": False,
    }


@app.get("/api/generated")
def list_generated():
    files = []
    for file_path in sorted(OUTPUT_DIR.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in {".scl", ".xml"}:
            files.append({
                "name": file_path.name,
                "type": file_path.suffix[1:].upper(),
                "size": file_path.stat().st_size,
            })
    return {"files": files}


# ---------------------------------------------------------
# Tag request endpoint
# NOTE: Requires TAGS command in the C# worker.
# ---------------------------------------------------------

class TagCreateRequest(BaseModel):
    table_name: str = Field(
        default="AI_Generated_Tags",
        min_length=1,
        max_length=60,
    )
    project_path: str = Field(min_length=1, max_length=1000)
    plc_name: str = Field(min_length=1, max_length=128)
    tags: list[dict] = Field(min_length=1)


@app.post("/api/tags/create")
def create_tags(request: TagCreateRequest):
    table_name = validate_block_name(request.table_name)
    allowed = {"Bool", "Byte", "Word", "DWord", "Int", "DInt", "Real", "Time"}
    clean = []

    for tag in request.tags:
        name = str(tag.get("name", "")).strip()
        data_type = str(tag.get("data_type", "Bool")).strip()
        address = str(tag.get("address", "")).strip()

        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,59}", name):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid tag name: {name}",
            )
        if data_type not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Unsupported data type: {data_type}",
            )

        clean.append({
            "name": name,
            "data_type": data_type,
            "address": address,
        })

    json_path = OUTPUT_DIR / "tags_to_create.json"
    json_path.write_text(
        json.dumps(clean, indent=2),
        encoding="utf-8",
    )

    output = _run_worker([
        "TAGS",
        request.project_path,
        request.plc_name,
        table_name,
        str(json_path),
    ])

    return {
        "status": "created",
        "table_name": table_name,
        "tags": clean,
        "worker_output": output,
        "plc_download_performed": False,
    }


# ---------------------------------------------------------
# Compile endpoint
# NOTE: Requires COMPILE command in the C# worker.
# ---------------------------------------------------------

class CompileRequest(BaseModel):
    project_path: str = Field(min_length=1, max_length=1000)
    plc_name: str = Field(min_length=1, max_length=128)


@app.post("/api/tia/compile")
def compile_plc(request: CompileRequest):
    output = _run_worker(
        ["COMPILE", request.project_path, request.plc_name],
        timeout=600,
    )
    return {
        "status": "compile_requested",
        "worker_output": output,
        "plc_download_performed": False,
    }


# ---------------------------------------------------------
# Fixed reference-based LAD generator
# ---------------------------------------------------------

class LadGenerateRequest(BaseModel):
    block_name: str = Field(min_length=1, max_length=60)
    input_a: str = Field(min_length=1, max_length=60)
    input_b: str = Field(min_length=1, max_length=60)
    output: str = Field(min_length=1, max_length=60)


@app.post("/api/lad/generate")
def generate_lad_template(request: LadGenerateRequest):
    block = validate_block_name(request.block_name)
    names = [
        request.input_a.strip(),
        request.input_b.strip(),
        request.output.strip(),
    ]

    for name in names:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,59}", name):
            raise HTTPException(
                status_code=422,
                detail=f"Invalid PLC tag name: {name}",
            )

    template = OUTPUT_DIR / "FB_Parallel_Reference.xml"
    if not template.is_file():
        raise HTTPException(
            status_code=500,
            detail=(
                "Known-good V19 parallel reference XML is missing "
                "from generated/."
            ),
        )

    xml = template.read_text(encoding="utf-8-sig")
    xml = xml.replace(
        "<Name>FB_Parallel_Template</Name>",
        f"<Name>{block}</Name>",
    )

    for old, new in zip(
        ("start pb", "auto start", "motor run"),
        names,
    ):
        xml = xml.replace(
            f'<Component Name="{old}"',
            f'<Component Name="{new}"',
        )

    output_path = OUTPUT_DIR / f"{block}.xml"
    if output_path.exists():
        raise HTTPException(
            status_code=409,
            detail=(
                f"Generated XML already exists: {output_path.name}. "
                "Choose another block name or move the old file."
            ),
        )

    import xml.etree.ElementTree as ET
    try:
        ET.fromstring(xml)
    except ET.ParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Generated LAD XML is malformed: {exc}",
        ) from exc

    output_path.write_text(xml, encoding="utf-8")

    return {
        "status": "generated_from_v19_reference",
        "block_name": block,
        "xml_file": output_path.name,
        "logic": "(input_a OR input_b) -> output",
        "supported_pattern": (
            "Two parallel normally-open contacts driving one coil"
        ),
        "limitations": (
            "Fixed reference-based OR rung generator; not unrestricted "
            "natural-language LAD generation. Validate in TIA Portal V19."
        ),
        "tags_required": names,
    }
