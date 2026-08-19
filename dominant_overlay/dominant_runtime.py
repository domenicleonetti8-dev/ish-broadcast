from __future__ import annotations

import os
import queue
import sys
import threading
import time
import uuid
from pathlib import Path

from .bootstrap import build_unified_executive
from .dominant_host import DominantEiraHostBridge
from .schema import TurnInput
from .voice.conversation_intelligence import ConversationIntelligence
from .voice.loop import VoiceConversationLoop


class AutonomyPulse:
    """Bounded self-directed initiative.

    Internal reflection is allowed. Proactive speech is allowed only after an
    idle interval and only about a safe self-generated goal. It never authorizes
    external mutation or core/identity rewrite.
    """

    def __init__(self, executive, host, emit):
        self.executive = executive
        self.host = host
        self.emit = emit
        self.stop_event = threading.Event()
        self.last_human = time.monotonic()
        self.last_spoken = 0.0
        self.thread = threading.Thread(target=self._run, name="eira-autonomy", daemon=True)

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def human_turn(self):
        self.last_human = time.monotonic()

    def _run(self):
        while not self.stop_event.wait(30):
            agency = getattr(self.executive, "agency", None)
            if agency is None:
                continue
            try:
                agency.safe_cycle()
                if os.environ.get("EIRA_PROACTIVE_SPEECH", "1") not in {"1", "true", "yes", "on"}:
                    continue
                if time.monotonic() - self.last_human < 120:
                    continue
                if time.monotonic() - self.last_spoken < 600:
                    continue
                goals = list(agency.goals.open())
                safe = [g for g in goals if agency.policy.autonomous_risk_allowed(g.risk) and int(getattr(g, "priority", 0)) >= 80]
                if not safe:
                    continue
                goal = safe[0]
                prompt = (
                    "You have been idle and may choose whether to initiate a brief conversation with Dom. "
                    "Only speak if this safe self-generated goal creates genuinely useful value right now. "
                    "Otherwise answer exactly [SILENT]. Do not take any external action.\n\n"
                    f"GOAL: {goal.objective}\nRISK: {goal.risk}"
                )
                text = self.host._ollama(prompt, omni_query=goal.objective).strip()
                if not text or text.upper() == "[SILENT]":
                    continue
                self.emit(text)
                try:
                    self.host.deliver_speech(text, {"autonomous": True, "goal_id": goal.goal_id})
                except Exception:
                    pass
                self.last_spoken = time.monotonic()
            except Exception:
                continue


def _config_path(live: Path) -> Path:
    return live / "extensions" / "unified_brain_ai" / "live_config.json"


def _emit(text: str):
    print(f"\nEira: {text}\n", flush=True)


def main() -> int:
    live = Path(os.environ.get("EIRA_LIVE_ROOT") or Path(__file__).resolve().parents[2]).resolve()
    os.environ.setdefault("EIRA_LIVE_ROOT", str(live))
    host = DominantEiraHostBridge(live)
    executive = build_unified_executive(str(_config_path(live)), host=host)
    pulse = AutonomyPulse(executive, host, _emit)
    pulse.start()

    print("EIRA DOMINANT BRAIN: online", flush=True)
    print("CONTROL: unified_brain_ai -> main.py | legacy router bypassed | OmniVenom attached", flush=True)

    always_speak = os.environ.get("EIRA_ALWAYS_SPEAK", "1").lower() in {"1", "true", "yes", "on"}
    voice_device = os.environ.get("EIRA_VOICE_DEVICE", "iphone")
    voice_auto = os.environ.get("EIRA_VOICE_AUTO", "0").lower() in {"1", "true", "yes", "on"}
    voice_loop = VoiceConversationLoop(executive, executive.gateway, recognition_locale="en-US")

    try:
        while True:
            if voice_auto:
                r = voice_loop.listen_and_respond(voice_device)
                if r.ok:
                    pulse.human_turn()
                    if r.response_text:
                        _emit(r.response_text)
                    continue
                local = host.listen_local()
                if local.get("ok"):
                    text = str(local.get("transcript") or "").strip()
                else:
                    voice_auto = False
                    print("Voice input endpoint not ready; continuing in text mode. Type /voice to retry.", flush=True)
                    continue
            else:
                try:
                    text = input("You: ").strip()
                except EOFError:
                    break

            if not text:
                continue
            low = text.lower()
            if low in {"exit", "quit", "goodbye", "shutdown"}:
                break
            if low.startswith("/voice"):
                parts = text.split(maxsplit=1)
                if len(parts) == 2:
                    voice_device = parts[1].strip() or voice_device
                voice_auto = True
                continue
            if low == "/text":
                voice_auto = False
                continue
            if low == "/status":
                _emit(str({"brain": "dominant", "host": host.route_status(), "agency": getattr(executive, "agency", None) is not None}))
                continue

            pulse.human_turn()
            turn = TurnInput(
                "main_" + uuid.uuid4().hex[:12],
                text,
                options={"voice_response": bool(always_speak), "dominant_main_takeover": True},
            )
            response = executive.handle(turn)
            _emit(response.text or "I couldn't form a response for that turn.")
    except KeyboardInterrupt:
        pass
    finally:
        pulse.stop()
    print("EIRA DOMINANT BRAIN: stopped", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
