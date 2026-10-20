"""Wire format shared with the C firmware; no serial dependency for replay."""
from dataclasses import dataclass
import struct

FRAME_BYTES = 22
@dataclass(frozen=True)
class Message:
    kind: int = 1
    sequence: int = 0
    tick: int = 0
    a: int = 0
    b: int = 0
    vref: int = 0
    dropped: int = 0
    flags: int = 0
    def input_volts(self):
        if self.kind != 1 or self.a > 4095 or self.b > 4095 or not 3000 <= self.vref <= 3600:
            raise ValueError('Not a valid ADC sample')
        return tuple(code * self.vref * 2 / (4095 * 1000) for code in (self.a, self.b))

def crc16(data):
    crc = 0xffff
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ (0x1021 if crc & 0x8000 else 0)) & 0xffff
    return crc

def encode(m):
    body = struct.pack('<2sBBHI5H', b'\xa5\x5a', 1, m.kind, m.sequence,
                       m.tick, m.a, m.b, m.vref, m.dropped, m.flags)
    return body + struct.pack('<H', crc16(body))

def decode(data):
    if len(data) != FRAME_BYTES or data[:3] != b'\xa5\x5a\x01' or crc16(data[:-2]) != int.from_bytes(data[-2:], 'little'):
        raise ValueError('Invalid frame, version or CRC')
    return Message(*struct.unpack('<BHI5H', data[3:20]))

class Parser:
    def __init__(self):
        self.buffer = bytearray()
    def feed(self, data):
        self.buffer.extend(data)
        messages = []
        while len(self.buffer) >= 2:
            if self.buffer[:2] != b'\xa5\x5a':
                del self.buffer[0]
                continue
            if len(self.buffer) < FRAME_BYTES:
                break
            try:
                message = decode(self.buffer[:FRAME_BYTES])
            except ValueError:
                del self.buffer[0]
                continue
            messages.append(message)
            del self.buffer[:FRAME_BYTES]
        return messages
