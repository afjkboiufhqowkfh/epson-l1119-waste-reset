"""Read the L1119 waste-ink EEPROM cells over the D4 link. Read-only."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from d4client import D4, D4Error

READ_KEY = [0x97, 0x07]
WRITE_KEY = b"Maribaya"
ADDRS = [0x1C, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37]
RESET = {28: 0, 52: 0, 53: 0, 54: 94, 55: 94, 47: 0, 48: 0, 49: 0, 50: 0, 51: 0}


def main():
    trace = "--trace" in sys.argv
    d = D4(trace=trace)
    try:
        rev = d.connect()
        print("CONNECTED, D4 revision = 0x%02x" % rev)
        print()
        print("addr   now      reset-to")
        for a in ADDRS:
            v = d.read_cell(READ_KEY, a)
            target = RESET.get(a)
            print("0x%02X   %-8s %s" % (
                a,
                ("0x%02X (%d)" % (v, v)) if v is not None else "None",
                ("0x%02X (%d)" % (target, target)) if target is not None else "-",
            ))
    except D4Error as exc:
        print("D4 ERROR: %s" % exc)
        return 1
    finally:
        d.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
