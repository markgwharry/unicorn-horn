#!/usr/bin/env python3
"""Visual LED checks over the WLED JSON API (raw pixel writes via the segment "i" key).

  led_test.py HOST colours [--cycles N]   solid red, green, blue (4 s each)
  led_test.py HOST chase   [--cycles N]   one white pixel stepping 0 -> 15 (mirror off)

"i" freezes segment 0 and writes raw pixel indices, so mirroring/grouping can't
mask a wiring fault. The segment is unfrozen and switched off when done.
"""
import argparse
import json
import time
import urllib.request


def post(host: str, state: dict) -> None:
    req = urllib.request.Request(f"http://{host}/json/state", data=json.dumps(state).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    urllib.request.urlopen(req, timeout=5).read()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("mode", choices=["colours", "chase"])
    ap.add_argument("--cycles", type=int, default=3)
    ap.add_argument("--leds", type=int, default=16)
    a = ap.parse_args()

    post(a.host, {"on": True, "bri": 128, "seg": [{"id": 0, "mi": False, "frz": False}]})
    try:
        for c in range(a.cycles):
            if a.mode == "colours":
                for name, hexcol in (("RED", "FF0000"), ("GREEN", "00FF00"), ("BLUE", "0000FF")):
                    print(f"cycle {c + 1}: {name}", flush=True)
                    post(a.host, {"seg": [{"id": 0, "i": [0, a.leds, hexcol]}]})
                    time.sleep(4)
            else:
                for px in range(a.leds):
                    print(f"cycle {c + 1}: pixel {px}", flush=True)
                    post(a.host, {"seg": [{"id": 0, "i": [0, a.leds, "000000", px, "FFFFFF"]}]})
                    time.sleep(0.8)
    finally:
        post(a.host, {"on": False, "seg": [{"id": 0, "frz": False}]})
        print("done: segment unfrozen, light off")


if __name__ == "__main__":
    main()
