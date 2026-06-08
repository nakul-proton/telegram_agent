from pathlib import Path


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
