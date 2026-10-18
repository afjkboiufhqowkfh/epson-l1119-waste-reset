"""Permanent waste-ink counter reset for the Epson L1119 over USB (D4).

Reads and backs up EEPROM 0x00-0x3F, prints the plan, and (unless --dry-run)
writes the reset set, verifying every cell afterwards.

Model data (reinkpy / epson_print_conf): read_key [0x97,0x07], reset set below.

Write-key encoding
------------------
The key that goes on the wire is the plaintext key shifted by +1 per byte
(epson_print_conf's ``caesar``). reinkpy stores it both ways: ``wkey`` is the
shifted form and ``wkey1`` the plaintext, so 'Maribaya' +1 == 'Nbsjcbzb'.
``epson_usb.epson_ctrl.eeprom_write_payload`` expects the *shifted* bytes.
Sending the plaintext key still earns a ``:OK;`` reply, but the firmware
discards the value -- the trap the reference tool documents for the XP-950.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from d4client import D4, D4Error

READ_KEY = [0x97, 0x07]
# Candidate keys, shifted form first, plaintext second (for the record).
WRITE_KEYS = [b"Nbsjcbzb", b"Maribaya"]

# reinkpy L1119/ET-1110 reset set (address -> value)
RESET = {
    0x1C: 0x00, 0x2F: 0x00,
    0x30: 0x00, 0x31: 0x00, 0x32: 0x00, 0x33: 0x00,
    0x34: 0x00, 0x35: 0x00, 0x36: 0x5E, 0x37: 0x5E,
}
BACKUP_LO, BACKUP_HI = 0x00, 0x3F
MAIN_DIV = 63.46
BORDER_DIV = 34.16

HERE = os.path.dirname(os.path.abspath(__file__))


def le16(v_lo, v_hi):
    return (v_hi << 8) | v_lo


def hx(v):
    return "0x%02X" % v if v is not None else "None"


def main():
    dry = "--dry-run" in sys.argv
    trace = "--trace" in sys.argv

    d = D4(trace=trace)
    try:
        rev = d.connect()
        print("CONNECTED, D4 revision = 0x%02x" % rev)
        print()

        print("Reading EEPROM 0x%02X-0x%02X for backup..." % (BACKUP_LO, BACKUP_HI))
        cells = {}
        missing = []
        for addr in range(BACKUP_LO, BACKUP_HI + 1):
            v = d.read_cell(READ_KEY, addr)
            if v is None:
                missing.append(addr)
            else:
                cells[addr] = v
        stamp = time.strftime("%Y%m%d_%H%M%S")
        bpath = os.path.join(HERE, "backup_l1119_%s.json" % stamp)
        with open(bpath, "w", encoding="utf-8") as fh:
            json.dump({"model": "L1119", "read_key": READ_KEY,
                       "range": [BACKUP_LO, BACKUP_HI],
                       "created": stamp, "cells": {str(k): v for k, v in cells.items()}},
                      fh, indent=1)
        print("backup written: %s (%d cells read, %d unreadable)"
              % (bpath, len(cells), len(missing)))
        if missing:
            print("unreadable addresses: %s" % ", ".join("0x%02X" % a for a in missing))
        print()

        main_now = le16(cells.get(0x30), cells.get(0x31)) if 0x30 in cells and 0x31 in cells else None
        bord_now = le16(cells.get(0x32), cells.get(0x33)) if 0x32 in cells and 0x33 in cells else None
        if main_now is not None:
            print("main waste counter (0x30/0x31): %d  ->  %.1f%%" % (main_now, main_now / MAIN_DIV))
        if bord_now is not None:
            print("borderless counter (0x32/0x33): %d  ->  %.1f%%" % (bord_now, bord_now / BORDER_DIV))
        print()

        print("Plan (address: now -> target):")
        changes = []
        for addr in sorted(RESET):
            now = cells.get(addr)
            tgt = RESET[addr]
            mark = ""
            if now is None:
                mark = "  (current value unknown)"
            elif now != tgt:
                mark = "  *"
                changes.append(addr)
            print("  0x%02X: %-8s -> 0x%02X%s" % (addr, hx(now), tgt, mark))
        print("cells that will change: %s"
              % (", ".join("0x%02X" % a for a in changes) if changes else "(none)"))
        print()

        if dry:
            print("DRY RUN: nothing written. Re-run without --dry-run to apply.")
            return 0

        # Probe the write key on a cell whose value must change, and trust only
        # the read-back: a `:OK;` reply alone is not proof the byte moved.
        probe_addr = next((a for a in sorted(RESET)
                           if a in cells and cells[a] != RESET[a]), None)
        if probe_addr is None:
            print("Nothing to do: every reset cell already holds its target value.")
            return 0
        print("Probing write key on 0x%02X (%s -> 0x%02X)..."
              % (probe_addr, hx(cells.get(probe_addr)), RESET[probe_addr]))

        chosen = None
        for key in WRITE_KEYS:
            ok, reply = d.write_cell(READ_KEY, key, probe_addr, RESET[probe_addr])
            time.sleep(0.2)
            back = d.read_cell(READ_KEY, probe_addr)
            committed = (back == RESET[probe_addr])
            print("  key %r -> reply %-5s read-back %-8s %s"
                  % (key, "OK" if ok else "NA", hx(back),
                     "COMMITTED" if committed else "discarded (no effect)"))
            if committed:
                chosen = key
                break
        if chosen is None:
            print("ERROR: no candidate key committed the probe write; "
                  "aborting without further changes.")
            return 2
        print("using write key %r" % chosen)
        print()

        print("Writing reset set...")
        for addr in sorted(RESET):
            if addr == probe_addr:
                continue
            ok, reply = d.write_cell(READ_KEY, chosen, addr, RESET[addr])
            print("  0x%02X <- 0x%02X : %s"
                  % (addr, RESET[addr], "accepted" if ok else "FAILED %r" % reply))
            time.sleep(0.15)

        print()
        print("Verifying by reading back...")
        allok = True
        for addr in sorted(RESET):
            v = d.read_cell(READ_KEY, addr)
            good = (v == RESET[addr])
            allok = allok and good
            print("  0x%02X = %-8s expected 0x%02X  %s"
                  % (addr, hx(v), RESET[addr], "OK" if good else "MISMATCH"))
        print()
        if allok:
            print("RESET COMPLETE and verified.")
        else:
            print("RESET INCOMPLETE: some cells did not read back as expected.")
            print("Original values are in %s if you need to restore them." % bpath)
        return 0 if allok else 3
    except D4Error as exc:
        print("D4 ERROR: %s" % exc)
        return 1
    finally:
        d.close()


if __name__ == "__main__":
    sys.exit(main())
