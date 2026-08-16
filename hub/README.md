# Broadcast Bluetooth hub

The hub is the component that makes **broadcast** appear in the iPhone's own
**Settings > Bluetooth** list as an audio device. It runs on a Raspberry Pi or
another Debian Linux computer with Bluetooth Classic support:

`iPhone -> A2DP sink named broadcast -> PipeWire -> A2DP speaker sinks`

The iPhone is the audio source. BlueZ and WirePlumber make the Pi an A2DP sink
for the phone and an A2DP source for the speakers. The supervisor creates one
independent `pw-loopback` process per connected speaker. A route that fails or
disconnects is stopped and retried without stopping the other routes.

## Hardware

- Raspberry Pi 5 with current 64-bit Raspberry Pi OS Bookworm or newer.
- The Pi's built-in Bluetooth controller for the iPhone-facing endpoint.
- A powered USB hub and one reliable Bluetooth USB controller per speaker are
  recommended for five or more independent outputs. One controller may work
  with a small number of speakers, but its radio bandwidth and firmware are a
  physical limit that software cannot remove.
- Two Bluetooth speakers are the minimum end-to-end proof target. The manager
  supports up to 10 paired and trusted speakers.

No Mac, Xcode, TestFlight, jailbreak, or iSH runtime is required for the hub.
The native iPhone app in this repository remains an optional control/status
surface; its BLE advertisement is not the iPhone's audio accessory.

## Install

On the Pi, from this repository:

```sh
bluetoothctl list
sudo sh hub/install.sh \
  --user YOUR_PI_USER \
  --input-controller BUILT_IN_CONTROLLER_MAC
```

The installer is idempotent. It installs BlueZ, PipeWire, WirePlumber, the
headless pairing/reconnect service, the per-speaker fanout service, and both
WirePlumber 0.4 and 0.5 configuration formats. It preserves an existing
`/etc/broadcast-hub/config.json` on later runs.

After installation, the input controller is continuously held in this state:

- alias exactly `broadcast`;
- powered, pairable, and discoverable;
- Audio/Video Loudspeaker device class where the controller supports it;
- A2DP sink registered by WirePlumber.

All other controllers stay powered but non-discoverable and non-pairable.

## Pair each output speaker

Put one speaker into pairing mode and bind it to its assigned controller:

```sh
sudo broadcast-pair-speaker CONTROLLER_MAC SPEAKER_MAC
```

Repeat with a separate controller for each speaker. Only paired, trusted,
unblocked devices that publish the standard Audio Sink UUID are eligible. The
root service discovers them dynamically, reconnects them independently, and
enforces the 10-output maximum.

For deterministic controller binding and route order, edit
`/etc/broadcast-hub/config.json`:

```json
{
  "speaker_priority": [
    "10:20:30:40:50:60",
    "10:20:30:40:50:61"
  ],
  "speaker_controllers": {
    "10:20:30:40:50:60": "00:11:22:33:44:56",
    "10:20:30:40:50:61": "00:11:22:33:44:57"
  },
  "speaker_delays_ms": {
    "10:20:30:40:50:60": 0,
    "10:20:30:40:50:61": 175
  }
}
```

Keep all other keys from the installed file. Delays add up to 5000 ms to
faster speakers so their hardware buffering can be aligned with the slowest
speaker. Restart both services after configuration changes:

```sh
sudo systemctl restart broadcast-bluetooth.service
systemctl --user restart broadcast-hub.service
```

## iPhone connection and proof gate

1. Open **Settings > Bluetooth** on the iPhone.
2. Select the device named exactly **broadcast** and complete pairing.
3. Start music or a test tone on the iPhone.
4. Run `broadcast-status` on the Pi.

The software gate requires all of the following:

- `endpoint_name` is `broadcast` and `controller_discoverable` is true;
- a `bluez_input.*` node exists for the phone's incoming A2DP stream;
- at least two independent `bluez_output.*` nodes have live loopback
  processes;
- `runtime_ready` and `minimum_output_gate_met` are true.

The final physical gate is stricter: the same phone audio must actually be
heard from at least two independent speakers. Status cannot hear the room, so
it deliberately reports `physical_audio_proof: not-recorded` until that test
is performed and documented. Source tests are never substituted for that
audible proof.

## Diagnostics

```sh
sudo systemctl status broadcast-bluetooth.service
systemctl --user status broadcast-hub.service
broadcast-status
bluetoothctl show BUILT_IN_CONTROLLER_MAC
wpctl status
```

`bluetoothctl show` should report alias `broadcast`, `Discoverable: yes`, and
the local Audio Sink service. The user service writes live graph state to
`/run/user/UID/broadcast-hub/status.json`; the system service writes controller
and reconnect state to `/run/broadcast-hub/bluez-status.json`.

## Repeatable source verification

```sh
sh tests/run_broadcast_tests.sh
```

The suite uses fake BlueZ controllers, devices, PipeWire nodes, and loopback
processes to verify exact naming, role wiring, allowlists, controller binding,
the 10-device cap, reconnect cooldowns, per-speaker delays, dynamic join/leave,
installer idempotence, and failure isolation. It does not claim radio or
audible proof without the actual Pi, iPhone, and speakers.
