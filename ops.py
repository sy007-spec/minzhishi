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
VIDEO_PROJECTS = {
    "first-video": {
        "dir": ROOT / "first-video",
        "output": "minzhishi-launch-001.mp4",
        "frames": ("00:00:02", "00:00:15", "00:00:29"),
    },
    "support-video-001-youxx": {
        "dir": ROOT / "support-video-001-youxx",
        "output": "mzs-2026-001-youxx-public.mp4",
        "frames": ("00:00:03", "00:00:11", "00:00:20", "00:00:29", "00:00:37", "00:00:46", "00:00:56"),
    },
}
DEFAULT_PROJECT = "first-video"
VIDEO_DIR = VIDEO_PROJECTS[DEFAULT_PROJECT]["dir"]
DEFAULT_OUTPUT = VIDEO_DIR / "renders" / VIDEO_PROJECTS[DEFAULT_PROJECT]["output"]
FRAME_TIMES = ("00:00:02", "00:00:15", "00:00:29")


def run(args: list[str], cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args))
    subprocess.run(args, cwd=str(cwd), env=env, check=True)


def npm_cmd() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def project_dir(args: argparse.Namespace) -> Path:
    name = getattr(args, "project", DEFAULT_PROJECT)
    if name not in VIDEO_PROJECTS:
        choices = ", ".join(sorted(VIDEO_PROJECTS))
        raise SystemExit(f"Unknown video project: {name}. Choices: {choices}")
    return VIDEO_PROJECTS[name]["dir"]


def default_output(args: argparse.Namespace) -> Path:
    name = getattr(args, "project", DEFAULT_PROJECT)
    project = VIDEO_PROJECTS[name]
    return project["dir"] / "renders" / project["output"]


def frame_times(args: argparse.Namespace) -> tuple[str, ...]:
    name = getattr(args, "project", DEFAULT_PROJECT)
    return VIDEO_PROJECTS[name]["frames"]


def ensure_video_dir(video_dir: Path) -> None:
    if not video_dir.exists():
        raise SystemExit(f"Missing video project: {video_dir}")


def ensure_deps(video_dir: Path) -> None:
    ensure_video_dir(video_dir)
    node_modules = video_dir / "node_modules"
    if not node_modules.exists():
        run([npm_cmd(), "install"], cwd=video_dir)


def with_media_tools(video_dir: Path) -> dict[str, str]:
    ensure_deps(video_dir)
    env = os.environ.copy()

    ffmpeg_dir = video_dir / "node_modules" / "@ffmpeg-installer"
    ffprobe_dir = video_dir / "node_modules" / "@ffprobe-installer"

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
    video_dir = project_dir(_)
    ensure_deps(video_dir)
    run([npm_cmd(), "run", "check"], cwd=video_dir)


def render(args: argparse.Namespace) -> None:
    video_dir = project_dir(args)
    output = Path(args.output).resolve() if args.output else default_output(args)
    output.parent.mkdir(parents=True, exist_ok=True)
    run(
        [npm_cmd(), "run", "render", "--", "--quality", args.quality, "--output", str(output)],
        cwd=video_dir,
        env=with_media_tools(video_dir),
    )


def preview(args: argparse.Namespace) -> None:
    video_dir = project_dir(args)
    ensure_deps(video_dir)
    run([npm_cmd(), "run", "dev", "--", "--port", str(args.port)], cwd=video_dir)


def probe(args: argparse.Namespace) -> None:
    video_dir = project_dir(args)
    target = Path(args.file).resolve() if args.file else default_output(args)
    if not target.exists():
        raise SystemExit(f"Missing media file: {target}")

    ffprobe = shutil.which("ffprobe", path=with_media_tools(video_dir)["PATH"])
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
        cwd=str(video_dir),
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
    video_dir = project_dir(args)
    target = Path(args.file).resolve() if args.file else default_output(args)
    if not target.exists():
        raise SystemExit(f"Missing media file: {target}")

    ffmpeg = shutil.which("ffmpeg", path=with_media_tools(video_dir)["PATH"])
    if not ffmpeg:
        raise SystemExit("ffmpeg not available. Run: python ops.py install")

    out_dir = video_dir / "renders" / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stamp in frame_times(args):
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
            cwd=video_dir,
            env=with_media_tools(video_dir),
        )


def install(args: argparse.Namespace) -> None:
    run([npm_cmd(), "install"], cwd=project_dir(args))


def clean(args: argparse.Namespace) -> None:
    video_dir = project_dir(args)
    for path in (video_dir / "renders", video_dir / ".hyperframes"):
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

    def add_project_arg(command: argparse.ArgumentParser) -> None:
        command.add_argument(
            "--project",
            choices=sorted(VIDEO_PROJECTS),
            default=DEFAULT_PROJECT,
            help=f"Video project, default: {DEFAULT_PROJECT}",
        )

    install_parser = sub.add_parser("install", help="Install external video-tool dependencies")
    add_project_arg(install_parser)
    install_parser.set_defaults(func=install)

    check_parser = sub.add_parser("check", help="Run HyperFrames checks")
    add_project_arg(check_parser)
    check_parser.set_defaults(func=check)

    render_parser = sub.add_parser("render", help="Render the launch video")
    add_project_arg(render_parser)
    render_parser.add_argument("--quality", choices=("draft", "standard", "high"), default="high")
    render_parser.add_argument("--output", help="Output path, default: project render path")
    render_parser.set_defaults(func=render)

    preview_parser = sub.add_parser("preview", help="Start HyperFrames preview server")
    add_project_arg(preview_parser)
    preview_parser.add_argument("--port", type=int, default=3017)
    preview_parser.set_defaults(func=preview)

    probe_parser = sub.add_parser("probe", help="Print rendered video metadata")
    add_project_arg(probe_parser)
    probe_parser.add_argument("--file", help="Media file, default: project render path")
    probe_parser.set_defaults(func=probe)

    frames_parser = sub.add_parser("frames", help="Extract key frames for visual review")
    add_project_arg(frames_parser)
    frames_parser.add_argument("--file", help="Media file, default: project render path")
    frames_parser.set_defaults(func=frames)

    clean_parser = sub.add_parser("clean", help="Remove local render/cache outputs")
    add_project_arg(clean_parser)
    clean_parser.set_defaults(func=clean)

    args = parser.parse_args()
    args.func(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
