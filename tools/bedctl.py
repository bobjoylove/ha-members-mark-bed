#!/usr/bin/env python3
"""
Set BED_IP and BED_KEY (32 hex chars, see tools/extract_key.py) first:
  export BED_IP=192.168.1.50 BED_KEY=0123456789abcdef0123456789abcdef

Local (no-cloud) controller and protocol debugger for the Member's Mark WiFi
adjustable base (XLink LAN protocol, UDP 5987). Close the phone app first.

Control:
  python3 bedctl.py head_up 2        # hold Head Up for 2 s (also head_down/foot_up/foot_down)
  python3 bedctl.py flat             # tap a button (flat, zero_g, memory1..4, light, massage_*)
  python3 bedctl.py memory3          # recall preset III (memory1..4 = app I, II, III, M)
  python3 bedctl.py save III         # store current position in preset III (6 s long-press)
  python3 bedctl.py raw 0x00000100   # tap any key code
  python3 bedctl.py rawhold 0x10 2   # hold any key code for 2 s

Debug:
  python3 bedctl.py monitor          # print status bytes live; shows which bytes change
  python3 bedctl.py probe            # guided test of every candidate button -> probe_log.txt
  python3 bedctl.py probe 0x100 0x200   # probe only these codes
"""
import os, socket, struct, sys, time, datetime

BED_IP = os.environ.get("BED_IP", "")
PORT = 5987
# Treat like a password: anyone on your LAN with it can drive the bed.
ACCESS_KEY = bytes.fromhex(os.environ.get("BED_KEY", "")) if os.environ.get("BED_KEY") else b""

# Confirmed: head/foot up/down, flat, zero_g, memory1 (I), memory2 (II), light,
# massage_head/foot (cycle off/low/med/high), massage_timer, massage_off, massage_pattern.
# Others follow Keeson's remote key table and are guesses until probed.
KEYS = {
    "head_up":   0x00000001,
    "head_down": 0x00000002,
    "foot_up":   0x00000004,
    "foot_down": 0x00000008,
    "tilt_up":   0x00000010,
    "tilt_down": 0x00000020,
    "lumbar_up": 0x00000040,
    "lumbar_down": 0x00000080,
    "massage_step":   0x00000100,
    "massage_timer":  0x00000200,
    "massage_foot":   0x00000400,
    "massage_head":   0x00000800,
    "zero_g":    0x00001000,
    "memory1":   0x00002000,
    "memory2":   0x00004000,
    "memory3":   0x00008000,
    "memory4":   0x00010000,
    "light":     0x00020000,
    "massage_off":    0x02000000,
    "massage_pattern": 0x04000000,   # app wave button: starts massage, cycles 4 patterns
    "massage_wave":   0x10000000,
    "flat":      0x08000000,
}
HOLD_KEYS = {"head_up", "head_down", "foot_up", "foot_down", "tilt_up", "tilt_down", "lumbar_up", "lumbar_down"}

# Probe order: things that don't move the bed first.
PROBE_ORDER = [
    ("light", None), ("light", None),
    ("massage_head", None), ("massage_head", None), ("massage_foot", None),
    ("massage_step", None), ("massage_timer", None), ("massage_wave", None), ("massage_off", None),
    ("foot_up", 2.0), ("foot_down", 2.0),
    ("tilt_up", 1.5), ("tilt_down", 1.5), ("lumbar_up", 1.5), ("lumbar_down", 1.5),
    ("memory2", None), ("memory3", None), ("memory4", None), ("flat", None),
]


def frame(ptype, payload):
    return bytes([ptype]) + struct.pack(">I", len(payload)) + payload


def inner(key):
    k = struct.pack("<I", key)
    cs = (0xEDFA - sum(k)) & 0xFFFF
    return bytes.fromhex("aa03000f000000000100000401") + k + struct.pack("<H", cs) + b"\x55"


def status_body(data):
    """Return the bed's status frame from 'aa 83' onward, or None."""
    if not data or data[0] != 0x83:
        return None
    j = data.find(b"\xaa\x83")
    return data[j:] if j >= 0 else None


def describe(body):
    head = int.from_bytes(body[13:15], "little")
    foot = int.from_bytes(body[15:17], "little")
    return f"head={head:5d} foot?={foot:5d} bytes17-28={body[17:29].hex(' ')}"


class Bed:
    def __init__(self, ip=BED_IP):
        self.addr = (ip, PORT)
        self.s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.s.settimeout(2)
        self.msg = 0x0D
        self.session = None
        self.last = None          # last status body
        self.frames = []          # (t, body) captured since reset_capture()

    def _recv_type(self, want, tries=10):
        for _ in range(tries):
            data, _ = self.s.recvfrom(4096)
            if data[0] == want:
                return data
        raise RuntimeError(f"no 0x{want:02x} reply")

    def connect(self, quiet=False):
        self.s.sendto(frame(0x23, b"\x03\x02\x0b" + ACCESS_KEY + bytes.fromhex("006300001e")), self.addr)
        resp = self._recv_type(0x2B)
        self.session = resp[-3:-1]
        if not quiet:
            print(f"handshake ok, device {resp[9:17].hex()} session {self.session.hex()}")
        self.s.sendto(frame(0x33, self.session + b"\x00"), self.addr)
        self.s.sendto(frame(0x73, b"\x03\x02\x0c" + ACCESS_KEY + b"\x00"), self.addr)
        time.sleep(0.3)
        self.pump()

    def pump(self):
        """Read everything waiting; remember status frames."""
        self.s.settimeout(0)
        try:
            while True:
                data, _ = self.s.recvfrom(4096)
                body = status_body(data)
                if body is not None:
                    self.last = body
                    self.frames.append((time.time(), body))
        except (BlockingIOError, socket.timeout):
            pass
        self.s.settimeout(2)

    def send_key(self, key):
        payload = self.session + b"\x02" + struct.pack("<H", self.msg) + inner(key)
        self.msg = (self.msg + 1) & 0xFFFF
        self.s.sendto(frame(0x83, payload), self.addr)

    def hold(self, key, seconds, interval=0.1):
        end = time.time() + seconds
        while time.time() < end:
            self.send_key(key); time.sleep(interval); self.pump()
        self.release()

    def press(self, key):
        for _ in range(3):
            self.send_key(key); time.sleep(0.1); self.pump()
        self.release()

    def release(self):
        for _ in range(3):
            self.send_key(0); time.sleep(0.1); self.pump()

    def idle(self, seconds, interval=0.2):
        """Send 'no button' frames (as the app does) so the bed keeps reporting status."""
        end = time.time() + seconds
        while time.time() < end:
            self.send_key(0); time.sleep(interval); self.pump()

    def ping(self):
        self.s.sendto(frame(0xD0, self.session), self.addr)


def diff(a, b):
    if a is None or b is None:
        return "n/a"
    n = max(len(a), len(b))
    out = []
    for i in range(n):
        x = a[i] if i < len(a) else None
        y = b[i] if i < len(b) else None
        # [7],[9] are counters, the last 3 bytes are checksum + end marker
        if x != y and i not in (7, 9, len(b) - 3, len(b) - 2):
            out.append(f"[{i}] {x:02x}->{y:02x}" if x is not None and y is not None else f"[{i}] {x}->{y}")
    return ", ".join(out) or "no change"


def monitor(bed):
    print("Monitoring. Use the remote or app (or other bedctl commands in another window). Ctrl-C to stop.")
    print("Byte index legend: [13-14]=head position, [15-16]=foot?, the rest unknown.\n")
    prev, t_ping = None, time.time()
    while True:
        bed.idle(0.4)
        if time.time() - t_ping > 8:
            bed.ping(); t_ping = time.time()
        cur = bed.last
        if cur is not None and prev is not None and cur[10:-3] != prev[10:-3]:
            print(f"{datetime.datetime.now():%H:%M:%S.%f}"[:-3], describe(cur), "|", diff(prev, cur))
        elif cur is not None and prev is None:
            print("first:", describe(cur), "| full", cur.hex(" "))
        prev = cur if cur is not None else prev


def probe(bed, items):
    log = open("probe_log.txt", "a")
    log.write(f"\n=== probe {datetime.datetime.now()} ===\n")
    print("For each step: watch/listen to the bed, then type what happened (Enter = nothing).")
    print("Type 'q' to quit early.\n")
    for name, hold in items:
        code = KEYS.get(name, name)
        label = name if isinstance(name, str) and name in KEYS else hex(code)
        bed.idle(1.0)
        before = bed.last
        bed.frames = []
        print(f"--> {label} ({hex(code)}){' hold %.1fs' % hold if hold else ''}")
        if hold:
            bed.hold(code, hold)
        else:
            bed.press(code)
        bed.idle(3.0)
        after = bed.last
        changes = sorted({d for (_, f) in bed.frames for d in diff(before, f).split(", ")} - {"no change", "n/a"})
        note = input("    what happened? ").strip()
        if note.lower() == "q":
            break
        line = (f"{label} {hex(code)} hold={hold} | seen: {note or '-'}\n"
                f"   before: {before.hex(' ') if before else None}\n"
                f"   after : {after.hex(' ') if after else None}\n"
                f"   bytes that changed at any point: {', '.join(changes) or 'none'}\n")
        print(line); log.write(line); log.flush()
        bed.ping()
    log.close()
    print("Saved to probe_log.txt")


def main():
    if len(sys.argv) < 2:
        print(__doc__); sys.exit(1)
    cmd = sys.argv[1]
    if not BED_IP or len(ACCESS_KEY) != 16:
        sys.exit("Set BED_IP and BED_KEY environment variables first (see --help / README).")
    bed = Bed()
    bed.connect()
    if cmd == "monitor":
        try:
            monitor(bed)
        except KeyboardInterrupt:
            pass
    elif cmd == "probe":
        items = [(int(c, 0), None) for c in sys.argv[2:]] or PROBE_ORDER
        probe(bed, items)
    elif cmd == "save":
        name = sys.argv[2] if len(sys.argv) > 2 else ""
        presets = {"I": "memory1", "II": "memory2", "III": "memory3", "M": "memory4"}
        if name.upper() not in presets:
            sys.exit("usage: bedctl.py save I|II|III|M")
        print(f"holding preset {name.upper()} for 6 s to save the current position...")
        bed.hold(KEYS[presets[name.upper()]], 6)
    elif cmd == "raw":
        bed.press(int(sys.argv[2], 0))
    elif cmd == "rawhold":
        bed.hold(int(sys.argv[2], 0), float(sys.argv[3]) if len(sys.argv) > 3 else 2)
    elif cmd in HOLD_KEYS:
        bed.hold(KEYS[cmd], float(sys.argv[2]) if len(sys.argv) > 2 else 2)
    elif cmd in KEYS:
        bed.press(KEYS[cmd])
    else:
        sys.exit(f"unknown command {cmd}; choose from {', '.join(KEYS)}, raw, rawhold, monitor, probe")
    bed.idle(0.5)
    if bed.last is not None:
        print("status:", describe(bed.last))
    print("done")


if __name__ == "__main__":
    main()
