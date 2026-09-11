# Portable probe transport contract

The real Bluetooth endpoint is the portable probe. The iPhone discovers
`broadcast` as a normal Classic Bluetooth speaker and completes the standard
pairing handshake. The iPhone app does not register the endpoint.

## Radio roles

The probe owns these simultaneous roles:

- one inbound Classic Bluetooth A2DP Sink named exactly `broadcast`;
- up to ten independent outbound Classic Bluetooth A2DP Source strings;
- one PipeWire loopback per connected speaker, so a failed output cannot stop
  another output.

BlueZ supplies pairing, trust, profile connection, and controller evidence.
WirePlumber registers both A2DP roles. PipeWire supplies the live audio nodes
and fans the inbound stream out to the speaker sinks.

## Registration proof

The probe is not registered merely because a command succeeded. The BlueZ
service rereads the adapter and requires all of the following:

- controller powered;
- alias exactly `broadcast`;
- pairable and discoverable;
- the local Audio Sink UUID `0000110b-0000-1000-8000-00805f9b34fb`.

Only that readback can set `probe_registered`, `probe_findable`, or
`probe_connectable`.

## Inbound connection proof

The large probe is connected only when BlueZ observes a paired, unblocked,
connected device on the input controller whose services are resolved and
include the Audio Source UUID, and PipeWire exposes the matching
`bluez_input.*` node. Streaming requires that input node to report
`running`.

## Speaker-string proof

A smaller string is connected only when all four facts exist for the same
Bluetooth address:

1. BlueZ reports the speaker paired, trusted, connected, unblocked, and
   service-resolved with the Audio Sink UUID.
2. PipeWire exposes the matching `bluez_output.*` node.
3. That string's independent `pw-loopback` process is alive.
4. The route has not been invalidated by a newer BlueZ snapshot.

A string is streaming only when both its input and output PipeWire nodes report
`running`. Stale status is rejected after the configured freshness window.

## Failure isolation

Each output owns its own reconnect cooldown, PipeWire process, delay, error,
and retry state. Disconnecting or killing one speaker removes only its string.
The ten-output cap is enforced before connection and routing.

## Physical proof

Source tests and CI can prove parsing, evidence gating, service installation,
failure isolation, and command construction. They cannot hear a room. The
runtime therefore retains `physical_audio_proof: not-recorded` until a person
connects a real source to `broadcast` and hears the same stream from the real
speaker outputs.
