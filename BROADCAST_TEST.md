# broadcast device test

## Settings-visible multi-speaker endpoint

The Raspberry Pi/Linux hub is the component that must appear in the same
iPhone's Bluetooth Settings as `broadcast`. Install and pair it using
[hub/README.md](hub/README.md), select **broadcast** on the iPhone, and play
phone audio. `broadcast-status` must show an incoming `bluez_input.*` node and
at least two independent active output routes. Completion requires hearing the
same audio from at least two physical speakers; a source or graph test alone is
not accepted as physical proof.

The tests below cover the optional native iPhone controller and its direct iOS
routes. Its BLE local name is visible to other devices, not to its own iPhone
as an audio accessory.

## Native controller app

The app exposes the exact logical name `broadcast`, a readable BLE control
service, and a live audio-route screen. A finger is a remembered logical
output. The table can remember up to 10 fingers and rebuilds whenever an
output joins, leaves, or changes position. Physical playback is limited to
the routes iOS exposes: one system-selected output in Compatible mode, or the
built-in route plus one eligible bidirectional secondary device in iOS 26.2
dual-route mode.

## Ordinary Bluetooth speaker

1. Pair the speaker in iPhone Settings.
2. Open **broadcast** and tap the radio-wave control.
3. Select **Compatible**.
4. Tap **Choose Audio** and select the speaker.
5. Wait for the speaker row to show `bound • active route`.
6. Tap **Run Check**. The app checks Bluetooth permission/state, BLE service,
   local-name advertisement, audio engine, bound route, and the PCM software
   signal path.
7. Tap **Test Sound** and confirm the 440 Hz tone is audible.

## iOS multidevice route

1. On iOS 26.2 or newer, select **Multi**.
2. Use **Choose Audio** to activate an eligible bidirectional Bluetooth
   HFP/LE route. The built-in route remains available as the primary route.
3. Check the wanted routes shown by iOS in the finger list.
4. Tap **Test Sound**. The same stereo test buffer is mapped to every active
   checked route; unchecked channels remain silent.

The screen reports requested mode, actual audio-session mode, Bluetooth
state, advertising state, logical and active route counts, the current
physical route maximum, mapped channels, and route errors. It does not claim
that 10 ordinary Bluetooth speakers can be active when iOS exposes fewer
routes. If **No sound** is selected after a test, the app switches to
Compatible mode for a standard speaker retry.

The share button exports a timestamped JSON diagnostic report containing the
current route snapshot, health state, last software probe, app/build identity,
and the last 64 lifecycle events. `health_ready` means the software path is
ready for a listening test; `hardware_audio_confirmation` remains `required`
until a person actually hears the test sound.

## BLE control-service check

From a second BLE-central device, scan while the app is in the foreground:

- Local name: `broadcast`
- Primary service: `B0ADC0DE-0000-4F1A-9000-000000000001`
- Readable status characteristic:
  `B0ADC0DE-0000-4F1A-9000-000000000002`

Reading the status characteristic returns the same live JSON shown by
`cat /dev/broadcast`.

## Raw PCM input

`/dev/broadcast_audio` accepts signed 16-bit little-endian, interleaved
stereo PCM at 48 kHz. Writes must contain whole four-byte stereo frames and
are rejected until at least one checked output is actively mapped.

## Repeatable core verification

Run `sh tests/run_broadcast_tests.sh`. The suite covers independent bind and
reconnect states, the 10-finger limit, join/leave route rebuilds, exact
stereo duplication, silent unchecked routes, per-sink failure isolation,
signed PCM conversion (including unaligned input), readiness-state ordering,
software-probe gating, 100,000 randomized finger
operations, and 100,000 randomized route rebuilds. When available, it repeats
the suite under AddressSanitizer and UndefinedBehaviorSanitizer.
