# broadcast verification record

Date: 2026-08-16

## Deliverable identity

- Display and probe name: `broadcast`
- Bundle identifier: `com.domenicleonetti8.broadcast`
- Version/build: `1.6.0 (816)`
- Large-bubble role: classic Bluetooth `A2DP Sink`
- Small-string role: classic Bluetooth `A2DP Source`
- Maximum independent strings: `10`
- iSH control device: `/dev/broadcast`
- PCM device: `/dev/broadcast_audio`, signed 16-bit little-endian stereo,
  48 kHz
- Separate BLE status service: `B0ADC0DE-0000-4F1A-9000-000000000001`
- BLE status characteristic: `B0ADC0DE-0000-4F1A-9000-000000000002`

## Completed and source-verifiable

- The single `broadcast` probe and ten-string topology is encoded as a hard
  contract, including exact role and name constants.
- Invalid evidence is rejected: a probe cannot become registered without a
  native A2DP provider, and cannot become findable/connectable without A2DP
  Sink registration.
- BLE GATT advertising is carried as separate control-plane evidence and never
  promotes classic-speaker state.
- `BroadcastA2DPProbeTransport` defines the complete native seam: Sink
  registration, source connection count, speaker discovery, string attach and
  detach, PCM writes, active-string counts, and frame counters.
- The stock provider returns a stable explicit unsupported result instead of
  fabricating discovery or connection.
- The UI renders one large `broadcast` A2DP Sink bubble with ten smaller linked
  string slots. Colors are driven only by registered, attached, and exact
  `native_a2dp_stream` evidence.
- `/dev/broadcast` exposes start, stop, scan, attach, detach, test, and JSON
  status. `/dev/broadcast_audio` rejects partial stereo frames and unavailable
  routes.
- The string registry enforces a ten-string ceiling, exponential reconnect
  timing, independent joins/leaves, and bounded discovery storage.
- The fan-out core duplicates complete frames to every active sink and records
  failures per sink, so one failed write does not stop other strings.
- The PCM core verifies signed extrema, half-scale samples, invalid sizes,
  insufficient capacity, and unaligned input.
- Stress tests execute 100,000 randomized registry/fan-out operations; normal
  and supported sanitizer runs pass locally.
- GitHub Ghost Probe compiles the unsigned arm64 iPhone app, checks compiled
  identity and boundary markers, packages a standard unsigned IPA payload, and
  publishes logs plus JSON/Markdown evidence.

## Deliberately removed

- The remote/home-radio idea and portable Linux hardware direction.
- Treating an iOS `AVRoutePickerView` or multiroute audio session as the
  one-probe/ten-string product.
- Giving the BLE control plane the `broadcast` local name or calling it an
  old-school Bluetooth speaker.
- Any unverified `connected` or physical-audio claim.

## Remaining non-software boundary

Public stock-iOS app APIs do not expose registration of classic A2DP Sink or
A2DP Source profiles. Therefore the bundled stock provider correctly reports:

- `provider_available: false`
- `registered: false`
- `findable: false`
- `connectable: false`
- `registration_evidence: none`

The software architecture is complete up to that native transport boundary.
Physical completion requires a permitted native environment that implements
`BroadcastNativeA2DPProbeTransport`, then real radio evidence that another
source discovers/connects to `broadcast` and that independent generic speakers
receive the test audio through their string nodes. Until both events occur,
this source is not described as physically Bluetooth-proven.
