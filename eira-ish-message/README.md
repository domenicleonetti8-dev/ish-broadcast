# Eira iSH Message Bridge

App-free iPhone voice-to-message path for Eira.

## Architecture

iPhone microphone -> iOS Dictation -> iSH terminal text -> SSH/Tailscale -> `/media/domenicleonetti/easystore/EIRA/LIVE` -> `python3 main.py`

The bridge does not capture raw iPhone microphone audio, bypass iOS microphone permissions, or modify Eira's outward voice. iOS remains responsible for microphone access and dictation. Eira receives the resulting text through her existing terminal input path.

## Install in iSH

Run the raw `install.sh` from this directory. The installer creates:

- `~/bin/eira-check` to verify the existing Tailscale/SSH path.
- `~/bin/eira` to connect directly to the Pi, enter Eira's LIVE directory, and run `python3 main.py` interactively.

Defaults:

- host: `100.107.25.56`
- user: `root`
- LIVE directory: `/media/domenicleonetti/easystore/EIRA/LIVE`

All defaults can be overridden before installation with `EIRA_HOST`, `EIRA_USER`, or `EIRA_DIR`.

## Use

Run `eira`, wait for the normal `Dom >` prompt, then use the iPhone keyboard's Dictation control. Dictated text arrives through the same `read_dom_message()` path as typed text.

A future native iOS application can be developed separately without changing this bridge.
