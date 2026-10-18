"""Minimal, robust D4 client for the Epson L1119 over Windows USBPRINT.

Based on the byte sequence proven by d4probe3.py: drain hard, ENTER, INIT,
OPENCHANNEL, then EPSON-CTRL requests with the credit handshake.

Read-only by default; the caller decides whether to write.
"""

import struct
import time

from epson_usb.backends.usbprint_win import device_paths, WindowsUsbPrintTransport
from epson_usb.util import hexdump

ENTER = b"\x00\x00\x00\x1b\x01@EJL 1284.4\n@EJL\n@EJL\n"
SOCK = 0x02


def pkt(psid, ssid, payload, credit=0, control=0):
    return struct.pack(">BBHBB", psid, ssid, 6 + len(payload), credit, control) + payload


class D4Error(Exception):
    pass


class D4:
    def __init__(self, path=None, trace=False):
        self.trace = trace
        self.path = path or device_paths()[0]
        self.t = WindowsUsbPrintTransport(self.path)
        self.buf = b""
        self.rev = None
        self.opened = False

    # -- transport ---------------------------------------------------------
    def open(self):
        if not self.opened:
            self.t.open()
            self.opened = True
        return self

    def close(self):
        try:
            self.t.close()
        finally:
            self.opened = False

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # -- io ----------------------------------------------------------------
    def _log(self, tag, data):
        if self.trace:
            print("     %-6s %s" % (tag, hexdump(data) if data else "(empty)"))

    def drain(self, quiet_ms=350, max_rounds=40):
        """Read until two consecutive empty reads; drop whatever was queued."""
        total = b""
        empty = 0
        for _ in range(max_rounds):
            d = self.t.read(1024, quiet_ms)
            if not d:
                empty += 1
                if empty >= 2:
                    break
            else:
                empty = 0
                total += d
        self.buf = b""
        if total:
            self._log("drain", total)
        return total

    def send(self, psid, ssid, payload, credit=0, control=0):
        p = pkt(psid, ssid, payload, credit, control)
        self._log(">", p)
        self.t.write(p, 3000)
        return p

    def _fill(self, ms):
        d = self.t.read(1024, ms)
        if d:
            self.buf += d
            self._log("<raw", d)
            return True
        return False

    def recv(self, ms=2000):
        """Return (psid, ssid, payload) of the next packet, or None on timeout."""
        deadline = time.monotonic() + ms / 1000.0
        while len(self.buf) < 6:
            remain = deadline - time.monotonic()
            if remain <= 0:
                return None
            if not self._fill(int(remain * 1000) + 1):
                return None
        psid, ssid, length, credit, control = struct.unpack(">BBHBB", self.buf[:6])
        if length < 6:
            self.buf = self.buf[6:]
            return (psid, ssid, b"")
        while len(self.buf) < length:
            remain = deadline - time.monotonic()
            if remain <= 0 or not self._fill(int(remain * 1000) + 1):
                self.buf = self.buf[6:]
                return None
        payload = self.buf[6:length]
        self.buf = self.buf[length:]
        return (psid, ssid, payload)

    # -- handshake ---------------------------------------------------------
    def connect(self, attempts=3):
        """Run the handshake, retrying the whole sequence if the printer stalls.

        The L1119 firmware needs a quiet gap between handshake steps: it often
        ignores a request sent too soon after the previous reply. Draining
        before every step (which costs ~0.7 s of quiet) is what makes it
        deterministic.
        """
        last = None
        for _ in range(attempts):
            try:
                return self._connect_once()
            except D4Error as exc:
                last = exc
                self.drain()
        raise last

    def _connect_once(self):
        self.open()
        self.drain()
        self._log(">", ENTER)
        self.t.write(ENTER, 3000)
        time.sleep(0.3)
        enter = self.recv(3000)
        if enter is None:
            raise D4Error("no answer to the EJL enter sequence")
        self._log("enter", enter[2])

        rev = 0x20
        ok = False
        for _ in range(6):
            self.drain()
            self.send(0, 0, bytes([0x00, rev]), credit=1)
            r = self.recv(3000)
            payload = r[2] if r else b""
            self._log("init", payload)
            if len(payload) >= 3 and payload[0] == 0x80:
                if payload[1] == 0x00:
                    ok = True
                    break
                if payload[2] and payload[2] != rev:
                    rev = payload[2]
                    continue
        if not ok:
            raise D4Error("D4 Init failed (tried revision 0x%02x)" % rev)
        self.rev = rev

        if rev == 0x10:
            open_payload = struct.pack(">BBBHHHH", 1, 2, SOCK, 0x0100, 0x0100, 0x0000, 0x0000)
        else:
            open_payload = struct.pack(">BBBHHH", 1, 2, SOCK, 0x0100, 0x0100, 0x0000)
        for _ in range(4):
            self.drain()
            self.send(0, 0, open_payload, credit=1)
            r = self.recv(3000)
            payload = r[2] if r else b""
            self._log("open", payload)
            if len(payload) >= 2 and payload[0] == 0x81 and payload[1] == 0x00:
                return rev
        raise D4Error("D4 OpenChannel failed on socket %d" % SOCK)

    # -- commands ----------------------------------------------------------
    def _credit_request(self):
        if self.rev == 0x10:
            self.send(0, 0, struct.pack(">BBBHH", 0x04, 0x02, SOCK, 0x0080, 0xFFFF), credit=1)
        else:
            self.send(0, 0, struct.pack(">BBBH", 0x04, 0x02, SOCK, 0x0008), credit=1)
        for _ in range(4):
            r = self.recv(1500)
            if r is None:
                break
            self._log("creditreq", r[2])
            if r[2] and r[2][0] == 0x84:
                break

    def request(self, frame, tries=14, attempts=3):
        for _ in range(attempts):
            self._credit_request()
            self.send(0, 0, struct.pack(">BBBH", 0x03, 0x02, SOCK, 0x0008), credit=1)
            r = self.recv(1500)
            self._log("creditreply", r[2] if r else b"")
            self.send(SOCK, SOCK, frame, credit=8)
            for _ in range(tries):
                r = self.recv(2000)
                if r is None:
                    continue
                psid, ssid, payload = r
                if psid == SOCK and payload:
                    self._log("reply", payload)
                    return payload
            time.sleep(0.2)
        return None

    # -- EEPROM helpers ----------------------------------------------------
    def read_cell(self, read_key, addr):
        from epson_usb.epson_ctrl import eeprom_read_frame, parse_eeprom_reply

        reply = self.request(eeprom_read_frame(read_key, addr))
        if not reply:
            return None
        parsed = parse_eeprom_reply(reply)
        if parsed is None:
            return None
        got_addr, value = parsed
        if got_addr != addr:
            return None
        return value

    def write_cell(self, read_key, write_key, addr, value):
        from epson_usb.epson_ctrl import eeprom_write_frame, write_confirmed

        reply = self.request(eeprom_write_frame(read_key, write_key, addr, value))
        return write_confirmed(reply), reply
