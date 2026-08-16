# broadcast probe test

## Exact topology under test

`audio source -> broadcast [classic A2DP Sink] -> strings 1..10 [classic A2DP Source] -> generic speakers`

`broadcast` is the one discoverable and connectable speaker probe. A string is
an independent outbound connection from that probe to one generic Bluetooth
speaker. The phone-local product must not replace this topology with an iOS
audio-route picker, a BLE-only name, a remote machine, or a pretend connection.

## iSH control surface

Inside this fork of iSH:

```sh
printf 'start\n' > /dev/broadcast
cat /dev/broadcast
printf 'scan\n' > /dev/broadcast
printf 'attach SPEAKER_ID\n' > /dev/broadcast
printf 'detach SPEAKER_ID\n' > /dev/broadcast
printf 'test\n' > /dev/broadcast
printf 'stop\n' > /dev/broadcast
```

`cat /dev/broadcast` returns one JSON record. The important fields are:

- `probe.profile`: `classic_bluetooth_a2dp_sink`
- `probe.registered`, `findable`, `connectable`, and
  `inbound_source_connections`: native transport evidence for the large bubble
- `maximum_strings`: always `10`
- `string_nodes`: smaller A2DP Source bubbles with independent state and
  evidence
- `control_plane.counts_as_classic_speaker_registration`: always `false`
- `hardware_audio_confirmation`: `required` until a human hears the test tone

`/dev/broadcast_audio` accepts whole frames of signed 16-bit little-endian,
interleaved stereo PCM at 48 kHz. A write is rejected until the classic probe
is registered and at least one speaker string is physically active.

## Expected stock-iOS result

Tap **Register Probe** or write `start`. With only public stock-iOS APIs, the
large bubble remains unregistered and the status is:

```json
{
  "probe": {
    "name": "broadcast",
    "profile": "classic_bluetooth_a2dp_sink",
    "state": "native_a2dp_provider_unavailable",
    "registered": false,
    "findable": false,
    "connectable": false,
    "registration_evidence": "none"
  }
}
```

That is a passing honesty check, not a physical Bluetooth pass. A BLE GATT scan
from another device may see the separate status service UUID, but that service
does not advertise the `broadcast` local name and must not change the classic
probe state.

## Native-provider integration proof

A linked class named `BroadcastNativeA2DPProbeTransport` must conform to
`BroadcastA2DPProbeTransport`. Physical completion requires all of these:

1. A separate Bluetooth source discovers exactly lowercase `broadcast` as a
   classic audio speaker and connects to it.
2. The report shows `probe.registered`, `findable`, and `connectable` from the
   native provider, with at least one inbound source connection.
3. Up to ten generic speakers appear as distinct `string_nodes`; each active
   node has the exact transport evidence `native_a2dp_stream`.
4. Attaching, detaching, or failing one string does not mutate another string's
   connection or frame counter.
5. The same PCM frames reach every active string; inactive strings remain
   silent.
6. **Test Sound** is heard on every active physical speaker.

No software report alone may claim steps 1 or 6.

## Repeatable source verification

Run:

```sh
sh tests/run_broadcast_tests.sh
```

The suite checks the exact name and roles, native-evidence invariants, the
ten-string ceiling, independent bind/reconnect state, per-string failure
isolation, exact fan-out, PCM conversion and alignment, readiness ordering,
100,000 randomized string operations, project wiring, the bubble UI markers,
the `/dev` commands, and removal of the obsolete hardware detour. When the
compiler supports them, the C tests repeat under AddressSanitizer and
UndefinedBehaviorSanitizer.
