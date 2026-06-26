# Gamdias Aura FL240 — Linux Display Controller

A reverse-engineered Linux controller for the **Gamdias Aura FL240 (CHIONE STN)** all-in-one cooler display.

Displays real-time CPU temperature, fan RPM, and pump RPM on the built-in LCD — no Windows required.

![Display showing CPU temp and RPM rings](https://raw.githubusercontent.com/alexnogueirasilva/gamdias-aura-fl240-linux/main/assets/display-1.jpg)
![Display alternate view](https://raw.githubusercontent.com/alexnogueirasilva/gamdias-aura-fl240-linux/main/assets/display-2.jpg)

## Features

- CPU temperature on the 7-segment display
- Fan RPM ring gauge (filled arc, stack mode)
- Pump RPM ring gauge (filled arc, stack mode)
- Auto-reconnect if the device disconnects
- Runs as a systemd service (starts automatically on boot)

## Requirements

- Linux with systemd
- Python 3.10+
- The cooler connected via USB

## Installation

```bash
git clone https://github.com/alexnogueirasilva/gamdias-aura-fl240-linux.git
cd gamdias-aura-fl240-linux
sudo bash install.sh
```

The installer will:

1. Detect the HID device automatically by USB Vendor/Product ID (`1b80:b533`)
2. Copy the script to `/usr/local/lib/gamdias/`
3. Create a udev rule so the device is accessible without root
4. Add your user to the `input` group
5. Register, enable, and start the systemd service

> **Note:** Log out and back in after installation for the `input` group to take effect (not required for the service itself).

## Uninstallation

```bash
sudo bash uninstall.sh
```

## Configuration

Edit `/usr/local/lib/gamdias/gamdias_display.py` to adjust:

| Variable | Default | Description |
|---|---|---|
| `DEVICE` | `/dev/hidraw3` | HID device path (auto-set by installer) |
| `INTERVAL` | `2.0` | Seconds between display updates |
| `FAN_MAX_RPM` | `1800` | Max fan RPM for ring gauge scaling |
| `PUMP_MAX_RPM` | `2300` | Max pump RPM for ring gauge scaling |

After editing, restart the service:

```bash
sudo systemctl restart gamdias-display
```

## Checking status

```bash
# Service status
systemctl status gamdias-display

# Live logs
journalctl -u gamdias-display -f
```

## How it works

The cooler communicates via **HID Feature Reports** (9-byte packets over `ioctl`). Commands:

| Command | Description |
|---|---|
| `0x30` | Init / query firmware version |
| `0x60` | Enable display sections (fan ring, pump ring, white, blue) |
| `0x61` | Set fan RPM ring gauge (filled arc bitmask) |
| `0x62` | Set pump RPM ring gauge (filled arc bitmask) |
| `0x63` | Set temperature on 7-segment display |

Sensor data is read from the Linux `hwmon` subsystem:
- CPU temp: `k10temp` or `coretemp` driver
- Fan / pump RPM: `it8689` SuperIO chip (`IT8689E` found on B550M AORUS ELITE and similar boards)

## Compatibility

Tested on:
- **Cooler:** Gamdias Aura FL240 (CHIONE STN)
- **Motherboard:** Gigabyte B550M AORUS ELITE
- **OS:** Arch Linux (kernel 6.x)

Other boards with the `IT8689E` SuperIO chip should work. If your fan/pump sensors are on different `fan*_input` entries, adjust `IT8689_PUMP_FAN` and `IT8689_CASE_FAN` in the script.

## License

MIT
