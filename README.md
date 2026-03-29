# slap_cc

中文说明见 [README.zh-CN.md](README.zh-CN.md)。

`slap_cc` turns a physical slap on an Apple Silicon MacBook into a prompt sent to the currently focused chat UI.

The project reads the laptop IMU, detects short impact spikes, picks a prompt from a pool, pastes it into the frontmost app, and submits it. The original use case here is nudging Claude Code without touching the keyboard.

## How it works

1. Read accelerometer samples from the Apple Silicon IMU via `macimu`
2. Track a slow gravity baseline
3. Compute dynamic acceleration magnitude
4. Trigger when the impulse crosses a threshold and clears cooldown
5. Pick a prompt from `prompt_pool.json`
6. Paste the prompt into the focused app and press `Enter`

## Requirements

- Apple Silicon MacBook
- macOS
- Python 3.10+
- `sudo` access for IMU reading
- Accessibility permission for the app that launches the automation flow

Notes:

- The IMU access path is macOS-specific.
- The chat-submit path is frontmost-app automation. Keep Claude Code or your target chat UI focused when the detector is armed.

## Project Layout

- `slap_detector.py`: detector and action dispatcher
- `prompt_pool.json`: prompt list used for live sends
- `requirements.txt`: Python dependency list

## Setup

```bash
cd slap_cc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick Start

Sanity-check the detector without sending anything:

```bash
sudo .venv/bin/python3 slap_detector.py --dry-run --debug
```

Run a mock signal without hardware:

```bash
.venv/bin/python3 slap_detector.py --mock --dry-run
```

Run the live hardware flow against the focused app:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost
```

Run it in the background so you can switch focus back to Claude Code:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost > slap.log 2>&1 &
```

## Accessibility Permissions

If macOS blocks the send path with an error like:

```text
osascript is not allowed to send keystrokes. (1002)
```

enable Accessibility access in:

`System Settings > Privacy & Security > Accessibility`

You will typically need to allow:

- `Terminal` or `iTerm`
- `System Events`
- any helper process you use to launch the script

If the prompt appears in the chat box but does not submit until the next slap, increase the paste-to-submit delay:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --submit-delay-ms 300
```

## Usage

Basic live run:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost
```

Use a single fixed prompt every time:

```bash
sudo .venv/bin/python3 slap_detector.py \
  --action frontmost \
  --prompt "find the root cause and fix it"
```

Use a custom prompt file:

```bash
sudo .venv/bin/python3 slap_detector.py \
  --action frontmost \
  --prompts-file my_prompts.json
```

Dry-run while still showing detected prompts:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --dry-run --debug
```

Use raw typing instead of clipboard paste:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --send-mode type
```

Insert the prompt but do not submit:

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --no-enter
```

## Tuning

The defaults are intentionally sensitive:

- `--threshold-g 0.28`
- `--cooldown-ms 350`
- `--gravity-alpha 0.01`
- `--submit-delay-ms 180`

Useful adjustments:

- Lighter taps: lower `--threshold-g`
- Fewer accidental triggers: raise `--threshold-g` or `--cooldown-ms`
- Faster recovery between slaps: lower `--cooldown-ms`
- More reliable chat submit after paste: raise `--submit-delay-ms`

Example:

```bash
sudo .venv/bin/python3 slap_detector.py \
  --action frontmost \
  --threshold-g 0.20 \
  --submit-delay-ms 300 \
  --debug
```

## Prompt Pool Format

`prompt_pool.json` must be a JSON array of strings:

```json
[
  "continue working on the current task",
  "find the root cause and fix it",
  "verify the implementation instead of assuming it works"
]
```

## Troubleshooting

`No compatible AppleSPU IMU was found`

- Make sure this is an Apple Silicon MacBook with the relevant sensor path available.

`Run with sudo so Python can access the AppleSPU HID device`

- Start the hardware mode with `sudo`.

Prompt pasted but did not send

- Increase `--submit-delay-ms`.
- Confirm the target app is focused.

Nothing happens in the chat UI

- Confirm Accessibility permissions are enabled.
- Verify the app you want to control is frontmost.
- Try `--dry-run --debug` first to separate detection problems from UI automation problems.

Too many accidental triggers

- Increase `--threshold-g`
- Increase `--cooldown-ms`

## Safety Notes

- This sends input to the frontmost app. Do not arm it if another app is focused.
- Background the detector only when you know what app will receive the prompt.
- If you are testing live, start with `--dry-run`.

## Publish Checklist

Before creating a repo:

1. Review `prompt_pool.json` and remove anything you do not want public.
2. Make sure `.venv`, logs, and caches are ignored.
3. Decide whether you want to add a license.
4. Test the README commands from a fresh clone.

## License

No license file is included yet. Add one before publishing if you want others to reuse the code under explicit terms.
