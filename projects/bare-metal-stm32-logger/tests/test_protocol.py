import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
from protocol import Message,Parser,crc16,decode,encode

class ProtocolTests(unittest.TestCase):
    def test_crc_check_value(self):
        self.assertEqual(crc16(b'123456789'),0x29b1)
    def test_c_golden_vector(self):
        m=Message(1,65535,0xfedcba98,4095,1234,3300,65535,0x2ff)
        vector=bytes.fromhex(Path('build/c-vector.hex').read_text())
        self.assertEqual(encode(m),vector)
        self.assertEqual(decode(vector),m)
    def test_all_single_bit_errors(self):
        b=encode(Message(vref=3300))
        for pos in range(22):
            for bit in range(8):
                x=bytearray(b); x[pos]^=1<<bit
                with self.assertRaises(ValueError): decode(x)
    def test_stream_resynchronizes(self):
        m=Message(a=100,b=1000,vref=3300); b=encode(m)
        stream=b'junk'+b[:11]+b+b'\xa5\xa5'+b
        parser=Parser(); found=[]
        for byte in stream: found.extend(parser.feed(bytes([byte])))
        self.assertEqual(found,[m,m])
    def test_voltage_conversion(self):
        self.assertEqual(Message(a=0,b=4095,vref=3300).input_volts(),(0,6.6))
        self.assertAlmostEqual(Message(a=2048,b=0,vref=3300).input_volts()[0],3.3008058608)
    def test_invalid_input(self):
        for m in [Message(kind=0x80,vref=3300),Message(a=4096,vref=3300),Message(vref=0)]:
            with self.assertRaises(ValueError): m.input_volts()
        with self.assertRaises(ValueError): decode(b'')

if __name__=='__main__': unittest.main()
