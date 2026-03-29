#!/usr/bin/env python3
"""Detect MacBook slap/impact events from the Apple Silicon IMU."""

from __future__ import annotations

import argparse
import json
import math
import os
import pwd
import random
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_PROMPTS_PATH = Path(__file__).with_name("prompt_pool.json")


@dataclass
class ImpactDetector:
    """Track a slow gravity baseline and emit on short acceleration spikes."""

    threshold_g: float
    cooldown_s: float
    gravity_alpha: float = 0.02

    def __post_init__(self) -> None:
        self.gravity = None
        self.last_trigger = 0.0

    def measure(self, x: float, y: float, z: float) -> float:
        if self.gravity is None:
            self.gravity = [x, y, z]
            return 0.0

        gx, gy, gz = self.gravity
        alpha = self.gravity_alpha
        gx = (1.0 - alpha) * gx + alpha * x
        gy = (1.0 - alpha) * gy + alpha * y
        gz = (1.0 - alpha) * gz + alpha * z
        self.gravity = [gx, gy, gz]

        dx = x - gx
        dy = y - gy
        dz = z - gz
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def trigger(self, sample_time: float, impulse_g: float) -> float | None:
        if impulse_g < self.threshold_g:
            return None

        if sample_time - self.last_trigger < self.cooldown_s:
            return None

        self.last_trigger = sample_time
        return impulse_g


class ActionDispatcher:
    """Dispatch a prompt to either stdout or the frontmost macOS app."""

    def __init__(
        self,
        action: str,
        dry_run: bool,
        press_enter: bool,
        send_mode: str,
        submit_delay_ms: int,
    ) -> None:
        self.action = action
        self.dry_run = dry_run
        self.press_enter = press_enter
        self.send_mode = send_mode
        self.submit_delay_ms = submit_delay_ms

    def dispatch(self, prompt: str) -> None:
        if self.dry_run or self.action == "print":
            suffix = " + submit" if self.press_enter else ""
            print(f"[action] {self.action}/{self.send_mode}: {prompt!r}{suffix}")
            sys.stdout.flush()
            return

        if self.action != "frontmost":
            raise ValueError(f"Unsupported action: {self.action}")

        script_lines = self._build_script_lines(prompt)
        subprocess.run(self._osascript_command(script_lines), check=True)

    def _build_script_lines(self, prompt: str) -> list[str]:
        if self.send_mode == "type":
            script_lines = [
                'tell application "System Events"',
                f'keystroke {self._applescript_string(prompt)}',
            ]
        elif self.send_mode == "paste":
            script_lines = [
                f"set the clipboard to {self._applescript_string(prompt)}",
                'tell application "System Events"',
                'keystroke "v" using command down',
            ]
        else:
            raise ValueError(f"Unsupported send mode: {self.send_mode}")

        if self.press_enter:
            if self.send_mode == "paste" and self.submit_delay_ms > 0:
                script_lines.append("end tell")
                script_lines.append(f"delay {self.submit_delay_ms / 1000.0:.3f}")
                script_lines.append('tell application "System Events"')
            script_lines.append("key code 36")
        script_lines.append("end tell")
        return script_lines

    def _osascript_command(self, script_lines: list[str]) -> list[str]:
        if os.geteuid() == 0 and os.environ.get("SUDO_USER"):
            sudo_user = os.environ["SUDO_USER"]
            uid = pwd.getpwnam(sudo_user).pw_uid
            command = ["launchctl", "asuser", str(uid), "sudo", "-u", sudo_user, "osascript"]
        else:
            command = ["osascript"]

        for line in script_lines:
            command.extend(["-e", line])
        return command

    @staticmethod
    def _applescript_string(value: str) -> str:
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'


def load_prompts(prompts_file: Path) -> list[str]:
    data = json.loads(prompts_file.read_text())
    if not isinstance(data, list) or not data or not all(isinstance(item, str) for item in data):
        raise ValueError(f"{prompts_file} must contain a non-empty JSON string array")
    return data


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Print a terminal message when a MacBook slap/impact is detected."
    )
    parser.add_argument(
        "--threshold-g",
        type=float,
        default=0.28,
        help="Dynamic acceleration threshold in g units. Lower is more sensitive.",
    )
    parser.add_argument(
        "--cooldown-ms",
        type=int,
        default=350,
        help="Minimum delay between triggers in milliseconds.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=100,
        help="Requested IMU sample rate in Hz.",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Use synthetic IMU data instead of the real sensor.",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=10.0,
        help="Mock mode duration in seconds.",
    )
    parser.add_argument(
        "--gravity-alpha",
        type=float,
        default=0.01,
        help="Baseline adaptation speed. Lower values make short taps stand out more.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print the recent peak impulse once per second for threshold tuning.",
    )
    parser.add_argument(
        "--action",
        choices=("print", "frontmost"),
        default="frontmost",
        help="Where slap prompts should go. `frontmost` types into the focused macOS app.",
    )
    parser.add_argument(
        "--prompts-file",
        type=Path,
        default=DEFAULT_PROMPTS_PATH,
        help="JSON file containing an array of prompt strings.",
    )
    parser.add_argument(
        "--prompt",
        help="Fixed prompt to send on every slap. Overrides --prompts-file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect slaps and log the chosen action without typing into any app.",
    )
    parser.add_argument(
        "--no-enter",
        action="store_true",
        help="Type the prompt without pressing Enter afterward.",
    )
    parser.add_argument(
        "--send-mode",
        choices=("paste", "type"),
        default="paste",
        help="How to insert the prompt into the focused app. `paste` is more reliable for chat UIs.",
    )
    parser.add_argument(
        "--submit-delay-ms",
        type=int,
        default=180,
        help="Delay between inserting the prompt and pressing Enter. Helps chat UIs register pasted text.",
    )
    return parser


def print_startup(args: argparse.Namespace) -> None:
    mode = "mock" if args.mock else "hardware"
    print(
        f"mode={mode} threshold={args.threshold_g:.2f}g cooldown={args.cooldown_ms}ms "
        f"sample_rate={args.sample_rate}Hz gravity_alpha={args.gravity_alpha:.3f}"
    )
    action = f"action={args.action}"
    action += f" send_mode={args.send_mode} submit_delay_ms={args.submit_delay_ms}"
    if args.dry_run:
        action += " dry_run=true"
    if args.prompt:
        action += f" fixed_prompt={args.prompt!r}"
    else:
        action += f" prompts_file={str(args.prompts_file)!r}"
    print(action)
    if not args.mock:
        print("This needs an Apple Silicon MacBook with the SPU IMU and usually `sudo`.")
    print("Waiting for impacts. Press Ctrl-C to stop.")


def iter_mock_samples(duration: float, sample_rate: int):
    dt = 1.0 / sample_rate
    total = max(1, int(duration * sample_rate))
    for i in range(total):
        t = i * dt
        x = 0.01 * math.sin(2.0 * math.pi * 0.9 * t)
        y = 0.01 * math.cos(2.0 * math.pi * 1.1 * t)
        z = -1.0 + 0.01 * math.sin(2.0 * math.pi * 0.7 * t)

        # Inject two clear impact-like spikes so mock mode proves the detector works.
        if i in {total // 3, (2 * total) // 3}:
            x += 1.2
            y += 0.5
            z += 0.8

        yield t, x, y, z
        time.sleep(dt)


def run(args: argparse.Namespace) -> int:
    detector = ImpactDetector(
        threshold_g=args.threshold_g,
        cooldown_s=args.cooldown_ms / 1000.0,
        gravity_alpha=args.gravity_alpha,
    )
    debug_peak = 0.0
    debug_last_print = time.monotonic()
    dispatcher = ActionDispatcher(
        action=args.action,
        dry_run=args.dry_run,
        press_enter=not args.no_enter,
        send_mode=args.send_mode,
        submit_delay_ms=args.submit_delay_ms,
    )
    try:
        prompts = [args.prompt] if args.prompt else load_prompts(args.prompts_file)
    except Exception as exc:
        print(f"Failed to load prompts: {exc}", file=sys.stderr)
        return 1

    if args.mock:
        print_startup(args)
        for sample_time, x, y, z in iter_mock_samples(args.duration, args.sample_rate):
            impulse_now = detector.measure(x, y, z)
            if args.debug:
                debug_peak = max(debug_peak, impulse_now)
                now = time.monotonic()
                if now - debug_last_print >= 1.0:
                    print(f"[debug] recent_peak={debug_peak:.3f}g threshold={args.threshold_g:.3f}g")
                    debug_peak = 0.0
                    debug_last_print = now
            impulse_g = detector.trigger(sample_time, impulse_now)
            if impulse_g is None:
                continue
            stamp = time.strftime("%H:%M:%S")
            prompt = random.choice(prompts)
            print(f"[{stamp}] SLAP DETECTED impulse={impulse_g:.3f}g prompt={prompt!r}")
            dispatcher.dispatch(prompt)
            sys.stdout.flush()
        return 0

    try:
        from macimu import IMU
    except ImportError:
        print(
            "macimu is not installed. Create the venv and run `pip install -r requirements.txt`.",
            file=sys.stderr,
        )
        return 1

    if sys.platform != "darwin":
        print("This script only works on macOS.", file=sys.stderr)
        return 1
    if os.geteuid() != 0:
        print("Run with sudo so Python can access the AppleSPU HID device.", file=sys.stderr)
        return 1
    if not IMU.available():
        print("No compatible AppleSPU IMU was found on this machine.", file=sys.stderr)
        return 1

    imu = IMU(sample_rate=args.sample_rate)
    print_startup(args)

    with imu:
        for sample in imu.stream_accel_timed():
            impulse_now = detector.measure(sample.x, sample.y, sample.z)
            if args.debug:
                debug_peak = max(debug_peak, impulse_now)
                now = time.monotonic()
                if now - debug_last_print >= 1.0:
                    print(f"[debug] recent_peak={debug_peak:.3f}g threshold={args.threshold_g:.3f}g")
                    debug_peak = 0.0
                    debug_last_print = now
                    sys.stdout.flush()
            impulse_g = detector.trigger(sample.t, impulse_now)
            if impulse_g is None:
                continue
            stamp = time.strftime("%H:%M:%S")
            prompt = random.choice(prompts)
            print(f"[{stamp}] SLAP DETECTED impulse={impulse_g:.3f}g prompt={prompt!r}")
            try:
                dispatcher.dispatch(prompt)
            except subprocess.CalledProcessError as exc:
                print(f"[action-error] osascript failed with exit code {exc.returncode}", file=sys.stderr)
            except Exception as exc:
                print(f"[action-error] {exc}", file=sys.stderr)
            sys.stdout.flush()

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(build_parser().parse_args()))
    except KeyboardInterrupt:
        print("\nStopped.")
        raise SystemExit(0)
