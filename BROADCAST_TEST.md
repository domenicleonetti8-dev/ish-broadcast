# broadcast device test

The app exposes the exact logical name `broadcast`, a readable BLE control
service, and a live audio-route screen. A finger is a selected output route.
The routing table accepts up to 10 fingers and rebuilds whenever an output
joins, leaves, or changes position.

## Ordinary Bluetooth speaker

1. Pair the speaker in iPhone Settings.
2. Open **broadcast** and tap the radio-wave control.
3. Select **Compatible**.
4. Tap **Choose Audio** and select the speaker.
5. Wait for the speaker row to show `bound • active route`.
6. Tap **Test Sound** and confirm the 440 Hz tone is audible.

## iOS multidevice route

1. On iOS 26.2 or newer, select **Multi**.
2. Use **Choose Audio** to activate an eligible bidirectional Bluetooth
   HFP/LE route. The built-in route remains available as the primary route.
3. Check each wanted route in the finger list.
4. Tap **Test Sound**. The same stereo test buffer is mapped to every active
   checked route; unchecked channels remain silent.

The screen reports requested mode, actual audio-session mode, Bluetooth
state, advertising state, active/bound finger counts, mapped channels, and
route errors. If **No sound** is selected after a test, the app switches to
Compatible mode for a standard speaker retry.

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
100,000 randomized finger operations, and 100,000 randomized route rebuilds.
When available, it repeats the suite under AddressSanitizer and
UndefinedBehaviorSanitizer.
