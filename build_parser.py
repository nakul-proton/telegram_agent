from pathlib import Path
from datetime import datetime
import json
import shutil
from config import DEFAULT_PROJECT_METADATA


def parse_generated_files(response_text: str) -> dict[str, str]:
    """
    Parse Gemini multi-file output.

    Expected format:

    FILE: scripts/lane_detector.py
    <content>

    FILE: configs/lane_detection.yaml
    <content>
    """

    files = {}

    current_file = None
    current_lines = []

    for line in response_text.splitlines():

        if line.startswith("FILE:"):

            if current_file:

                files[current_file] = "\n".join(
                    current_lines
                ).rstrip() + "\n"

            current_file = (
                line.replace("FILE:", "", 1)
                .strip()
            )

            current_lines = []

        else:

            current_lines.append(line)

    if current_file:

        files[current_file] = "\n".join(
            current_lines
        ).rstrip() + "\n"

    return files


def save_generated_files(
    files: dict[str, str],
    generated_root: Path
) -> list[str]:

    saved = []

    generated_root.mkdir(
        parents=True,
        exist_ok=True
    )

    for relative_path, content in files.items():

        target = generated_root / relative_path

        target.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        target.write_text(
            content,
            encoding="utf-8"
        )

        saved.append(relative_path)

    return saved


# ============================================================
# PROJECT MANAGEMENT
# ============================================================

def _get_projects_file() -> Path:
    """Return path to projects.json"""
    return Path.home() / "telegram_agent" / "projects.json"


def _init_projects_file():
    """Initialize projects.json with default project"""
    projects_file = _get_projects_file()
    
    data = {
        "active_project": "lane_detection",
        "projects": {
            "lane_detection": DEFAULT_PROJECT_METADATA.copy()
        }
    }
    
    projects_file.write_text(json.dumps(data, indent=2))
    return data


def get_active_project() -> dict:
    """
    Get active project metadata.
    
    Returns {name, path, test_command}
    """
    projects_file = _get_projects_file()
    
    if not projects_file.exists():
        _init_projects_file()
    
    data = json.loads(projects_file.read_text())
    active_name = data.get("active_project", "lane_detection")
    
    if active_name not in data["projects"]:
        active_name = "lane_detection"
    
    return data["projects"][active_name]


def select_project(project_name: str) -> bool:
    """
    Switch active project.
    
    Returns True if success, False if project not found.
    """
    projects_file = _get_projects_file()
    
    if not projects_file.exists():
        _init_projects_file()
    
    data = json.loads(projects_file.read_text())
    
    if project_name not in data["projects"]:
        return False
    
    data["active_project"] = project_name
    projects_file.write_text(json.dumps(data, indent=2))
    return True


def add_project(name: str, path: str, test_command: str = "pytest") -> None:
    """Register new project"""
    projects_file = _get_projects_file()
    
    if not projects_file.exists():
        _init_projects_file()
    
    data = json.loads(projects_file.read_text())
    
    data["projects"][name] = {
        "name": name,
        "path": path,
        "test_command": test_command
    }
    
    projects_file.write_text(json.dumps(data, indent=2))


def list_projects() -> list[str]:
    """Return list of all registered project names"""
    projects_file = _get_projects_file()
    
    if not projects_file.exists():
        _init_projects_file()
    
    data = json.loads(projects_file.read_text())
    return list(data["projects"].keys())


def save_build_to_history(
    project_name: str,
    generated_dir: Path,
    task: str,
    status: str,
    validation_output: str,
    error_type: str = None,
    error_message: str = None,
    parent_timestamp: str = None
) -> str:
    """
    Save build snapshot to history.
    
    Returns timestamp (build_id) like "2026-06-13T12-34-56Z"
    """
    
    timestamp = datetime.now().strftime("%Y-%m-%dT%H-%M-%SZ")
    
    build_dir = (
        Path.home()
        / "telegram_agent"
        / "build_history"
        / project_name
        / timestamp
    )
    build_dir.mkdir(parents=True, exist_ok=True)
    
    # Save metadata
    metadata = {
        "task": task,
        "status": status,
        "error_type": error_type,
        "error_message": error_message,
        "parent_timestamp": parent_timestamp,
        "timestamp": timestamp
    }
    (build_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))
    
    # Save validation output (raw, full)
    (build_dir / "validation.txt").write_text(validation_output)
    
    # Copy generated files snapshot
    generated_snapshot = build_dir / "generated"
    if generated_dir.exists():
        shutil.copytree(
            generated_dir,
            generated_snapshot,
            dirs_exist_ok=True
        )
    
    return timestamp


def load_build_from_history(project_name: str, timestamp: str) -> dict:
    """
    Load build from history by timestamp.
    
    Returns {
        "metadata": {...},
        "validation_output": "...",
        "generated_dir": Path
    } or None if not found
    """
    
    build_dir = (
        Path.home()
        / "telegram_agent"
        / "build_history"
        / project_name
        / timestamp
    )
    
    if not build_dir.exists():
        return None
    
    metadata_file = build_dir / "metadata.json"
    validation_file = build_dir / "validation.txt"
    
    metadata = {}
    if metadata_file.exists():
        metadata = json.loads(metadata_file.read_text())
    
    validation_output = ""
    if validation_file.exists():
        validation_output = validation_file.read_text()
    
    return {
        "metadata": metadata,
        "validation_output": validation_output,
        "generated_dir": build_dir / "generated"
    }


def get_latest_failed_build(project_name: str) -> dict:
    """
    Get the most recent failed build for a project.
    
    Returns {
        "timestamp": "2026-06-13T21-55-52Z",
        "metadata": {...},
        "validation_output": "...",
        "generated_dir": Path
    } or None if no failed build found
    """
    
    history_root = (
        Path.home()
        / "telegram_agent"
        / "build_history"
        / project_name
    )
    
    if not history_root.exists():
        return None
    
    # Get all build directories
    build_dirs = [
        d for d in history_root.iterdir()
        if d.is_dir()
    ]
    
    if not build_dirs:
        return None
    
    # Sort by timestamp descending (most recent first)
    build_dirs.sort(reverse=True)
    
    # Find the first failed build
    for build_dir in build_dirs:
        metadata_file = build_dir / "metadata.json"
        
        if not metadata_file.exists():
            continue
        
        metadata = json.loads(metadata_file.read_text())
        
        if metadata.get("status") == "failed":
            timestamp = build_dir.name
            build = load_build_from_history(project_name, timestamp)
            
            if build:
                build["timestamp"] = timestamp
                return build
    
    return None


def read_generated_files_as_text(generated_dir: Path) -> str:
    """
    Read all generated files and format as text for context.
    
    Returns formatted string like:
    FILE: scripts/lane_detector.py
    <content>
    
    FILE: configs/lane_detection.yaml
    <content>
    """
    
    if not generated_dir.exists():
        return ""
    
    output = []
    
    for f in sorted(generated_dir.rglob("*")):
        if not f.is_file():
            continue
        
        if "__pycache__" in f.parts or f.suffix == ".pyc":
            continue
        
        rel_path = f.relative_to(generated_dir)
        
        try:
            content = f.read_text(encoding="utf-8")
            output.append(f"FILE: {rel_path}\n{content}")
        except Exception:
            output.append(f"FILE: {rel_path}\n[Binary or unreadable]\n")
    
    return "\n\n".join(output)

