#!/usr/bin/env bash
# Restore the Unicorn Horn WLED setup onto a freshly flashed WLED 16.0.1 over HTTP.
#
#   ./restore.sh <host>        e.g. ./restore.sh 192.168.1.49   (or 4.3.2.1 via the WLED AP)
#
# The device must already be on the network (Improv: tools/improv.py PORT provision).
# Wi-Fi/AP passwords live in wsec.json on the device and are neither backed up nor touched.
# Order matters: palettes + presets first, cfg.json last (WLED reboots on cfg.json upload).
set -euo pipefail

HOST="${1:?usage: $0 <host-or-ip>}"
DIR="$(cd "$(dirname "$0")" && pwd)/backup"
CURL=(curl -4 -sS --fail --max-time 10)   # -4: WLED doesn't answer mDNS AAAA, curl would stall

wait_up() {
  for _ in $(seq 1 45); do
    "${CURL[@]}" --max-time 2 "http://$HOST/json/info" >/dev/null 2>&1 && return 0
    sleep 2
  done
  echo "device at $HOST did not respond" >&2; exit 1
}

upload() {  # $1 = file in backup/, $2 = optional source path override
  printf '  %-14s ' "$1"
  "${CURL[@]}" -F "data=@${2:-$DIR/$1};filename=/$1" "http://$HOST/upload"; echo
}

echo "Waiting for $HOST ..."
wait_up
ver=$("${CURL[@]}" "http://$HOST/json/info" | python3 -c 'import json,sys;print(json.load(sys.stdin)["ver"])')
echo "Found WLED $ver"
[ "$ver" = "16.0.1" ] || echo "WARNING: backup was taken from 16.0.1; cfg keys and effect/palette IDs may differ" >&2

# backup/cfg.json has the Wi-Fi SSID blanked (public repo). Carry over the network
# block the device is using right now (Improv-provisioned), so the restore can't
# knock it off Wi-Fi. Only SSID/IP settings come back from /json/cfg; passwords never do.
CFG_TMP=$(mktemp -t unicorn_cfg)
trap 'rm -f "$CFG_TMP"' EXIT
"${CURL[@]}" "http://$HOST/json/cfg" | python3 -c '
import json, sys
live = json.load(sys.stdin)
cfg = json.load(open(sys.argv[1]))
nw = live["nw"]
for w in nw.get("ins", []): w.pop("pskl", None)
cfg["nw"] = nw
json.dump(cfg, open(sys.argv[2], "w"), separators=(",", ":"))
' "$DIR/cfg.json" "$CFG_TMP"

echo "Uploading:"
upload palette0.json     # Unicorn (custom palette ID 200 on 16.0.1)
upload palette1.json     # Royal   (custom palette ID 199)
upload presets.json
upload cfg.json "$CFG_TMP"   # triggers reboot

sleep 3
echo "Waiting for reboot ..."
wait_up

echo "Verifying:"
"${CURL[@]}" "http://$HOST/presets.json" > /tmp/unicorn_presets_check.$$
"${CURL[@]}" "http://$HOST/json/info" > /tmp/unicorn_info_check.$$
"${CURL[@]}" "http://$HOST/json/cfg" > /tmp/unicorn_cfg_check.$$
set +e
python3 - "$DIR" /tmp/unicorn_presets_check.$$ /tmp/unicorn_info_check.$$ /tmp/unicorn_cfg_check.$$ <<'EOF'
import json, sys
d, pfile, ifile, cfile = sys.argv[1:]
want_p = json.load(open(f"{d}/presets.json")); got_p = json.load(open(pfile))
i = json.load(open(ifile)); c = json.load(open(cfile)); want_c = json.load(open(f"{d}/cfg.json"))
checks = {
    "presets.json identical": want_p == got_p,
    "name": c["id"]["name"] == want_c["id"]["name"],
    "mdns": c["id"]["mdns"] == want_c["id"]["mdns"],
    "LED outputs": c["hw"]["led"]["ins"] == want_c["hw"]["led"]["ins"],
    "limiter": c["hw"]["led"]["maxpwr"] == want_c["hw"]["led"]["maxpwr"],
    "buttons": c["hw"]["btn"]["ins"] == want_c["hw"]["btn"]["ins"],
    "boot defaults": c["def"] == want_c["def"],
    "AP SSID": c["ap"]["ssid"] == want_c["ap"]["ssid"],
    "custom palettes loaded (2)": i.get("cpalcount", 0) >= 2,
    "LED count": i["leds"]["count"] == want_c["hw"]["led"]["total"],
}
for k, ok in checks.items(): print(f"  {'OK  ' if ok else 'FAIL'} {k}")
sys.exit(0 if all(checks.values()) else 1)
EOF
rc=$?
rm -f /tmp/unicorn_*_check.$$
[ $rc -eq 0 ] && echo "Restore complete." || { echo "Restore verification FAILED" >&2; exit 1; }
