#!/usr/bin/env python3
"""
Find your bed's 16-byte access key in a packet capture of the official app.

Works with any capture format (pcap / pcapng from tcpdump, Wireshark, iPhone
rvictl, Android PCAPdroid): it searches the raw bytes for the app's local
handshake on UDP 5987, so no libraries are needed.

  python3 extract_key.py capture.pcap
"""
import re
import sys
from collections import Counter

# 0x23 handshake: 23 00000018 03 xx xx <key16> ...
# 0x73 login:     73 00000014 03 xx xx <key16> 00
PATTERNS = [
    re.compile(rb"\x23\x00\x00\x00\x18\x03..(.{16})", re.S),
    re.compile(rb"\x73\x00\x00\x00\x14\x03..(.{16})\x00", re.S),
]


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    data = open(sys.argv[1], "rb").read()
    keys = Counter(m.group(1).hex() for p in PATTERNS for m in p.finditer(data))
    if not keys:
        sys.exit(
            "No handshake found. Start the capture *before* opening the app, "
            "keep the phone on the same Wi-Fi as the bed, then open the app's remote."
        )
    for key, n in keys.most_common():
        print(f"{key}   (seen {n}x)")
    if len(keys) == 1:
        print("\nUse this as the access key in Home Assistant.")


if __name__ == "__main__":
    main()
