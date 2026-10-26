# Unicorn Horn: WLED controller

ESP32-C3 (SuperMini-style, native USB) driving 16 × WS2812B up the front of the horn, over the fold and down the back. Pixel 0 is at the bottom of the front; pixel 15 is at the bottom of the back.

| | |
|---|---|
| Firmware | **WLED 16.0.1** "Niji", build `2606300`, asset `WLED_16.0.1_ESP32-C3.bin` (DIO) |
| Chip | ESP32-C3 (QFN32) rev v0.4, 4 MB embedded flash (XMC), USB-Serial/JTAG |
| MAC | `a0:85:e3:49:f2:30` |
| Home network | `192.168.1.49` (DHCP) · **http://unicorn.local** · name "Unicorn Horn" |
| Away from home | Joins nothing → opens AP **`Unicorn-Horn`** → browse to **http://4.3.2.1** |

## Wiring

| Strip | C3 |
|---|---|
| DIN | GPIO10 |
| 5V | 5V (VBUS) |
| GND | GND |
| *(button, not fitted yet)* | GPIO3 → pushbutton → GND (internal pull-up) |

Colour order is GRB, confirmed on the hardware. All 16 pixels light in physical order. LED 0 showed no 3.3 V data-level problem.

## Firmware image

Layout from the WLED web installer's `CHIP_CONFIG['ESP32-C3']` in `app.js` ([wled/WLED-WebInstaller@5fa2889](https://github.com/wled/WLED-WebInstaller/blob/5fa2889dc8b163415f0a994142a29738f0218931/app.js)). The repo has no static manifest file; the installer builds the manifest at runtime from that config. The default C3 flash mode is DIO.

| Offset | File | SHA-256 |
|---|---|---|
| `0x0` | `firmware/bootloader_c3_4m.bin` | `c32b14040f89947cf31dcc149f1ca1b618808e81cb9dcbdc717728b76518b10e` |
| `0x8000` | `firmware/partitions_c3_4m.bin` | `ab7a19ebb0ea19e684687802f2d8f199225a270c6b7dd72d73e8a8876f382e73` |
| `0x10000` | `firmware/WLED_16.0.1_ESP32-C3.bin` | `58960172b3fbb16106a90250d0cc4a7f4735a9a083f751a64bc2019ddb5a254c` (matches GitHub's release digest) |

`bootloader_c3_4m.bin` is the installer's canonical `bootloader_c3_8m.bin` (`0d677b33…c7c14`) re-flagged for 4 MB flash by `tools/reflag_bootloader.py`. That script is a port of `patchBootloaderFlashSize()`: it patches the header nibble and recomputes the SHA-256. Its output is byte-identical to esptool's own `--flash-size 4MB` patch. The 8 MB and 16 MB partition tables are kept in `firmware/` for reference.

## Reflashing from scratch

esptool 5.x (hyphenated commands). **This board needs the BOOT button.** USB resets misbehave on this Mac and board:
- esptool can't reset a running WLED into download mode.
- Any reset sent over USB, including esptool's `--after hard-reset`, lands in download mode instead of booting.

So:

1. Unplug, **hold BOOT, plug in, release**.
2. Flash:
   ```
   P=/dev/cu.usbmodem1101
   esptool --chip esp32c3 --port $P --before no-reset --after no-reset erase-flash
   esptool --chip esp32c3 --port $P --before no-reset --after no-reset --baud 921600 write-flash \
     --flash-mode keep --flash-freq keep --flash-size keep \
     0x0 firmware/bootloader_c3_4m.bin 0x8000 firmware/partitions_c3_4m.bin 0x10000 firmware/WLED_16.0.1_ESP32-C3.bin
   ```
3. **Power-cycle** the board (unplug and replug, no BOOT).
4. Join Wi-Fi over Improv Serial. It prompts for the SSID, and for the password with `getpass`, which is never echoed or stored:
   ```
   uv venv .venv && uv pip install --python .venv/bin/python pyserial   # first time only
   .venv/bin/python -I tools/improv.py /dev/cu.usbmodem1101 provision
   ```
5. `./restore.sh <ip>`

## Restore

```
./restore.sh 192.168.1.49
```

It uploads `backup/palette0.json` and `palette1.json`, then `backup/presets.json`, then `backup/cfg.json` (which makes WLED reboot). It then waits for the device and checks presets, name, mDNS name, LED output, limiter, buttons, boot defaults, AP SSID, both custom palettes and the LED count.

**Tested** on 2026-10-26:
- **End to end:** erase → flash → Improv → restore, with all checks passing and the device booting into preset 1, on, at 35 %. That run used the original 5-preset set.
- **After adding presets 6–7 and `palette1.json`:** re-run against the configured device, all checks passing. This exercises every upload and check but not a blank device again.

The device must already be on the network. Passwords live in `wsec.json` on the device, which is neither backed up nor touched by the restore. The repo is public, so the home Wi-Fi SSID is blanked in `backup/cfg.json`; `restore.sh` copies the network block the device is currently using (`nw` from `/json/cfg`, which never includes passwords) into the cfg before uploading it.

## Configuration (changes from WLED defaults)

| Setting | Value |
|---|---|
| LED output | 1 × WS281x (type 22), GPIO10, 16 LEDs, GRB (order 0) |
| Brightness limiter | On: 500 mA max, 55 mA per LED |
| Power-up | On, preset 1, brightness 89 (35 %) |
| Button 0 | **Type None on GPIO9** (see below) |
| Button 1 | Pushbutton on GPIO3, pull-up. Short press → preset 10 (cycle 1–7), long press → preset 11 (Off), double press → preset 5 |
| AP SSID | `Unicorn-Horn` (opens when no Wi-Fi connection after boot) |
| Wi-Fi TX power | 8.5 dBm (`txpwr 34`), the build default from `LOLIN_WIFI_FIX`; left unchanged |

`config/cfg_patch.json` is the exact JSON that was POSTed to `/json/cfg`.

### Why button 0 sits on GPIO9

From the WLED 16.0.1 source:
- **`button.cpp`:** button **0** has extra behaviour when released. Held for more than 5 s it opens the AP; held for more than 10 s it runs `WLED_FS.format()`, a **factory reset**.
- **`cfg.cpp`:** a button entry with `pin -1` is **dropped from the list**, so the following buttons move up one index. Setting button 0 to "no pin" would make GPIO3 *become* button 0 and inherit the factory reset.

Button 0 is therefore type None (skipped by the button loop) on GPIO9. GPIO9 is the board's BOOT strap and has no other use. GPIO20/21 are avoided because claiming WLED's hardware RX pin disables serial RX, and with it Improv.

### Long press = Off, not toggle

On buttons other than 0, WLED fires the long-press action at 600 ms and then **repeats it every 400 ms** while the button is held. A toggle would flicker and finish in an arbitrary state. Preset 11 is plain Off, so the repeat does no harm, and a short press brings the light back.

## Presets

Effects and palettes are chosen **by name** against the device's live `/json/eff` and `/json/pal` lists by `tools/build_presets.py`. IDs are resolved at build time; the values below are for 16.0.1.

| ID | Name | Effect | Palette | Notes |
|---|---|---|---|---|
| 1 | Rainbow climb | Palette (65) | Unicorn (200) | Mirror on: rises up both faces together. Speed 120, size 200 |
| 2 | Fairy dust | Twinklefox (80) | Unicorn (200) | Speed 70, twinkle rate 110 |
| 3 | Pink & lilac breathe | Breathe (2) | \* Color 1 (2) | `#f6a8d4` over `#d4b4f4`, speed 60 |
| 4 | Over the top | Meteor (76) | Unicorn (200) | Mirror off: up the front, over the fold, down the back. Gradient + smooth, speed 150, trail 150 |
| 5 | Unicorn power | Glitter (87) | Royal (199) | Brightness 255 (limiter caps the current), speed 230, glitter 255 |
| 6 | Royal waves | Colorwaves (67) | Royal (199) | Mirror on, brightness 255, speed 200 |
| 7 | Royal fireworks | Fireworks Starburst (89) | Royal (199) | Brightness 255, chance 200, fragments 180 |
| 10 | Cycle | `{"ps":"1~7~"}` | | Steps 1→7 and wraps. **Only works from a button** (see below) |
| 11 | Off | `{"on":false}` | | Long-press action |

Presets 1–4 run at brightness 89 (35 %); presets 5–7 at 255.

**`presets.json` must stay compact** (no whitespace). WLED saves a preset by editing the file in place (`file.cpp`, `writeObjectToFile`): it finds `"<id>":` and counts braces from the very next byte. A space after the colon makes it treat the old preset as 1 byte long, leave the old body behind and corrupt the file on the first save from the UI. `build_presets.py` writes compact JSON for this reason; don't hand-edit or pretty-print the file before uploading. Saving in place, adding and deleting presets were tested via `psave`/`pdel`.

**If you change presets in the web UI,** pull them back into the repo with `curl -4 http://unicorn.local/presets.json -o backup/presets.json`. Otherwise `restore.sh` will put the old versions back. Fire 2012 on the Royal palette (speed 70, spark rate 190, mirror on) was the runner-up if an eighth preset is wanted.

**Custom palettes.** WLED 16 custom palettes have no name field, so the UI shows them as custom palettes, not by these names:

| File | Name here | ID | Stops |
|---|---|---|---|
| `palette0.json` | Unicorn | 200 | `#f6a8d4` @0 → `#d4b4f4` @64 → `#a8d8f6` @128 → `#c8f2e6` @192 → `#f6a8d4` @255 |
| `palette1.json` | Royal | 199 | `#2a0055` @0 → `#7b00c8` @48 → `#ffb300` @96 → `#ff8c00` @144 → `#7b00c8` @192 → `#2a0055` @255 |

**Preset 10 in the app:** WLED (`presets.cpp`) only honours a `"ps":"1~7~"` inside a preset when a button calls it, which avoids recursion. Picking preset 10 in the app or web UI does nothing; pick presets 1–7 directly instead. The cycle path itself was tested via `{"ps":"1~7~"}` on `/json/state`, which gave 5→6→7→1→2.

## Phone control

- **At home:** open `http://unicorn.local` (or `192.168.1.49`) in Safari, then Share → *Add to Home Screen*. Any WLED app on the same network also works.
- **Out trick-or-treating:** the horn can't reach home Wi-Fi, so after boot it opens the **`Unicorn-Horn`** AP. Join it from the phone and open **http://4.3.2.1**.

## Files

| Path | What |
|---|---|
| `firmware/` | Flashed images (see table above) plus the 8 MB/16 MB variants |
| `backup/` | `cfg.json`, `presets.json`, `palette0.json`, `palette1.json` pulled from the device. No passwords; `pskl` (password-length) fields removed; Wi-Fi SSID blanked |
| `config/` | Source for the device changes: `cfg_patch.json`, `palette0.json`, `palette1.json`, generated `presets.json` |
| `restore.sh` | Push `backup/` onto a freshly flashed WLED and verify |
| `tools/improv.py` | Improv Serial client: `info`, and `provision` (getpass) |
| `tools/build_presets.py` | Builds presets from effect/palette names; `--upload` |
| `tools/led_test.py` | Colour-order (`colours`) and single-pixel `chase` tests |
| `tools/reflag_bootloader.py` | Re-flags a bootloader image's flash size |

## To do

- [ ] **Set the AP password** in the web UI: Config → WiFi Setup → AP password. Until then it's WLED's default.
- [ ] Fit the GPIO3 button and test short, double and long press. These are configured but untested because the button isn't wired yet.
- [ ] Consider an OTA lock or settings PIN if the horn will be on shared networks.
