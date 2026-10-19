"""Binary UART frames shared with rtl/serial_link.v; little-endian integers."""
from dataclasses import dataclass
import struct


def crc8(data: bytes) -> int:
    """CRC-8/SMBUS (check value for b'123456789' is 0xF4)."""
    crc = 0
    for value in data:
        crc ^= value
        for _ in range(8):
            crc = ((crc << 1) ^ (0x07 if crc & 0x80 else 0)) & 0xFF
    return crc


def command(sequence: int, rpm: int = 0, enable: bool = False,
            clear: bool = False) -> bytes:
    if not isinstance(rpm, int) or not 0 <= rpm <= 600:
        raise ValueError("Target must be an integer from 0 to 600 RPM")
    if clear and (enable or rpm):
        raise ValueError("Clear requires a disabled, zero-speed command")
    payload = struct.pack("<BBHB", 0xA5, sequence & 255, rpm,
                          int(enable) | (int(clear) << 1))
    return payload + bytes([crc8(payload)])


@dataclass(frozen=True)
class Telemetry:
    sequence: int
    rpm_x10: int
    target_rpm: int
    duty_permille: int
    status: int
    faults: int
    invalid_count: int

    @property
    def rpm(self):
        return self.rpm_x10 / 10

    @property
    def active(self):
        return bool(self.status & 1)

    @property
    def armed(self):
        return bool(self.status & 2)

    def pack(self) -> bytes:
        payload = struct.pack("<BBhHHBBB", 0x5A, self.sequence & 255,
                              self.rpm_x10, self.target_rpm,
                              self.duty_permille, self.status,
                              self.faults, self.invalid_count)
        return payload + bytes([crc8(payload)])


class TelemetryParser:
    """Retains partial frames and rescans one byte after any bad CRC."""
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes) -> list[Telemetry]:
        self.buffer.extend(data)
        packets = []
        while self.buffer:
            if self.buffer[0] != 0x5A:
                del self.buffer[0]
            elif len(self.buffer) < 12:
                break
            elif crc8(self.buffer[:11]) != self.buffer[11]:
                del self.buffer[0]
            else:
                values = struct.unpack("<BBhHHBBB", self.buffer[:11])
                packets.append(Telemetry(*values[1:]))
                del self.buffer[:12]
        return packets


FAULT_NAMES = {1: "driver", 2: "heartbeat timeout", 4: "no encoder motion",
               8: "invalid quadrature", 16: "reverse motion"}


def fault_description(mask: int) -> str:
    return ", ".join(name for bit, name in FAULT_NAMES.items() if mask & bit) or "none"
