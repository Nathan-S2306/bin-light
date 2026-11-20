# Bin Light

A Govee smart bulb that lights up in the colour of the bin that needs to go out, so nobody forgets bin night. It works for any Kirklees (Huddersfield area) address. You don't need any wiring or extra hardware, and you don't need to leave a computer running.

## What the colours mean

The bulb comes on at **5pm the evening before collection** and goes off at **midday on collection day**.

| Bin | Bulb |
|---|---|
| Grey (general waste) | White |
| Green (recycling) | Green |
| Brown (garden waste) | Orange |
| Two bins on the same day | Swaps between the two colours every few minutes |

At all other times the bulb is **off**. Brightness is 60%, dropping to 15% between 11pm and 7am.

Collection dates come from the Kirklees "Manage your bins" service twice a day, so Christmas and bank holiday changes come through automatically. If that service ever stops answering, the light keeps going by assuming each bin stays on its fortnightly cycle.

## What to buy

**One Govee Wi-Fi colour bulb (about £10–£15).** Make sure it says **Wi-Fi**: Bluetooth-only Govee bulbs won't work. Pick a standard screw (E27) or bayonet (B22) fitting to match the lamp, and put it somewhere that gets walked past in the evening.

## How it works

```
Twice a day:      fetch_bins.py -> asks Kirklees for the next bin dates -> docs/bins.json
Every 4 minutes:  bin_bulb.py   -> reads bins.json -> sets the bulb colour (only when it needs to change)
```

Both run free on GitHub Actions. Because `bin_bulb.py` only sends a command when the colour should change, turning the bulb off in the Govee app sticks until the next change.

---

## Setup (about 15 minutes)

### 1. Set up the bulb
Screw it in, install the **Govee Home** app, and add the bulb to your Wi-Fi. Check you can change its colour from the app.

### 2. Get a Govee API key
In the Govee Home app, go to Profile (person icon) → Settings (cog) → **Apply for API Key**. Fill in the short form (reason: "home automation"), and the key arrives by email.

### 3. Find the property's UPRN
The UPRN (Unique Property Reference Number) is how the council identifies the address. Search the postcode on findmyaddress.co.uk or uprn.uk and pick the address.

### 4. Add the secrets
In the repo, go to **Settings → Secrets and variables → Actions → New repository secret**, and add:
- `GOVEE_API_KEY`: the key from step 2
- `BIN_UPRN`: the number from step 3

Secrets stay private even though the repo is public, so the address isn't visible to anyone.

### 5. Start it
1. Go to **Actions** and enable workflows if asked.
2. Open **Update bins → Run workflow** and wait for the green tick. The log lists the next grey, green and brown dates.
3. Open **Update light → Run workflow**, tick "force", and run it. The bulb should change within a few seconds: it switches off if no bin is due, or shows a colour if one is.

That's it. From now on it runs by itself.

---

## Optional extras

**More than one Govee device on the account:** by default the system uses the first colour bulb. To choose a specific one, open the latest **Update light** run log. It lists your devices with their `sku` and `device` values. Add those as the secrets `GOVEE_SKU` and `GOVEE_DEVICE`.

**Timings and colours:** these are set at the top of `bin_bulb.py` (`SHOW_FROM`, `SHOW_UNTIL`, the `LOOKS` colour table, and the brightness levels).

---

## Troubleshooting

- **Bulb never changes:** open Actions → Update light → the latest run, and read the log. It prints what it decided ("green (due: green, brown)") and any error from Govee. The usual causes are a mistyped API key or a Bluetooth-only bulb.
- **No bin dates:** check the latest **Update bins** run. It prints what the council sent back. An empty reply usually means the UPRN is wrong.
- **Changes arrive a little late:** GitHub sometimes runs scheduled jobs a few minutes behind. That's fine for a bin reminder.
- **Workflows stopped after a couple of months:** GitHub pauses scheduled jobs in repos with no activity for 60 days. The twice-daily bin updates normally count as activity, but if it ever happens, click "Enable workflow" in Actions.
