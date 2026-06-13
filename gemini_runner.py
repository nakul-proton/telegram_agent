from pyexpat.errors import messages
import shutil
from datetime import datetime
from pathlib import Path
from google import genai
from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    PROJECT_DIR_DEFAULT,
)
import subprocess
import yaml
import json
from build_parser import (
    parse_generated_files,
    save_generated_files,
    save_build_to_history,
    get_active_project,
)

client = genai.Client(api_key=GEMINI_API_KEY)

# Keep for backward compatibility
PROJECT_DIR = Path(PROJECT_DIR_DEFAULT)

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


def build_project_context(project: dict = None):
    """
    Build project context from memory files.
    
    Args:
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    """
    
    if project is None:
        project = get_active_project()
    
    project_dir = Path(project["path"])
    context = ""

    for file in MEMORY_FILES:

        path = project_dir / file

        if path.exists():

            context += f"\n\n===== {file} =====\n"
            context += path.read_text()

    return context


def ask_gemini(prompt, project: dict = None):
    """
    Ask Gemini with project context.
    
    Args:
        prompt: User question
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    """

    project_context = build_project_context(project)

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

def build_file(task, project: dict = None):
    """
    Build a single file (lane_detector.py).
    
    Args:
        task: Build task description
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    """

    if project is None:
        project = get_active_project()

    project_context = build_project_context(project)
    project_name = project["name"]

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

    generated_dir = (
        Path.home() / "telegram_agent" / "generated" / project_name
    )

    generated_dir.mkdir(parents=True, exist_ok=True)

    output_file = generated_dir / "lane_detector.py"

    output_file.write_text(response.text)

    return str(output_file)

def approve_build(project: dict = None):
    """
    Approve and apply generated files.
    
    Args:
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    """

    if project is None:
        project = get_active_project()

    verification = verify_build(project)

    if not verification["success"]:

        return (
            "Approval aborted.\n\n"
            + "\n".join(
                verification["messages"]
            )
        )

    messages = verification["messages"]

    backup_dir, backed_up = (
        backup_existing_files(project)
    )

    applied = apply_generated_files(project)

    report = (
        "Approval successful\n\n"
    )

    report += (
        "Verification:\n"
    )

    for msg in messages:
        report += f"✓ {msg}\n"

    report += "\n"

    report += (
        f"Backup Folder:\n"
        f"{backup_dir}\n\n"
    )

    report += (
        "Applied Files:\n"
    )

    for f in applied:
        report += f"✓ {f}\n"

    return report

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
    
def build_project(task, project: dict = None, repair_context: dict = None):
    """
    Build project with Gemini.
    
    Args:
        task: Build task description
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
        repair_context: Optional dict with {parent_timestamp, validation_output, error_message}
                        for /fix_build functionality
    
    Returns:
        {
            "build_id": "2026-06-13T12-34-56Z",
            "project": project metadata,
            "files": [list of files],
            "summary": "build summary text",
            "status": "pending" or "failed",
            "error_type": error type or None,
            "validation_output": full pytest output
        }
    """

    if project is None:
        project = get_active_project()

    project_name = project["name"]
    project_context = build_project_context(project)

    # Construct prompt with optional repair context
    prompt_parts = [
        "You are a senior software engineer.",
        "",
        "Project Context:",
        project_context,
        ""
    ]
    
    if repair_context:
        prompt_parts.extend([
            "PREVIOUS BUILD FAILURE (Build to repair):",
            f"Original Task: {repair_context.get('original_task')}",
            f"Error Type: {repair_context.get('error_type')}",
            f"Error Message: {repair_context.get('error_message')}",
            "",
            "Previous generated files (these had issues):",
            repair_context.get('generated_files', ''),
            "",
            "Full Validation Output from Previous Attempt:",
            "---",
            repair_context.get('validation_output', ''),
            "---",
            "",
        ])
    
    prompt_parts.extend([
        "Task:",
        task,
        "",
        "Generate ALL required file changes.",
        "",
        "Use EXACTLY this format:",
        "",
        "FILE: scripts/example.py",
        "<content>",
        "",
        "FILE: configs/example.yaml",
        "<content>",
        "",
        "FILE: memory/current_state.md",
        "<content>",
        "",
        "Also generate:",
        "",
        "FILE: build_summary.md",
        "",
        "The build summary must include:",
        "",
        "- Task",
        "- Files modified",
        "- Summary of changes",
        "- Risks",
        "- Validation steps",
        "",
        "Only output FILE sections."
    ])
    
    prompt = "\n".join(prompt_parts)

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
        / project_name
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

    # Verify build and capture validation output
    verification = verify_build(project)
    
    status = "pending" if verification["success"] else "failed"
    error_type = verification.get("error_type")
    error_message = verification.get("error_message")
    validation_output = verification.get("validation_output", "")
    
    # Save build to history
    build_id = save_build_to_history(
        project_name=project_name,
        generated_dir=generated_dir,
        task=task,
        status=status,
        validation_output=validation_output,
        error_type=error_type,
        error_message=error_message,
        parent_timestamp=repair_context.get("parent_timestamp") if repair_context else None
    )

    return {
        "build_id": build_id,
        "project": project,
        "files": saved_files,
        "summary": summary_text,
        "status": status,
        "error_type": error_type,
        "validation_output": validation_output
    }

def verify_build(project: dict = None):
    """
    Verify generated files before approval.
    
    Args:
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    
    Returns:
        {
            "success": bool,
            "messages": [...],
            "error_type": "pytest" | "yaml" | "syntax" | None,
            "error_message": "error details",
            "validation_output": "full raw output"
        }
    """

    if project is None:
        project = get_active_project()

    project_name = project["name"]
    project_path = Path(project["path"])

    generated_root = (
        Path.home()
        / "telegram_agent"
        / "generated"
        / project_name
    )

    messages = []
    validation_output = ""

    if not generated_root.exists():
        return {
            "success": False,
            "messages": [
                "generated directory not found"
            ],
            "error_type": None,
            "error_message": None,
            "validation_output": ""
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

            err_output = result.stdout + "\n" + result.stderr
            return {
                "success": False,
                "messages": [
                    f"Python syntax failed: {py_file}",
                    result.stderr,
                ],
                "error_type": "syntax",
                "error_message": f"Syntax error in {py_file}",
                "validation_output": err_output
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

            err_output = str(exc)
            return {
                "success": False,
                "messages": [
                    f"YAML validation failed: {yaml_file}",
                    str(exc),
                ],
                "error_type": "yaml",
                "error_message": f"YAML error in {yaml_file}: {str(exc)}",
                "validation_output": err_output
            }

    messages.append(
        "YAML validation passed"
    )

    # --------------------------------------------------
    # pytest validation
    # --------------------------------------------------

    try:

        result = subprocess.run(
            ["pytest"],
            cwd=str(project_path),
            capture_output=True,
            text=True,
        )

        validation_output = result.stdout + "\n" + result.stderr

        if result.returncode != 0:

            return {
                "success": False,
                "messages": [
                    "pytest failed",
                    result.stdout,
                    result.stderr,
                ],
                "error_type": "pytest",
                "error_message": "pytest validation failed",
                "validation_output": validation_output
            }

        messages.append(
            "pytest validation passed"
        )

    except Exception as exc:

        err_output = str(exc)
        return {
            "success": False,
            "messages": [
                "pytest execution failed",
                str(exc),
            ],
            "error_type": "pytest",
            "error_message": f"pytest execution error: {str(exc)}",
            "validation_output": err_output
        }

    return {
        "success": True,
        "messages": messages,
        "error_type": None,
        "error_message": None,
        "validation_output": validation_output
    }

def get_generated_files(project: dict = None):
    """
    Get list of generated files for a project.
    
    Args:
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    
    Returns:
        list of relative paths (Path objects)
    """

    if project is None:
        project = get_active_project()

    project_name = project["name"]

    generated_root = (
        Path.home()
        / "telegram_agent"
        / "generated"
        / project_name
    )

    files = []

    if not generated_root.exists():
        return files

    for f in generated_root.rglob("*"):

        if not f.is_file():
            continue

        if "__pycache__" in f.parts:
            continue

        if f.suffix == ".pyc":
            continue

        rel_path = f.relative_to(generated_root)

        if rel_path.name == "build_summary.md":
            continue

        files.append(rel_path)

    return files

def create_backup_folder():

    backup_root = (
        Path.home()
        / "telegram_agent"
        / "backups"
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    backup_dir = (
        backup_root
        / timestamp
    )

    backup_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    return backup_dir

def backup_existing_files(project: dict = None):
    """
    Backup existing files before approval.
    
    Args:
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    
    Returns:
        (backup_dir, list of backed up files)
    """

    if project is None:
        project = get_active_project()

    project_path = Path(project["path"])
    backup_dir = create_backup_folder()

    backed_up = []

    for rel_path in get_generated_files(project):

        source_file = project_path / rel_path

        if not source_file.exists():
            continue

        backup_file = backup_dir / rel_path

        backup_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        shutil.copy2(
            source_file,
            backup_file
        )

        backed_up.append(
            str(rel_path)
        )

    return backup_dir, backed_up

def apply_generated_files(project: dict = None):
    """
    Apply generated files to project.
    
    Args:
        project: Project metadata dict {name, path, test_command}
                 If None, uses active project
    
    Returns:
        list of applied files
    """

    if project is None:
        project = get_active_project()

    project_name = project["name"]
    project_path = Path(project["path"])

    generated_root = (
        Path.home()
        / "telegram_agent"
        / "generated"
        / project_name
    )

    applied = []

    for rel_path in get_generated_files(project):

        source_file = (
            generated_root
            / rel_path
        )

        target_file = (
            project_path
            / rel_path
        )

        target_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        shutil.copy2(
            source_file,
            target_file
        )

        applied.append(
            str(rel_path)
        )

    return applied

def get_latest_backup():

    backup_root = (
        Path.home()
        / "telegram_agent"
        / "backups"
    )

    if not backup_root.exists():

        return None

    backup_dirs = [
        d
        for d in backup_root.iterdir()
        if d.is_dir()
    ]

    if not backup_dirs:

        return None

    return sorted(
        backup_dirs
    )[-1]

def rollback_latest_backup():

    latest_backup = get_latest_backup()

    if latest_backup is None:

        return {
            "success": False,
            "message": "No backups found."
        }

    restored = []

    for source_file in latest_backup.rglob("*"):

        if not source_file.is_file():
            continue

        rel_path = (
            source_file.relative_to(
                latest_backup
            )
        )

        target_file = (
            PROJECT_DIR
            / rel_path
        )

        target_file.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        shutil.copy2(
            source_file,
            target_file
        )

        restored.append(
            str(rel_path)
        )

    return {
        "success": True,
        "backup": str(latest_backup),
        "restored": restored,
    }
