#!/usr/bin/env python3
"""Unified project operations for Minzhishi.

Keep repeatable source and configuration in Git; keep dependencies, caches,
rendered videos, and inspection frames out of Git.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VIDEO_DIR = ROOT / "first-video"
DEFAULT_OUTPUT = VIDEO_DIR / "renders" / "minzhishi-launch-001.mp4"
FRAME_TIMES = ("00:00:02", "00:00:15", "00:00:29")


def run(args: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=str(cwd), env=env, check=True)


def npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def ensure_video_dir() -> None:
    if not VIDEO_DIR.exists():
        raise SystemExit(f"Missing video project: {VIDEO_DIR}")


def ensure_deps() -> None:
    ensure_video_dir()
    node_modules = VIDEO_DIR / "node_modules"
    if not node_modules.exists():
        run([npm_cmd(), "install"], cwd=VIDEO_DIR)


def with_media_tools() -> dict[str, str]:
    ensure_deps()
    env = os.environ.copy()

    ffmpeg_dir = VIDEO_DIR / "node_modules" / "@ffmpeg-installer"
    ffprobe_dir = VIDEO_DIR / "node_modules" / "@ffprobe-installer"

    candidates = [
        ffmpeg_dir / "win32-x64",
        ffprobe_dir / "win32-x64",
        ffmpeg_dir / "ffmpeg",
        ffprobe_dir / "ffprobe",
    ]
    paths = [str(path) for path in candidates if path.exists()]
    env["PATH"] = os.pathsep.join(paths + [env.get("PATH", "")])
    return env


def check(_: argparse.Namespace) -> None:
    ensure_deps()
    run([npm_cmd(), "run", "check"], cwd=VIDEO_DIR)


def render(args: argparse.Namespace) -> None:
    output = Path(args.output).resolve() if args.output else DEFAULT_OUTPUT
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [npm_cmd(), "run", "render", "--", "--output", str(output)],
        cwd=VIDEO_DIR,
        env=with_media_tools(),
    )


def preview(args: argparse.Namespace) -> None:
    ensure_deps()
    run([npm_cmd(), "run", "dev", "--", "--port", str(args.port)], cwd=VIDEO_DIR)


def probe(args: argparse.Namespace) -> None:
    target = Path(args.file).resolve() if args.file else DEFAULT_OUTPUT
    if not target.exists():
        raise SystemExit(f"Missing media file: {target}")

    ffprobe = shutil.which("ffprobe", path=with_media_tools()["PATH"])
    if not ffprobe:
        raise SystemExit("ffprobe not available. Run: python ops.py install")

    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_streams",
            "-of",
            "json",
            str(target),
        ],
        cwd=str(VIDEO_DIR),
        check=True,
        capture_output=True,
        text=True,
    )
    data = json.loads(completed.stdout)
    stream = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), {})
    fmt = data.get("format", {})
    print(json.dumps(
        {
            "file": str(target),
            "width": stream.get("width"),
            "height": stream.get("height"),
            "duration": fmt.get("duration"),
            "size": fmt.get("size"),
            "codec": stream.get("codec_name"),
            "fps": stream.get("avg_frame_rate"),
        },
        ensure_ascii=False,
        indent=2,
    ))


def frames(args: argparse.Namespace) -> None:
    target = Path(args.file).resolve() if args.file else DEFAULT_OUTPUT
    if not target.exists():
        raise SystemExit(f"Missing media file: {target}")

    ffmpeg = shutil.which("ffmpeg", path=with_media_tools()["PATH"])
    if not ffmpeg:
        raise SystemExit("ffmpeg not available. Run: python ops.py install")

    out_dir = VIDEO_DIR / "renders" / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stamp in FRAME_TIMES:
        label = stamp.split(":")[-1]
        run(
            [
                ffmpeg,
                "-y",
                "-ss",
                stamp,
                "-i",
                str(target),
                "-frames:v",
                "1",
                str(out_dir / f"frame-{label}s.png"),
            ],
            cwd=VIDEO_DIR,
            env=with_media_tools(),
        )


def install(_: argparse.Namespace) -> None:
    run([npm_cmd(), "install"], cwd=VIDEO_DIR)


def clean(_: argparse.Namespace) -> None:
    for path in (VIDEO_DIR / "renders", VIDEO_DIR / ".hyperframes"):
        resolved = path.resolve()
        if ROOT not in resolved.parents:
            raise SystemExit(f"Refusing to clean outside project: {resolved}")
        if resolved.exists():
            print(f"Removing {resolved}")
            shutil.rmtree(resolved)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Minzhishi project operations")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("install", help="Install external video-tool dependencies").set_defaults(func=install)
    sub.add_parser("check", help="Run HyperFrames checks").set_defaults(func=check)

    render_parser = sub.add_parser("render", help="Render the launch video")
    render_parser.add_argument("--output", help=f"Output path, default: {DEFAULT_OUTPUT}")
    render_parser.set_defaults(func=render)

    preview_parser = sub.add_parser("preview", help="Start HyperFrames preview server")
    preview_parser.add_argument("--port", type=int, default=3017)
    preview_parser.set_defaults(func=preview)

    probe_parser = sub.add_parser("probe", help="Print rendered video metadata")
    probe_parser.add_argument("--file", help=f"Media file, default: {DEFAULT_OUTPUT}")
    probe_parser.set_defaults(func=probe)

    frames_parser = sub.add_parser("frames", help="Extract key frames for visual review")
    frames_parser.add_argument("--file", help=f"Media file, default: {DEFAULT_OUTPUT}")
    frames_parser.set_defaults(func=frames)

    sub.add_parser("clean", help="Remove local render/cache outputs").set_defaults(func=clean)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
