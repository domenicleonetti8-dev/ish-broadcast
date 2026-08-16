# broadcast bridge test

## Exact topology

`audio source -> broadcast [classic A2DP Sink] -> strings 1..10 [classic A2DP Source] -> generic speakers`

`broadcast` is a separate portable Bluetooth probe. It is the discoverable
speaker. The iPhone is an ordinary source: open Bluetooth settings, find
`broadcast`, and tap it. Each smaller string is a real independent outbound
connection from the probe to a generic Bluetooth speaker.

## Automated source verification

Run from the repository:

```sh
sh tests/run_broadcast_tests.sh
```

The suite verifies:

- exact lowercase name and A2DP role UUIDs;
- BlueZ adapter readback after configuration;
- rejection of setter-only and stale evidence;
- generic inbound pairing and resolved A2DP Source evidence;
- paired/trusted/resolved outbound A2DP Sink evidence;
- matching PipeWire `bluez_input.*` and `bluez_output.*` nodes;
- a separate live `pw-loopback` for every speaker string;
- ten-string limit, reconnect cooldown, per-speaker delay, and failure
  isolation;
- staged portable installer, service files, WirePlumber role configuration,
  idempotence, and Eira-host refusal;
- C registry, fan-out, PCM, health, stress, sanitizer, and iOS-controller
  regression checks.

The Python tests use controlled BlueZ and PipeWire snapshots to prove the logic.
They never count those snapshots as real radio or audible evidence.

## Install on the portable probe

On a supported Debian/Raspberry Pi OS host that travels with the phone and
speakers:

```sh
bluetoothctl list
sudo sh probe/install.sh \
  --portable \
  --user PROBE_USER \
  --input-controller INPUT_CONTROLLER_MAC
```

Pair each output speaker to its assigned output controller:

```sh
sudo broadcast-pair-speaker CONTROLLER_MAC SPEAKER_MAC
```

## Real connection test

1. Run `broadcast-status`; registration must be false until BlueZ readback
   contains the exact alias and local Audio Sink UUID.
2. On the iPhone, open Bluetooth settings and tap `broadcast`.
3. Confirm the status contains a paired, connected, service-resolved inbound
   Audio Source and a matching `bluez_input.*` node.
4. Power on a paired generic speaker.
5. Confirm its string contains a connected, service-resolved Audio Sink,
   matching `bluez_output.*` node, and live loopback process.
6. Start audio on the iPhone. `end_to_end_streaming` becomes true only while
   the matched PipeWire nodes report `running`.
7. Hear the audio from the real speaker.

Disconnecting one speaker must remove only that string. Other connected strings
must continue.

## Honesty gate

The following never count as connection proof:

- an app or BLE advertisement named `broadcast`;
- a successful setter or process launch without readback;
- an iOS route-picker selection;
- a generated test fixture;
- a stale status file;
- a compiled IPA.

Software status permanently says `physical_audio_proof: not-recorded` until
the real room test is separately documented.
