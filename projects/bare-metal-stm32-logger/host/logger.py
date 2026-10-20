"""Read a NUCLEO virtual COM port or replay committed synthetic frames."""
import argparse
import csv
import sys
from pathlib import Path
from protocol import Message, Parser, decode, encode

def main():
    p = argparse.ArgumentParser(description=__doc__)
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument('--port')
    source.add_argument('--replay', type=Path)
    p.add_argument('--out', type=Path, default=Path('build/capture.csv'))
    p.add_argument('--seconds', type=float, default=10)
    p.add_argument('--period-ms', type=int, choices=range(20,2001), metavar='20..2000')
    p.add_argument('--vref-mv', type=int, choices=range(3000,3601), metavar='3000..3600')
    args = p.parse_args()
    if args.seconds <= 0:
        p.error('--seconds must be positive')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    def capture(stream, frames):
        writer = csv.writer(stream)
        writer.writerow(['sequence','tick_ms','adc0','adc1','input0_v','input1_v','vref_mv','dropped','flags'])
        for m in frames:
            if m.kind == 0x80:
                print(f'ACK sequence={m.sequence} command={m.b:#x} status={m.a}', file=sys.stderr)
            elif m.kind == 1:
                writer.writerow([m.sequence,m.tick,m.a,m.b,*m.input_volts(),m.vref,m.dropped,m.flags])
    if args.replay:
        with args.out.open('w',newline='') as f:
            capture(f, (decode(bytes.fromhex(line)) for line in args.replay.read_text().splitlines() if line))
    else:
        import time
        try:
            import serial
        except ImportError:
            p.error('Hardware capture requires: python -m pip install pyserial==3.5')
        def frames(port):
            parser=Parser(); deadline=time.monotonic()+args.seconds
            for sequence,(kind,arg) in enumerate([(0x10,args.period_ms),(0x11,args.vref_mv),(0x12,0)]):
                if arg is not None: port.write(encode(Message(kind=kind,sequence=sequence,a=arg)))
            while time.monotonic()<deadline:
                yield from parser.feed(port.read(256))
        with serial.Serial(args.port,115200,timeout=.1) as port, args.out.open('w',newline='') as f:
            capture(f,frames(port))
    print(args.out)
if __name__ == '__main__':
    main()
