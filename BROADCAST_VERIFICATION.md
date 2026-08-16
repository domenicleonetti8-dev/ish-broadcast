# Broadcast verification record

Date: 2026-08-15

## Deliverable identity

- App display name: `broadcast`
- Bundle identifier: `com.domenicleonetti8.broadcast`
- Version: `1.4.1`
- Build: `814`
- BLE local name: `broadcast`
- BLE service: `B0ADC0DE-0000-4F1A-9000-000000000001`
- BLE status characteristic: `B0ADC0DE-0000-4F1A-9000-000000000002`
- PCM device: `/dev/broadcast_audio`, signed 16-bit little-endian stereo,
  48 kHz

## Evidence completed in this source tree

`sh tests/run_broadcast_tests.sh` passes both its normal and sanitizer runs.
The suite verifies:

- bind, unbind, reconnect, discovery-table replacement, and the 10-finger
  logical limit;
- exact stereo route mapping, unchecked-route silence, route changes, and the
  maximum selected-route bound;
- raw PCM conversion for zero, signed extrema, half-scale samples, invalid
  frame sizes, insufficient capacity, and unaligned input;
- 100,000 randomized finger/fanout operations and 100,000 randomized route
  rebuilds;
- the app plist, storyboard XML, Xcode source phase, framework links, unique
  Xcode object IDs, version/build numbers, bundle identifier, Ghost Probe
  workflow, and TestFlight lane wiring.
- exact lowercase `broadcast` enforcement in the Linux endpoint configuration
  and BlueZ adapter alias;
- WirePlumber 0.4 and 0.5 registration of both A2DP sink (phone input) and
  A2DP source (speaker output) roles, with headless seat monitoring disabled;
- dynamic paired/trusted Audio Sink discovery, controller binding, reconnect
  cooldowns, allowlists, priority order, and the 10-speaker hard limit;
- a separate `pw-loopback` process per speaker, dynamic joins/leaves,
  per-speaker delay calibration, and proof that one failed route does not stop
  another;
- idempotent staged installation of the system service, user service, scripts,
  shared configuration, and both supported WirePlumber formats.

The GitHub **Ghost Probe** workflow is the compile gate for the current native
iOS source. It runs on a hosted macOS runner, compiles an unsigned arm64
iPhone app, inspects the compiled bundle and linked frameworks, searches the
executable for the Broadcast device/UUID markers, and publishes the app plus
its logs and JSON/Markdown proof reports.

## Evaluation of the supplied app archive

The supplied `ish-broadcast-iphone.zip` contains a real arm64 Mach-O iPhone
app, but it is the older iSH `1.3.3` build `812`, not this `1.4.1` source. It
has no `_CodeSignature` directory or embedded provisioning profile, lacks the
current audio-route UI and PCM implementation, and is not installable on a
stock iPhone. Its archive SHA-256 is:

`654aeea9ca81a50aa90b5e01b872283f9603900d4c17e45c452beb3a8abab096`

That old app is deliberately excluded from the final source bundle so it
cannot be mistaken for the current deliverable.

## Physical behavior and hard limit

The app can remember 10 logical fingers. Public iPhone audio routing still
controls the number of simultaneous physical outputs:

- Compatible mode: one system-selected audio output.
- iOS 26.2 dual-route mode: the built-in route plus one eligible
  bidirectional secondary device.

The BLE name `broadcast` is advertised to **other BLE-central devices** while
the app is running. An iPhone does not list its own advertisement in its own
Bluetooth Settings screen, and a BLE control advertisement does not turn the
iPhone into a Bluetooth speaker.

The corrected Settings-visible path uses a separate Raspberry Pi/Linux radio:

`iPhone -> A2DP sink named broadcast -> PipeWire -> A2DP speaker sinks`

The hub supports 10 eligible outputs in software. Five or more reliable
independent Bluetooth streams should use a powered USB hub and separate
Bluetooth controllers; actual radio bandwidth, codec support, and each
speaker's internal buffering remain hardware limits. Per-speaker added delays
can align faster speakers but cannot make unsupported radio concurrency real.

## What constitutes a complete device proof

Portable code, project wiring, installer staging, and failure isolation are
verified here. The remaining hub proof cannot be fabricated by a source test:
the hub must be installed on the Pi, the same iPhone must list and connect to
`broadcast`, `broadcast-status` must report at least two live routes, and the
same phone audio must be heard on at least two independent speakers. Until
those events are recorded, the source must not be described as physically
Bluetooth-tested or guaranteed on the target radios.

TestFlight signing is only relevant to the optional controller app. It is not
required for the Raspberry Pi endpoint to appear in iPhone Bluetooth Settings.
