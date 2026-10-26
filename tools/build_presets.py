#!/usr/bin/env python3
"""Build presets.json from effect/palette *names*, resolved against a live WLED device.

  build_presets.py HOST OUT.json [--upload]

Effect and palette IDs change between WLED versions, so nothing here is a hard-coded ID:
each name is looked up in the device's /json/eff and /json/pal lists. Custom palettes
("Unicorn" = palette0.json, "Royal" = palette1.json) have no on-device name in WLED 16,
so they are resolved from /json/palx by matching their first colour stop against config/.
"""
import argparse
import json
import pathlib
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDS = 16
BRI = 89  # ~35 %

# name -> preset; "fx"/"pal" are names, resolved at build time
PRESETS = {
    1: dict(n="Rainbow climb", fx="Palette", pal="Unicorn", mi=True, bri=BRI,
            sx=120, ix=200, c1=0, o1=True, o2=False, o3=True),
    2: dict(n="Fairy dust", fx="Twinklefox", pal="Unicorn", mi=False, bri=BRI,
            sx=70, ix=110),
    3: dict(n="Pink & lilac breathe", fx="Breathe", pal="* Color 1", mi=False, bri=BRI,
            sx=60, col=[[0xF6, 0xA8, 0xD4], [0xD4, 0xB4, 0xF4], [0, 0, 0]]),
    4: dict(n="Over the top", fx="Meteor", pal="Unicorn", mi=False, bri=BRI,
            sx=150, ix=150, o1=True, o3=True),
    5: dict(n="Unicorn power", fx="Glitter", pal="Royal", mi=False, bri=255,
            sx=230, ix=255, col=[[0, 0, 0], [0, 0, 0], [255, 255, 255]]),
    6: dict(n="Royal waves", fx="Colorwaves", pal="Royal", mi=True, bri=255,
            sx=200, ix=128),
    7: dict(n="Royal fireworks", fx="Fireworks Starburst", pal="Royal", mi=False, bri=255,
            sx=200, ix=180, col=[[0, 0, 0], [0, 0, 0], [0, 0, 0]]),
}
API_PRESETS = {
    10: {"n": "Cycle", "ps": "1~7~"},  # only honoured when called from a button (presets.cpp)
    11: {"n": "Off", "on": False},     # long press: idempotent, safe under WLED's 400 ms long-press repeat
}


def get(host, path):
    return json.load(urllib.request.urlopen(f"http://{host}{path}", timeout=10))


CUSTOM_PALETTES = {"Unicorn": "palette0.json", "Royal": "palette1.json"}


def custom_palette_id(host, filename):
    want = json.loads((ROOT / "config" / filename).read_text())["palette"][1].lower()
    rgb = [int(want[i:i + 2], 16) for i in (0, 2, 4)]
    page = 0
    while True:
        d = get(host, f"/json/palx?page={page}")
        for k, stops in d.get("p", {}).items():
            if int(k) >= 72 and isinstance(stops, list) and stops and stops[0][1:4] == rgb:
                return int(k)
        if page >= d.get("m", 0):
            raise SystemExit(f"{filename} not found on device - upload config/{filename} first")
        page += 1


def build(host):
    effects, palettes = get(host, "/json/eff"), get(host, "/json/pal")
    pal_ids = {name: custom_palette_id(host, f) for name, f in CUSTOM_PALETTES.items()}
    out = {"0": {}}
    for pid, p in PRESETS.items():
        p = dict(p)
        fx = effects.index(p.pop("fx"))
        pal_name = p.pop("pal")
        pal = pal_ids[pal_name] if pal_name in pal_ids else palettes.index(pal_name)
        name, bri = p.pop("n"), p.pop("bri")
        seg = {"id": 0, "start": 0, "stop": LEDS, "grp": 1, "spc": 0, "of": 0, "on": True,
               "frz": False, "bri": 255, "rev": False, "fx": fx, "pal": pal, **p}
        out[str(pid)] = {"n": name, "on": True, "bri": bri, "transition": 7, "mainseg": 0, "seg": [seg]}
    for pid, p in API_PRESETS.items():
        out[str(pid)] = p
    return out


def upload(host, path):
    boundary = "----unicornhorn"
    body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"data\"; filename=\"/presets.json\"\r\n"
            f"Content-Type: application/json\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(f"http://{host}/upload", data=body, method="POST",
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    print(urllib.request.urlopen(req, timeout=10).read().decode())


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("host")
    ap.add_argument("out")
    ap.add_argument("--upload", action="store_true")
    a = ap.parse_args()
    presets = build(a.host)
    out = pathlib.Path(a.out)
    # Must be compact: WLED edits presets.json in place (file.cpp writeObjectToFile) by finding
    # '"<id>":' and brace-counting from the next byte. Whitespace after the colon makes it
    # measure the old object as 1 byte, orphan its body and corrupt the file on the first UI save.
    out.write_text(json.dumps(presets, separators=(",", ":")))
    for k, v in presets.items():
        if v:
            s = v.get("seg", [{}])[0]
            print(f"{k:>3} {v['n']:22} fx={s.get('fx', '-')} pal={s.get('pal', '-')} mi={s.get('mi', '-')} "
                  f"{'ps=' + v['ps'] if 'ps' in v else ''}")
    if a.upload:
        upload(a.host, out)
