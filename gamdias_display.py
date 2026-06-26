#!/usr/bin/env python3
"""
Gamdias Aura FL240 (CHIONE STN) — Linux display controller
Reverse-engineered from ZEUS CAST 1.4.3.39 / HIDB533 class

Protocol: HID Feature Reports, 9 bytes via IOWR ioctls
  [0] = 0x00  report ID (implicit, no-ID device)
  [1] = cmd   0x30=init  0x60=lights  0x61=fan ring  0x62=pump ring  0x63=temp
  [2..7] = payload
  [8] = SCE checksum = (0xFF - sum(bytes[0..7])) & 0xFF
"""

import os, fcntl, array, time, glob, logging, signal, sys
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
DEVICE          = "/dev/hidraw3"
INTERVAL        = 2.0       # seconds between updates
FAN_MAX_RPM     = 1800      # used to compute fan ring %
PUMP_MAX_RPM    = 2300      # used to compute pump ring %
LOG_LEVEL       = logging.INFO

# ── HID ioctls ────────────────────────────────────────────────────────────────
# Both use _IOWR ('H', nr, 9):  direction = READ|WRITE = 0xC0
HIDIOCSFEATURE_9 = 0xC0094806
HIDIOCGFEATURE_9 = 0xC0094807

# ── 7-segment digit encoding (NoToBy from ChioneVAstn.cs) ────────────────────
SEG = {0:0xF7, 1:0x91, 2:0xEB, 3:0xBB, 4:0x9D,
       5:0xBE, 6:0xFE, 7:0x97, 8:0xFF, 9:0xBF, None:0x88}

# ── Helpers ───────────────────────────────────────────────────────────────────

def sce(data: bytearray) -> int:
    return (0xFF - sum(data[:8])) & 0xFF

def feature_set(fd: int, data: bytearray):
    data[8] = sce(data)
    buf = array.array('B', data)
    fcntl.ioctl(fd, HIDIOCSFEATURE_9, buf)

def feature_get(fd: int, data: bytearray) -> bytes:
    data[8] = sce(data)
    buf = array.array('B', data)
    fcntl.ioctl(fd, HIDIOCGFEATURE_9, buf)
    return bytes(buf)

def up_display(pct: int) -> bytes:
    """Percentage 0-100 → 5-byte ring segment bitmask (stack/filled mode)."""
    pct = max(0, min(100, int(pct)))
    seg = pct // 5
    r = [0, 0, 0, 0, 0]
    for i in range(seg):
        bi  = i // 8
        bit = 7 - (i % 8)
        r[bi] |= 1 << bit
    return bytes(r)

# ── Device commands ───────────────────────────────────────────────────────────

def cmd_init(fd: int) -> bytes:
    """USB_30H — query firmware version."""
    buf = array.array('B', [0, 0x30, 0, 0, 0, 0, 0, 0, 0xCF])
    fcntl.ioctl(fd, HIDIOCGFEATURE_9, buf)
    return bytes(buf)

def cmd_lights(fd: int, fan=1, pump=1, white=1, blue=1, light=1):
    """USB_60H — enable/disable display sections."""
    feature_set(fd, bytearray([0, 0x60, 0, fan, pump, white, blue, light, 0]))

def cmd_fan_ring(fd: int, pct: int):
    """USB_61H — set fan RPM ring gauge (0-100 %)."""
    r = up_display(pct)
    feature_set(fd, bytearray([0, 0x61, r[0], r[1], r[2], r[3], r[4], 0, 0]))

def cmd_pump_ring(fd: int, pct: int):
    """USB_62H — set pump RPM ring gauge (0-100 %)."""
    r = up_display(pct)
    feature_set(fd, bytearray([0, 0x62, r[0], r[1], r[2], r[3], r[4], 0, 0]))

def cmd_temperature(fd: int, temp_c: float):
    """USB_63H — display CPU temperature in Celsius (XX.X format)."""
    val   = int(temp_c * 10)
    tens  = SEG.get(val // 100,      SEG[None])
    units = SEG.get((val % 100) // 10, SEG[None])
    tenth = SEG.get(val % 10,         SEG[None])
    feature_set(fd, bytearray([0, 0x63, tens, units, tenth, 1, 0, 0, 0]))

# ── Sensor reading ────────────────────────────────────────────────────────────

# SYS_FAN header mapping on IT8689E (B550M AORUS ELITE):
#   fan1 = CPU_FAN / PUMP header → pump
#   fan3 = SYS_FAN1             → radiator fan
# Adjust these if sensors are labeled differently on your board.
IT8689_PUMP_FAN = "fan1_input"
IT8689_CASE_FAN = "fan3_input"

def _hwmon_read(path: str) -> float | None:
    try:
        return float(Path(path).read_text().strip())
    except Exception:
        return None

def _it8689_path() -> str | None:
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*/"):
        try:
            if Path(hwmon + "name").read_text().strip() == "it8689":
                return hwmon
        except Exception:
            pass
    return None

def get_cpu_temp() -> float:
    for hwmon in glob.glob("/sys/class/hwmon/hwmon*/"):
        try:
            name = Path(hwmon + "name").read_text().strip()
        except Exception:
            continue
        if name in ("k10temp", "coretemp"):
            v = _hwmon_read(hwmon + "temp1_input")
            if v is not None:
                return v / 1000.0
    return 0.0

def get_fan_rpm() -> int:
    hwmon = _it8689_path()
    if hwmon:
        v = _hwmon_read(hwmon + IT8689_CASE_FAN)
        if v is not None:
            return int(v)
    # fallback: first nonzero fan on any chip
    for hw in glob.glob("/sys/class/hwmon/hwmon*/"):
        for f in sorted(glob.glob(hw + "fan*_input")):
            v = _hwmon_read(f)
            if v and v > 0:
                return int(v)
    return 0

def get_pump_rpm() -> int:
    hwmon = _it8689_path()
    if hwmon:
        v = _hwmon_read(hwmon + IT8689_PUMP_FAN)
        if v is not None:
            return int(v)
    return 0

# ── Main loop ─────────────────────────────────────────────────────────────────

log = logging.getLogger("gamdias")
_running = True

def _stop(sig, frame):
    global _running
    log.info("Sinal %s recebido, encerrando…", sig)
    _running = False

def open_device() -> int | None:
    try:
        fd = os.open(DEVICE, os.O_RDWR)
        log.info("Dispositivo aberto: %s", DEVICE)
        return fd
    except PermissionError:
        log.error("Sem permissão para %s. Adicione ao grupo 'input' ou execute como root.", DEVICE)
        return None
    except FileNotFoundError:
        return None
    except OSError as e:
        log.debug("Não foi possível abrir %s: %s", DEVICE, e)
        return None

def init_device(fd: int):
    resp = cmd_init(fd)
    log.info("Firmware: %d.%d", resp[2], resp[3])
    cmd_lights(fd)
    time.sleep(0.05)

def run_once(fd: int):
    cpu  = get_cpu_temp()
    fan  = get_fan_rpm()
    pump = get_pump_rpm()
    fpct = min(100, int(fan  / FAN_MAX_RPM  * 100)) if fan  else 0
    ppct = min(100, int(pump / PUMP_MAX_RPM * 100)) if pump else 0

    cmd_temperature(fd, cpu)
    cmd_fan_ring(fd, fpct)
    cmd_pump_ring(fd, ppct)

    log.debug("CPU %.1f°C  fan %d RPM (%d%%)  pump %d RPM (%d%%)", cpu, fan, fpct, pump, ppct)
    return cpu, fan, pump

def main():
    logging.basicConfig(
        level=LOG_LEVEL,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT,  _stop)

    log.info("Gamdias Aura FL240 — controller iniciado")

    fd   = None
    wait = 2.0  # reconnect backoff

    while _running:
        if fd is None:
            fd = open_device()
            if fd is None:
                log.warning("Aguardando dispositivo… (retry em %.0fs)", wait)
                time.sleep(wait)
                wait = min(wait * 2, 30)
                continue
            wait = 2.0
            try:
                init_device(fd)
            except OSError as e:
                log.error("Falha no init: %s", e)
                os.close(fd); fd = None
                continue

        try:
            cpu, fan, pump = run_once(fd)
            log.info("CPU %.1f°C  fan %d RPM  pump %d RPM", cpu, fan, pump)
            time.sleep(INTERVAL)
        except OSError as e:
            log.warning("Dispositivo desconectado (%s), reconectando…", e)
            try:
                os.close(fd)
            except OSError:
                pass
            fd = None

    if fd is not None:
        try:
            os.close(fd)
        except OSError:
            pass
    log.info("Encerrado.")

if __name__ == "__main__":
    main()
