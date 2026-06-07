#!/usr/bin/env python3
"""Lane detection pipeline.

Reads a video from ``input/``, detects lane markings using a classic
computer-vision pipeline (color/gradient masking -> region of interest ->
Hough line transform), and writes an annotated video to ``output/videos/``.

All tunable parameters live in ``configs/lane_detection.yaml`` and are loaded
once at import time into ``CONFIG``.

Usage:
    python scripts/lane_detector.py                 # process first video in input/
    python scripts/lane_detector.py clip.mp4        # process input/clip.mp4
    python scripts/lane_detector.py /path/to/v.mp4  # process an explicit path
"""

from __future__ import annotations

import sys
import logging
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
INPUT_DIR = PROJECT_ROOT / "input"
OUTPUT_VIDEO_DIR = PROJECT_ROOT / "output" / "videos"
OUTPUT_LOGS_DIR = PROJECT_ROOT / "output" / "logs"
CONFIG_PATH = PROJECT_ROOT / "configs" / "lane_detection.yaml"


def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load the pipeline configuration from a YAML file."""
    with open(path, "r") as fh:
        return yaml.safe_load(fh)


CONFIG = load_config()

logger = logging.getLogger(__name__)


def setup_logging():
    if logger.hasHandlers():
        return

    OUTPUT_LOGS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = OUTPUT_LOGS_DIR / f"lane_detection_{timestamp}.log"

    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_file)
    console_handler = logging.StreamHandler(sys.stdout)

    formatter = logging.Formatter(
        "%(asctime)s - %(levelname)s - %(message)s"
    )

    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    logger.info(f"Logging initialized: {log_file}")


VIDEO_EXTENSIONS = tuple(CONFIG["video"]["extensions"])


def make_lane_mask(frame: np.ndarray, cfg: dict | None = None) -> np.ndarray:
    m = (cfg or CONFIG)["mask"]
    hls = cv2.cvtColor(frame, cv2.COLOR_BGR2HLS)

    white = cv2.inRange(hls, tuple(m["white_lower"]), tuple(m["white_upper"]))
    yellow = cv2.inRange(hls, tuple(m["yellow_lower"]), tuple(m["yellow_upper"]))
    color_mask = cv2.bitwise_or(white, yellow)

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, tuple(m["gaussian_kernel"]), 0)
    edges = cv2.Canny(blur, m["canny_low"], m["canny_high"])

    return cv2.bitwise_or(color_mask, edges)


def region_of_interest(mask: np.ndarray, cfg: dict | None = None) -> np.ndarray:
    r = (cfg or CONFIG)["roi"]
    height, width = mask.shape[:2]
    polygon = np.array(
        [[
            (int(r["bottom_left_x_ratio"] * width), height),
            (int(r["apex_left_x_ratio"] * width), int(r["apex_y_ratio"] * height)),
            (int(r["apex_right_x_ratio"] * width), int(r["apex_y_ratio"] * height)),
            (int(r["bottom_right_x_ratio"] * width), height),
        ]],
        dtype=np.int32,
    )
    roi = np.zeros_like(mask)
    cv2.fillPoly(roi, polygon, r["fill_value"])
    return cv2.bitwise_and(mask, roi)


def _average_line(lines, height: int, y_top: int):
    if not lines:
        return None
    xs, ys = [], []
    for x1, y1, x2, y2 in lines:
        xs += [x1, x2]
        ys += [y1, y2]
    slope, intercept = np.polyfit(ys, xs, 1)
    y_bottom = height
    x_bottom = int(slope * y_bottom + intercept)
    x_top = int(slope * y_top + intercept)
    return (x_bottom, y_bottom, x_top, y_top)


def detect_lane_lines(roi_mask: np.ndarray, cfg: dict | None = None):
    cfg = cfg or CONFIG
    h_cfg = cfg["hough"]
    l_cfg = cfg["lanes"]
    height = roi_mask.shape[0]
    y_top = int(l_cfg["y_top_ratio"] * height)

    segments = cv2.HoughLinesP(
        roi_mask,
        rho=h_cfg["rho"],
        theta=h_cfg["theta_deg"] * np.pi / 180,
        threshold=h_cfg["threshold"],
        minLineLength=h_cfg["min_line_length"],
        maxLineGap=h_cfg["max_line_gap"],
    )
    if segments is None:
        return []

    min_abs_slope = l_cfg["min_abs_slope"]
    left, right = [], []
    for seg in segments:
        x1, y1, x2, y2 = seg[0]
        if x2 == x1:
            continue
        slope = (y2 - y1) / (x2 - x1)
        if abs(slope) < min_abs_slope:
            continue
        (left if slope < 0 else right).append((x1, y1, x2, y2))

    lanes = []
    for group in (left, right):
        line = _average_line(group, height, y_top)
        if line is not None:
            lanes.append(line)
    return lanes


def annotate(frame: np.ndarray, lanes, cfg: dict | None = None) -> np.ndarray:
    a = (cfg or CONFIG)["annotate"]
    overlay = np.zeros_like(frame)

    if len(lanes) == 2:
        (lbx, lby, ltx, lty), (rbx, rby, rtx, rty) = lanes
        area = np.array([[(lbx, lby), (ltx, lty), (rtx, rty), (rbx, rby)]], dtype=np.int32)
        cv2.fillPoly(overlay, area, tuple(a["fill_color"]))

    for x1, y1, x2, y2 in lanes:
        cv2.line(overlay, (x1, y1), (x2, y2), tuple(a["line_color"]), a["line_thickness"])

    return cv2.addWeighted(
        frame, a["frame_weight"], overlay, a["overlay_weight"], a["gamma"]
    )


def find_input_video(arg: str | None) -> Path:
    if arg:
        candidate = Path(arg)
        if not candidate.is_absolute():
            candidate = candidate if candidate.exists() else INPUT_DIR / arg
        if not candidate.exists():
            raise FileNotFoundError(f"Video not found: {arg}")
        return candidate

    videos = sorted(
        p for p in INPUT_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in VIDEO_EXTENSIONS
    )
    if not videos:
        raise FileNotFoundError(
            f"No video files found in {INPUT_DIR}. "
            f"Add one of: {', '.join(VIDEO_EXTENSIONS)}"
        )
    return videos[0]


def process_video(src: Path) -> Path:
    v = CONFIG["video"]
    cap = cv2.VideoCapture(str(src))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {src}")

    fps = cap.get(cv2.CAP_PROP_FPS) or v["default_fps"]
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0

    OUTPUT_VIDEO_DIR.mkdir(parents=True, exist_ok=True)
    dst = OUTPUT_VIDEO_DIR / f"{src.stem}{v['output_suffix']}.mp4"

    fourcc = cv2.VideoWriter_fourcc(*v["fourcc"])
    writer = cv2.VideoWriter(str(dst), fourcc, fps, (width, height))
    if not writer.isOpened():
        cap.release()
        raise RuntimeError(f"Could not open video writer for: {dst}")

    logger.info(
        f"Processing {src.name} ({width}x{height} @ {fps:.1f} fps, {total or '?'} frames)"
    )

    progress_interval = v["progress_interval"]
    frame_idx = 0
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            mask = make_lane_mask(frame)
            roi = region_of_interest(mask)
            lanes = detect_lane_lines(roi)
            writer.write(annotate(frame, lanes))

            frame_idx += 1
            if total and frame_idx % progress_interval == 0:
                pct = 100.0 * frame_idx / total
                logger.info(f"{frame_idx}/{total} frames ({pct:5.1f}%)")
    finally:
        cap.release()
        writer.release()

    logger.info(f"Done. Wrote {frame_idx} frames to {dst}")
    return dst


def main(argv: list[str]) -> int:
    setup_logging()

    arg = argv[1] if len(argv) > 1 else None

    try:
        src = find_input_video(arg)
        process_video(src)
    except (FileNotFoundError, RuntimeError) as exc:
        logger.error(str(exc))
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
