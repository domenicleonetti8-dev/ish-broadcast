# Eira iSH Dictation Bridge

This is intentionally **not an iOS app** and does not access or bypass the iPhone microphone.

The iPhone keeps ownership of microphone access. iOS Dictation converts speech to text in the normal keyboard. That text is entered into the existing iSH terminal and carried by SSH to Eira's normal `python3 main.py` prompt.

Runtime path:

`iPhone microphone -> iOS Dictation -> iSH terminal -> SSH -> /media/domenicleonetti/easystore/EIRA/LIVE -> python3 main.py`

The bridge does not modify Eira's outward voice, laughter, breathing, response generation, brain, memory, OmniVenom, or normal conversation code.

## Configuration

The installer creates `$HOME/.config/eira/ish-bridge.conf`. Set only the SSH target and optional port. Do not put passwords or private keys in the file.

## Commands

`eira --check` verifies that the remote LIVE directory and `main.py` are reachable and compilable.

`eira` opens an interactive TTY and runs `python3 main.py`. Once the `Dom >` prompt appears, typed text and text produced by iOS Dictation use the same stdin path.

## Verification

`sh eira-ish-bridge/tests/mock_test.sh` performs isolated mock-SSH tests. It never contacts the real Pi and never modifies Eira.
