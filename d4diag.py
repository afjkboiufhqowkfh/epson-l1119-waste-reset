"""Trace the D4 handshake against the L1119 over Windows USBPRINT.

Read-only: it never writes EEPROM. It just runs the handshake and dumps
every byte exchanged, so we can see which interface answers and where the
session stalls.
"""

import sys
import time

from epson_usb.backends.usbprint_win import device_paths, WindowsUsbPrintTransport
from epson_usb.d4 import D4Session, Timeouts, INITIAL_REVISION, EPSON_CTRL_SOCKET
from epson_usb.util import hexdump


def show(direction, event):
    if isinstance(event, (bytes, bytearray)):
        print("   %-6s %s" % (direction, hexdump(bytes(event))))
    else:
        print("   %-6s %r" % (direction, event))


def run_one(path, factor):
    print("=== path: %s" % path)
    print("    timeouts scaled x%s" % factor)
    t = WindowsUsbPrintTransport(path)
    try:
        t.open()
    except Exception as exc:
        print("    OPEN FAILED: %s" % exc)
        return None
    s = D4Session(t, timeouts=Timeouts.scaled(factor), trace=show)
    result = None
    try:
        rev = s.connect()
        result = rev
        print("    CONNECTED, revision=0x%02x" % rev)
    except Exception as exc:
        print("    CONNECT FAILED: %s" % exc)
    finally:
        s.close()
    return result


def main():
    paths = device_paths()
    print("usbprint device paths found: %d" % len(paths))
    for p in paths:
        print("   %s" % p)
    print()

    for factor in (1, 3):
        for p in paths:
            rev = run_one(p, factor)
            if rev is not None:
                print("    >>> SUCCESS on %s (x%s)" % (p, factor))
                return 0
        print()

    print("No interface completed the handshake.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
