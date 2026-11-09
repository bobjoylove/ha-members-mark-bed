# Member's Mark WiFi base — LAN protocol

XLink local protocol over **UDP 5987** (WiFi box by South Bay International, Keeson actuators).
Frames: `type(1) | length(4, big-endian) | payload`.

## Session
1. Client → bed `0x23`: `03 02 0b <access key, 16 bytes> 00 63 00 00 1e`
2. Bed → client `0x2b`: `00 03 02 0b 00 <device id, 8> ... <session id, 2> 00` — session id = bytes [-3:-1]
3. Client → bed `0x33 <session> 00` and `0x73 03 02 0c <access key> 00`
4. Keepalive `0xd0 <session>` every ~10 s → `0xdb <device id>`

The bed's internet connection (XLink cloud, TCP 23778) is not needed for local control.

## Commands (`0x83`)
`83 00000019 <session> 02 <msg id LE16> aa 03 00 0f 00 00 00 00 01 00 00 04 01 <key LE32> <checksum LE16> 55`
checksum = `0xEDFA − sum(key bytes)`.

- **Tap**: send the key 2–3× at 100 ms, then key `0` 3×.
- **Hold** (motors): resend every 100 ms with no `0` frames in between; send `0` to release.
- **Save preset**: hold the preset key ~6 s. A short tap recalls it.
- The bed only answers with status when it receives a frame, so poll with key `0`
  (as the app does) to get fresh status.

| Key | Function |
|---|---|
| `0x00000001` / `0x00000002` | Head up / down (hold) |
| `0x00000004` / `0x00000008` | Foot up / down (hold) |
| `0x00000200` | Massage timer, cycles 10 → 20 → 30 min |
| `0x00000400` / `0x00000800` | Foot / head massage, cycles off → low → med → high |
| `0x00001000` | Zero‑G |
| `0x00002000` `0x00004000` `0x00008000` `0x00010000` | Presets I, II, III, M |
| `0x00020000` | Light toggle |
| `0x02000000` | Massage off (both zones) |
| `0x04000000` | Massage pattern (app "wave"): starts massage / cycles 4 patterns |
| `0x08000000` | Flat (also stops massage) |

Tilt (`0x10`/`0x20`) and lumbar (`0x40`/`0x80`) did nothing on the tested base.

## Status (bed → client `0x83`, offsets from `aa 83`)
| Bytes | Meaning |
|---|---|
| 9–10 | Sequence counter |
| 13–14 | Head position, LE (0 = flat, ~11 800 max seen) |
| 15–16 | Foot position, LE (~200 flat, ~6 250 max seen) |
| 17 / 18 | Head / foot massage level: 0, 1, 3, 6 |
| 20–22 | Massage time remaining, LE, 10 ms units |
| 24 | bit `0x40` = light on (other bits change while moving) |
| 25 | Massage timer 1/2/3, `ff` = off. Also `01` while a preset is being saved |
| 27 | Massage pattern 0–3 |

Positions alternate between two slightly different readings frame to frame
(head ±25, foot ±130).
