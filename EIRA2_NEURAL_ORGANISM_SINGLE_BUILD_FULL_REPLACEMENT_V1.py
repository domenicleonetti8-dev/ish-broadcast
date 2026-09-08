TARGET = "eira2/neural/organism.py"
NEW = r'''from __future__ import annotations

import threading
from collections import deque
from pathlib import Path
from typing import Any

from ..contracts import Event, RuntimeContext, ServiceSpec
from ..kernel.events import EventService
from ..registry.graph import NodeRegistryService
from . import live as live_module
from .atlas import NeuralAtlas, stable_neuron_id
from .communication import CommunicationLiveNeuralHTTPService, PCMSubmitter, TextSubmitter
from .growth import overlay_live_filesystem
from .live import AtomicAtlasProxy, LiveNeuralSurface
from .sync import NeuralTopologySynchronizer


class RegistryAwareNeuralSurface(LiveNeuralSurface):
    """Live atlas that overlays canonical runtime nodes and proven bridges."""

    def __init__(
        self,
        root: Path,
        *,
        inventory: Path | None = None,
        trace: bool = True,
        sync_interval_seconds: float = 2.0,
    ) -> None:
        root = root.expanduser().resolve()

        # Build the canonical atlas exactly once. NeuralAtlas already resolves its
        # preferred inventory when inventory=None, so rebuilding solely to reuse
        # the detected inventory duplicates the same topology work.
        initial = NeuralAtlas(root, inventory=inventory).build()
        detected_inventory: Path | None = None
        if inventory is not None:
            detected_inventory = inventory.expanduser().resolve()
        elif initial.inventory_source and initial.inventory_source != "filesystem_scan_fallback":
            candidate = Path(initial.inventory_source)
            if candidate.is_file():
                detected_inventory = candidate.resolve()

        overlay_live_filesystem(initial, root)
        self.root = root
        self._inventory = detected_inventory
        self._runtime_nodes: dict[str, dict[str, str]] = {}
        self._refresh_lock = threading.RLock()
        self._revisions: deque[dict[str, Any]] = deque(maxlen=128)
        self.atlas = AtomicAtlasProxy(initial)

        from .activity import NeuralActivity

        self.activity = NeuralActivity(root, atlas=self.atlas)
        self.trace = bool(trace)
        self.invention_usdz_root = self.root / "var" / "inventions" / "usdz"
        self.apple_ar_brain = self.invention_usdz_root / "eira2_brain.usdz"
        self.sync = NeuralTopologySynchronizer(
            root,
            inventory=self._inventory,
            on_change=self.refresh_topology,
            interval_seconds=sync_interval_seconds,
        )
        self._runtime_bridges: dict[tuple[str, str, str], dict[str, Any]] = {}

    def _inject_runtime_nodes(self, atlas: NeuralAtlas) -> None:
        super()._inject_runtime_nodes(atlas)
        for row in self._runtime_bridges.values():
            source_id = stable_neuron_id(f"@runtime/{row['source']}")
            target_id = stable_neuron_id(f"@runtime/{row['target']}")
            if source_id not in atlas.neurons or target_id not in atlas.neurons:
                continue
            atlas._add_fiber(
                source_id,
                target_id,
                str(row.get("kind") or "runtime_call"),
                bool(row.get("conductive", True)),
                str(row.get("evidence") or "runtime_registry_bridge"),
            )

    def seed_registry(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        for node in snapshot.get("nodes", []):
            if not isinstance(node, dict):
                continue
            name = str(node.get("name") or "").strip()
            if not name:
                continue
            self._runtime_nodes[name] = {
                "kind": str(node.get("kind") or "service")[:80],
                "cluster": f"eira2:{name.split('.', 1)[0]}",
            }
        for bridge in snapshot.get("bridges", []):
            if not isinstance(bridge, dict):
                continue
            source = str(bridge.get("source") or "").strip()
            target = str(bridge.get("target") or "").strip()
            kind = str(bridge.get("kind") or "runtime_call")[:80]
            if not source or not target:
                continue
            self._runtime_bridges[(source, target, kind)] = {
                "source": source,
                "target": target,
                "kind": kind,
                "conductive": bool(bridge.get("conductive", True)),
                "evidence": str(bridge.get("evidence") or "registry_snapshot")[:160],
            }
        return self.refresh_topology("registry_seed")

    def register_runtime_bridge(
        self,
        source: str,
        target: str,
        *,
        kind: str = "runtime_call",
        conductive: bool = True,
        evidence: str = "registry_event",
    ) -> dict[str, Any]:
        source = str(source or "").strip()
        target = str(target or "").strip()
        kind = str(kind or "runtime_call")[:80]
        if not source or not target:
            return {"changed": False, "error": "runtime_bridge_identity_required"}
        self._runtime_bridges[(source, target, kind)] = {
            "source": source,
            "target": target,
            "kind": kind,
            "conductive": bool(conductive),
            "evidence": str(evidence or "registry_event")[:160],
        }
        return self.refresh_topology(f"runtime_bridge_registered:{source}:{target}:{kind}")


class OrganismNeuralHTTPService(CommunicationLiveNeuralHTTPService):
    """Canonical iPhone communication plus the live EIRA2 neural organism."""

    spec = ServiceSpec(
        "interfaces.neural_ui",
        required=False,
        dependencies=(
            "kernel.events",
            "registry.graph",
            "interfaces.ingress",
            "interfaces.native",
            "delivery.reactive_presence",
            "conversation.spine",
            "delivery.gate",
        ),
        start_timeout_seconds=60.0,
        stop_timeout_seconds=10.0,
    )

    def __init__(
        self,
        root: Path,
        *,
        text_submitter: TextSubmitter | None = None,
        pcm_submitter: PCMSubmitter | None = None,
        host: str = "127.0.0.1",
        port: int = 8782,
        inventory: Path | None = None,
        trace: bool = True,
        sync_interval_seconds: float = 2.0,
    ) -> None:
        # LiveNeuralHTTPService resolves LiveNeuralSurface from eira2.neural.live
        # at call time. Swap that constructor only for this synchronous startup
        # call so the communication layer and organism share one surface.
        original_surface = live_module.LiveNeuralSurface

        class _ConfiguredRegistrySurface(RegistryAwareNeuralSurface):
            def __init__(self, surface_root: Path, *, inventory=None, trace=True, **_: Any) -> None:
                super().__init__(
                    surface_root,
                    inventory=inventory,
                    trace=trace,
                    sync_interval_seconds=sync_interval_seconds,
                )

        live_module.LiveNeuralSurface = _ConfiguredRegistrySurface
        try:
            super().__init__(
                root,
                host=host,
                port=port,
                inventory=inventory,
                trace=trace,
                text_submitter=text_submitter,
                pcm_submitter=pcm_submitter,
            )
        finally:
            live_module.LiveNeuralSurface = original_surface

        if not isinstance(self.surface, RegistryAwareNeuralSurface):
            raise RuntimeError("registry_aware_surface_construction_failed")
        self._bridge_subscription_installed = False

    async def _bridge_event(self, event: Event) -> None:
        payload = dict(event.payload or {})
        self.surface.register_runtime_bridge(
            str(payload.get("source") or ""),
            str(payload.get("target") or ""),
            kind=str(payload.get("kind") or "runtime_call"),
            conductive=bool(payload.get("conductive", True)),
            evidence=str(payload.get("evidence") or event.topic),
        )

    async def start(self, context: RuntimeContext) -> None:
        try:
            registry = context.get_service("registry.graph")
            if isinstance(registry, NodeRegistryService):
                self.surface.seed_registry(registry.snapshot())
        except Exception:
            # Optional visualization must not become a lifecycle authority.
            pass
        if not self._bridge_subscription_installed:
            events = context.get_service("kernel.events")
            if isinstance(events, EventService):
                events.subscribe("registry.bridge_registered", self._bridge_event)
                self._bridge_subscription_installed = True
        await super().start(context)


def register() -> dict[str, object]:
    return {
        "name": "eira2.neural.organism",
        "kind": "registry_aware_neural_organism_and_communication_surface",
        "status": "online",
        "isolated": True,
        "file_neurons": True,
        "runtime_nodes": True,
        "runtime_bridges": True,
        "automatic_topology_sync": True,
        "real_execution_activity_only": True,
        "iphone_text_endpoint": "/v1/text",
        "iphone_pcm_endpoint": "/v1/listen",
        "iphone_ambient_endpoint": "/v1/ambient",
        "ambient_wake_gate": True,
        "single_conversation_authority": "conversation.spine",
        "single_delivery_authority": "delivery.gate",
        "invention_usdz_surface": "/inventions",
        "synthetic_membership_conductive": False,
    }
'''
