import shutil
from datetime import datetime
from pathlib import Path
from google import genai
from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    PROJECT_DIR,
)
import subprocess
import yaml
from build_parser import (
    parse_generated_files,
    save_generated_files,
)

client = genai.Client(api_key=GEMINI_API_KEY)

PROJECT_DIR = Path(PROJECT_DIR)

MEMORY_FILES = [
    "README.md",
    "CLAUDE.md",

    "memory/project_summary.md",
    "memory/current_state.md",
    "memory/roadmap.md",
    "memory/session_notes.md",

    "memory/architecture.md",
    "memory/decisions.md",

    "requirements.txt",

    "scripts/lane_detector.py",
    "configs/lane_detection.yaml",
    "tests/test_pipeline.py",
]


def build_project_context():

    context = ""

    for file in MEMORY_FILES:

        path = PROJECT_DIR / file

        if path.exists():

            context += f"\n\n===== {file} =====\n"
            context += path.read_text()

    return context


def ask_gemini(prompt):

    project_context = build_project_context()

    full_prompt = f"""
You are assisting with a software project.

Project Context:
{project_context}

User Request:
{prompt}
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=full_prompt
    )

    return response.text

def build_file(task):

    project_context = build_project_context()

    prompt = f"""
You are a senior Python engineer.

Project Context:
{project_context}

Task:
{task}

IMPORTANT:
Return ONLY the complete contents of the updated
scripts/lane_detector.py file.

Do not explain.
Do not use markdown.
Do not use ```.

Return only Python code.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    generated_dir = Path.home() / "telegram_agent" / "generated"

    generated_dir.mkdir(exist_ok=True)

    output_file = generated_dir / "lane_detector.py"

    output_file.write_text(response.text)

    return str(output_file)

def approve_build():

    verification = verify_build()

    if not verification["success"]:

        return (
            "Approval aborted.\n\n"
            + "\n".join(
                verification["messages"]
            )
        )

    messages = verification["messages"]

    return (
            "Verification successful\n\n"
            + "\n".join(messages)
    )

    project_file = (
        Path(PROJECT_DIR)
        / "scripts"
        / "lane_detector.py"
    )

    generated_file = (
        Path.home()
        / "telegram_agent"
        / "generated"
        / "scripts"
        / "lane_detector.py"
    )

    if not generated_file.exists():

        return "No generated file found."

    backup_dir = (
        Path.home()
        / "telegram_agent"
        / "backups"
    )

    backup_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_file = (
        backup_dir
        / f"lane_detector_{timestamp}.py"
    )

    shutil.copy2(
        project_file,
        backup_file
    )

    shutil.copy2(
        generated_file,
        project_file
    )

    return (
        f"Approved.\n"
        f"Backup: {backup_file}\n"
        f"Updated: {project_file}"
    )

def run_pytest():

    try:

        result = subprocess.run(
            ["pytest"],
            cwd=PROJECT_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )

        output = result.stdout + "\n" + result.stderr

        return output

    except Exception as e:

        return f"Pytest Error:\n{e}"
    
def build_project(task):

    project_context = build_project_context()

    prompt = f"""
You are a senior software engineer.

Project Context:
{project_context}

Task:
{task}

Generate ALL required file changes.

Use EXACTLY this format:

FILE: scripts/example.py
<content>

FILE: configs/example.yaml
<content>

FILE: memory/current_state.md
<content>

Also generate:

FILE: build_summary.md

The build summary must include:

- Task
- Files modified
- Summary of changes
- Risks
- Validation steps

Only output FILE sections.
"""

    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt
    )

    files = parse_generated_files(
        response.text
    )

    generated_dir = (
        Path.home()
        / "telegram_agent"
        / "generated"
    )

    saved_files = save_generated_files(
        files,
        generated_dir
    )

    summary_file = (
    generated_dir / "build_summary.md"
    )

    summary_text = ""

    if summary_file.exists():
        summary_text = summary_file.read_text()

    return {
        "files": saved_files,
        "summary": summary_text,
    }

def verify_build():
    """
    Verify generated files before approval.
    Returns:
        {
            "success": bool,
            "messages": [...]
        }
    """

    generated_root = (
        Path.home()
        / "telegram_agent"
        / "generated"
    )

    messages = []

    if not generated_root.exists():
        return {
            "success": False,
            "messages": [
                "generated directory not found"
            ]
        }

    generated_files = []

    for f in generated_root.rglob("*"):

        if not f.is_file():
            continue

        if "__pycache__" in f.parts:
            continue

        if f.suffix == ".pyc":
            continue

        generated_files.append(f)

    messages.append(
        f"Found {len(generated_files)} generated files"
    )

    # --------------------------------------------------
    # Python syntax check
    # --------------------------------------------------

    for py_file in generated_root.rglob("*.py"):

        result = subprocess.run(
            [
                "python",
                "-m",
                "py_compile",
                str(py_file),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            return {
                "success": False,
                "messages": [
                    f"Python syntax failed: {py_file}",
                    result.stderr,
                ],
            }

    messages.append(
        "Python syntax validation passed"
    )

    # --------------------------------------------------
    # YAML validation
    # --------------------------------------------------

    for yaml_file in (
        list(generated_root.rglob("*.yaml"))
        + list(generated_root.rglob("*.yml"))
    ):

        try:

            yaml.safe_load(
                yaml_file.read_text(
                    encoding="utf-8"
                )
            )

        except Exception as exc:

            return {
                "success": False,
                "messages": [
                    f"YAML validation failed: {yaml_file}",
                    str(exc),
                ],
            }

    messages.append(
        "YAML validation passed"
    )

    # --------------------------------------------------
    # pytest validation
    # --------------------------------------------------

    try:

        lane_project = (
            Path("/media/nakulrajramesh/LENOVO_USB_HDD/lane_detection")
        )

        result = subprocess.run(
            ["pytest"],
            cwd=lane_project,
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:

            return {
                "success": False,
                "messages": [
                    "pytest failed",
                    result.stdout,
                    result.stderr,
                ],
            }

        messages.append(
            "pytest validation passed"
        )

    except Exception as exc:

        return {
            "success": False,
            "messages": [
                "pytest execution failed",
                str(exc),
            ],
        }

    return {
        "success": True,
        "messages": messages,
    }
