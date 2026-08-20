# Eira iSH Message Bridge

No custom iOS app. No microphone bypass. No extra hardware.

Path:

iPhone microphone -> iOS Dictation -> iSH terminal text -> SSH over Tailscale -> Eira LIVE -> `python3 main.py`

The installer creates only connection helpers:

- `eira-check` verifies the existing Pi path and confirms `main.py` exists.
- `eira-connect` opens an interactive shell already positioned in `/media/domenicleonetti/easystore/EIRA/LIVE`.

It does **not** launch Eira, start a listener, create a second runtime, or replace the normal startup command.

After connecting, start Eira exactly as before:

```sh
python3 main.py
```

When `Dom >` appears, use the normal iPhone keyboard Dictation control. iOS owns microphone access and turns speech into text; that text enters the same `read_dom_message()` terminal path as typed text.

Default connection is `root@100.107.25.56`. Set `EIRA_HOST`, `EIRA_USER`, or `EIRA_DIR` before installation to override it.

A native iOS application, if ever desired, remains a separate future project and is not required by this bridge.
