# Member's Mark WiFi Bed for Home Assistant

Local, cloud-free control of the **Member's Mark adjustable bases with the WiFi box**
(the ones that use the *Member's Mark Base WiFi* app). The integration talks to the
bed's WiFi box directly on your LAN (UDP 5987), the same way the app does when it's
on the same network.

> Unofficial. Not affiliated with Sam's Club, Member's Mark, Keeson or XLink.
> Reverse-engineered from one bed (Luxury Adjustable Base, 2026). Other models using the
> same app are likely to work — please report back.

If your bed uses the **Bluetooth** app (*Member's Mark Base Remote*) instead, use
[ha-adjustable-bed](https://github.com/kristofferR/ha-adjustable-bed), which supports it.

## Features
| Entity | What it does |
|---|---|
| Head / Foot (cover) | Raise, lower, stop, and set position (0–100 %) with live position feedback |
| Under-bed light | On/off with real state |
| Preset I, II, III, M · Flat · Zero‑G | Recall positions |
| Save to preset I/II/III/M | Store the current position (same as long-pressing in the app) |
| Head / Foot massage | Off · Low · Medium · High |
| Massage pattern / timer | Pattern 1–4 · Off / 10 / 20 / 30 min |
| Massage time remaining | Countdown sensor |
| Stop · Massage off | |

Changes made with the remote or the app show up in Home Assistant within a few seconds.

## Install
**HACS (custom repository):** HACS → ⋮ → *Custom repositories* → add
`https://github.com/bobjoylove/ha-members-mark-bed` as type *Integration* →
install **Member's Mark WiFi Bed** → restart Home Assistant.

**Manual:** copy `custom_components/members_mark_bed` into your `config/custom_components/`
folder and restart.

Then: *Settings → Devices & Services → Add Integration → Member's Mark WiFi Bed* and enter
the bed's IP address and access key.

Give the bed a **DHCP reservation** so its IP doesn't change.

## Finding your access key
The bed only accepts commands that carry a 16-byte access key, which the app sends
when it connects. You capture it once from the app:

1. Start a packet capture of the phone's traffic (pick one):
   - **iPhone + Mac:** plug the phone in, then
     `rvictl -s <iPhone UDID>` and `sudo tcpdump -i rvi0 -w bed.pcap udp port 5987`
     (UDID from Finder/Xcode; `rvictl` comes with Xcode command line tools).
   - **Android:** the free **PCAPdroid** app → target the Member's Mark app → export a pcap.
   - **Router/AP with tcpdump** (UniFi, OpenWrt, …):
     `tcpdump -i any -U -s0 -w - host <bed IP> 2>/dev/null > bed.pcap`
     (don't use `ssh -t`, it corrupts the file).
2. With the phone on the **same Wi-Fi network as the bed**, open the app and press a button.
3. Stop the capture and run
   `python3 tools/extract_key.py bed.pcap`

The key appears to stay the same across sessions. We don't yet know whether every bed
shares one key — if you can compare keys between two beds, please open an issue (don't
post the full key) so this step can be dropped if they match.

**Tip:** close the phone app while Home Assistant is controlling the bed — the WiFi box
handles one local connection at a time best.

## Command-line tool
`tools/bedctl.py` controls the bed and helps decode new features:
```bash
export BED_IP=192.168.1.50 BED_KEY=<your key>
python3 tools/bedctl.py head_up 2     # hold head up 2 s
python3 tools/bedctl.py flat
python3 tools/bedctl.py monitor       # live status bytes
python3 tools/bedctl.py probe         # guided test of every button, writes probe_log.txt
```

## Protocol
See [docs/PROTOCOL.md](docs/PROTOCOL.md).

## Known limits
- Setting one massage zone to *Off* while the other is running steps through the higher
  levels (the bed's button only cycles one way; its "massage off" stops both zones).
- Position percentages are learned from the highest reading seen; adjust in the
  integration's *Configure* dialog if 100 % doesn't match full raise.
