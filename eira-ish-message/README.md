# Eira iSH Message Bridge

No custom iOS app. No microphone bypass. No extra hardware.

Path:

iPhone microphone -> iOS Dictation -> iSH terminal text -> SSH over Tailscale -> Eira LIVE -> `python3 main.py`

The installer creates `eira-check` and `eira` in `~/bin`. The `eira` command opens the existing Pi connection and launches Eira from `/media/domenicleonetti/easystore/EIRA/LIVE`.

Default connection is `root@100.107.25.56`. Set `EIRA_HOST`, `EIRA_USER`, or `EIRA_DIR` before installation to override it.

After connecting and seeing `Dom >`, use the normal iPhone keyboard Dictation control. iOS owns microphone access and sends the resulting text through the same terminal input path as typing.

A native iOS application, if ever desired, remains a separate future project and is not required by this bridge.
