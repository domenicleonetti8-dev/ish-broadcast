# broadcast verification record

Date: 2026-08-16

## Deliverable identity

- Bluetooth endpoint name: `broadcast`
- Controller app version/build: `1.7.0 (817)`
- Inbound role: Classic Bluetooth A2DP Sink
- Outbound role: Classic Bluetooth A2DP Source
- Maximum independent speaker strings: 10
- Real runtime: portable Linux probe under `probe/`
- iPhone role: ordinary audio source and optional controller
- Eira role: none

## Implemented

- BlueZ makes the portable probe powered, pairable, discoverable, and named
  exactly `broadcast`.
- WirePlumber registers both A2DP Sink and A2DP Source roles.
- A normal source finds and pairs with `broadcast` through system Bluetooth
  settings, as it would with a generic speaker.
- Paired and trusted generic speakers are discovered and reconnected
  independently.
- PipeWire discovers one inbound `bluez_input.*` node and up to ten outbound
  `bluez_output.*` nodes.
- One `pw-loopback` process is owned per speaker, with independent restart,
  delay, error, and disconnect handling.
- Adapter configuration is reread from BlueZ. Setter success never promotes the
  probe to registered, findable, or connectable.
- Inbound and outbound connection states require matched BlueZ device,
  resolved-service, UUID, PipeWire-node, and route-process evidence.
- Stale BlueZ snapshots are rejected.
- Streaming state additionally requires the relevant PipeWire nodes to report
  `running`.
- The installer is idempotent and refuses a live install on hostname `eira`.
- The iPhone/iSH UI cannot substitute its BLE service, bundle name, or a route
  picker for Classic Bluetooth proof.

## Automated evidence

`sh tests/run_broadcast_tests.sh` runs:

- C probe/string, PCM, fan-out, health, randomized stress, and supported
  sanitizer checks;
- portable-probe BlueZ/PipeWire evidence and failure-isolation unit tests;
- staged installer and idempotence verification;
- iOS project wiring validation.

GitHub Ghost Probe packages the portable probe runtime and separately compiles
and inspects the unsigned iPhone diagnostic artifact. The IPA is not the
Bluetooth radio endpoint.

## Physical proof gate

No software test is reported as an audible connection. Completion in a real
room requires:

1. A source device lists `broadcast` in normal Bluetooth settings.
2. The source pairs and BlueZ reports its resolved A2DP Source connection.
3. At least one generic speaker reports a resolved outbound A2DP connection.
4. Matching `bluez_input.*` and `bluez_output.*` nodes are running.
5. The associated `pw-loopback` process remains alive.
6. A person hears the same source audio from the connected output speaker.

Until that is performed on the portable radio hardware, status remains
`physical_audio_proof: not-recorded`.
