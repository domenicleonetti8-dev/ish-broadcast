# Native transport contract

`BroadcastNativeA2DPProbeTransport` is the only missing radio-facing component.
It is loaded by class name and must conform to
`BroadcastA2DPProbeTransport`. The rest of the product does not change when a
provider is linked.

## Large probe

`startWithName:error:` receives exactly `broadcast`. Success means the provider
has registered a virtual classic-Bluetooth audio endpoint with the A2DP Sink
role. The provider then exposes independent evidence through these properties:

- `registered`: the classic A2DP Sink service/profile registration exists;
- `findable`: the virtual endpoint is visible to the intended Bluetooth source;
- `connectable`: that source can select and connect to it;
- `inboundSourceConnections`: the count of established inbound A2DP source
  sessions.

On the phone-local target, “findable” means the source-side system Bluetooth UI
can resolve the virtual endpoint as `broadcast`; a BLE advertisement, app name,
or GATT service is not evidence. An impossible combination is rejected by
`BroadcastProbeContract`.

## Speaker strings

`startSpeakerDiscovery` begins discovery of generic classic Bluetooth Audio
Sink devices. `speakerStrings` returns at most ten dictionaries with this
schema:

| Key | Type | Meaning |
|---|---|---|
| `id` | string | Stable native device identifier |
| `name` | string | Speaker name |
| `state` | string | `discovered`, `attaching`, `attached`, `streaming`, `reconnecting`, or `error` |
| `attached` | boolean | User selected this string |
| `active` | boolean | A2DP media stream is currently established |
| `evidence` | string | Exactly `native_a2dp_stream` when active; otherwise `none` |
| `reconnect_attempts` | integer | Per-string retry count |

`attachSpeakerString:error:` and `detachSpeakerString:error:` affect only the
named string. Discovery, retry timers, queues, codec state, frame counters, and
errors must be isolated per identifier.

## PCM and fan-out

`writePCM16Stereo:length:error:` accepts signed 16-bit little-endian,
interleaved stereo PCM at 48 kHz. It must queue the same complete frames to each
active string. A failed or full queue increments only that string's failure
state and cannot stop writes to other active strings. The provider exposes
aggregate `sourceFrames`, `queuedFrames`, `mappedChannels`,
`activeSpeakerStrings`, and `audioEngineRunning` for health evidence.

The in-tree `BroadcastFanout`, `BroadcastPCM`, and string registry cores are the
reference semantics and are covered by deterministic, randomized, sanitizer,
and failure-isolation tests.

## Stop and proof

`stopSpeakerDiscovery` stops discovery without fabricating disconnects.
`stop` closes inbound and outbound profile sessions and removes the virtual
classic endpoint. The provider must never preserve `registered`, `findable`,
`connectable`, `active`, or `native_a2dp_stream` after the underlying native
evidence is gone.

A successful compile is not physical proof. Completion requires another source
to find/connect to `broadcast` and a person to hear the same test tone on the
active generic speakers.
