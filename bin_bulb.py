#!/usr/bin/env python3
"""
Bin Light - a Govee Wi-Fi bulb that shows which bin goes out.

Runs every few minutes on GitHub Actions. Reads docs/bins.json (made by
fetch_bins.py) and lights the bulb in the colour of the bin that's due, from
7am to 11pm on the day before collection:

    grey bin  -> white
    green bin -> green
    brown bin -> orange
    two bins on the same day -> the bulb swaps between them every few minutes

Outside that window the script leaves the bulb alone, so it can be used as
normal in the Govee app. The only command it sends is a single "off" at 11pm
when the bin colour finishes. If the council lookup stops working, it keeps going by
assuming each bin stays on its fortnightly cycle. It only talks to the bulb
when the colour should change, so turning it off in the Govee app sticks until
the next change.

Secrets / environment:
  GOVEE_API_KEY   required (request it in the Govee Home app)
  GOVEE_DEVICE    optional: the bulb's device id (auto-picks the first colour bulb if unset)
  GOVEE_SKU       optional: the bulb's model, needed only when GOVEE_DEVICE is set
"""

import datetime as dt
import json
import os
import sys
import time
import urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

UK = ZoneInfo("Europe/London")
ROOT = Path(__file__).resolve().parent
BINS_FILE = ROOT / "docs" / "bins.json"
STATE_FILE = ROOT / "docs" / "light_state.json"
API = "https://openapi.api.govee.com/router/api/v1"

SHOW_FROM = dt.time(7, 0)      # on at 7am the day before collection
SHOW_UNTIL = dt.time(23, 0)    # off at 11pm the same day
CYCLE_DAYS = 14
BRIGHTNESS = 60

LOOKS = {   # bin -> (r, g, b)
    "grey":  (255, 255, 255),
    "green": (0, 255, 40),
    "brown": (255, 90, 0),
}
ORDER = ["grey", "green", "brown"]


# ---------- deciding what to show ----------

def collection_dates(today):
    """{colour: [dates]} from bins.json, extended fortnightly if it's gone stale."""
    if not BINS_FILE.exists():
        return {}
    raw = json.loads(BINS_FILE.read_text()).get("bins", {})
    out = {}
    for colour, days in raw.items():
        dates = sorted(dt.date.fromisoformat(d) for d in days)
        if not dates:
            continue
        while dates[-1] < today:                     # lookup has stopped updating
            dates.append(dates[-1] + dt.timedelta(days=CYCLE_DAYS))
        out[colour] = dates
    return out


def due_now(now):
    """Bins whose 'put it out' window covers this moment."""
    local = now.astimezone(UK)
    due = []
    for colour, dates in collection_dates(local.date()).items():
        for d in dates:
            day_before = d - dt.timedelta(days=1)
            start = dt.datetime.combine(day_before, SHOW_FROM, tzinfo=UK)
            end = dt.datetime.combine(day_before, SHOW_UNTIL, tzinfo=UK)
            if start <= local < end:
                due.append(colour)
                break
    return sorted((c for c in due if c in LOOKS), key=ORDER.index)


def choose(due, last_shown):
    """Pick one colour; when two bins are due, take turns."""
    if not due:
        return None
    if last_shown in due:
        return due[(due.index(last_shown) + 1) % len(due)]
    return due[0]


def target_state(colour, now):
    if colour is None:
        return {"power": 0}
    return {"power": 1, "rgb": list(LOOKS[colour]), "brightness": BRIGHTNESS}


# ---------- talking to the bulb ----------

def govee(method, path, body=None):
    req = urllib.request.Request(
        API + path, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Govee-API-Key": os.environ["GOVEE_API_KEY"],
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        reply = json.load(r)
    if reply.get("code") not in (200, None):
        raise RuntimeError(f"Govee said: {reply}")
    return reply


def find_bulb():
    if os.environ.get("GOVEE_DEVICE"):
        if not os.environ.get("GOVEE_SKU"):
            sys.exit("GOVEE_DEVICE is set, so GOVEE_SKU must be set too.")
        return os.environ["GOVEE_SKU"], os.environ["GOVEE_DEVICE"]
    devices = govee("GET", "/user/devices").get("data", [])
    print("Devices on your Govee account:")
    for d in devices:
        print(f"  {d.get('deviceName')!r}  sku={d.get('sku')}  device={d.get('device')}")
    for d in devices:
        caps = {c.get("instance") for c in d.get("capabilities", [])}
        if "colorRgb" in caps and "powerSwitch" in caps:
            print(f"Using {d.get('deviceName')!r}")
            return d["sku"], d["device"]
    return None, None


def send(sku, device, ctype, instance, value):
    govee("POST", "/device/control", {
        "requestId": f"binlight-{int(time.time() * 1000)}",
        "payload": {"sku": sku, "device": device,
                    "capability": {"type": ctype, "instance": instance, "value": value}},
    })
    time.sleep(0.4)


def apply(state):
    sku, device = find_bulb()
    if not device:
        print("No colour bulb on the Govee account yet - add it in the Govee Home app. Skipping.")
        return False
    if state["power"] == 0:
        send(sku, device, "devices.capabilities.on_off", "powerSwitch", 0)
        return True
    r, g, b = state["rgb"]
    send(sku, device, "devices.capabilities.on_off", "powerSwitch", 1)
    send(sku, device, "devices.capabilities.color_setting", "colorRgb", (r << 16) + (g << 8) + b)
    send(sku, device, "devices.capabilities.range", "brightness", int(state["brightness"]))
    return True


# ---------- main ----------

def main():
    if not os.environ.get("GOVEE_API_KEY"):
        print("No GOVEE_API_KEY secret yet - skipping until the bulb is set up.")
        return
    now = dt.datetime.now(dt.timezone.utc)
    previous = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}
    due = due_now(now)
    colour = choose(due, previous.get("colour"))
    state = target_state(colour, now)
    print(f"{now.astimezone(UK):%a %d %b %H:%M} -> {colour or 'off'} "
          f"(due: {', '.join(due) or 'nothing'})  {state}")

    if state == previous.get("state") and "--force" not in sys.argv:
        print("No change; leaving the bulb alone.")
        return
    if not apply(state):
        return
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(
        {"colour": colour, "state": state,
         "changed": now.isoformat(timespec="seconds")}, indent=1))
    print("Bulb updated.")


if __name__ == "__main__":
    main()
