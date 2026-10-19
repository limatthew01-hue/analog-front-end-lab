import unittest

from host.model import ClosedLoop, MotorPlant, PIController, SpeedEstimator, trunc_div
from host.protocol import Telemetry, TelemetryParser, command, crc8


class ProtocolTests(unittest.TestCase):
    def test_crc_standard_check(self):
        self.assertEqual(crc8(b"123456789"), 0xF4)

    def test_command_fields(self):
        frame = command(257, 300, True)
        self.assertEqual(frame[:5], bytes([0xA5,1,44,1,1]))
        self.assertEqual(frame[5], crc8(frame[:5]))

    def test_target_bounds(self):
        for rpm in (-1, 601, 1.5):
            with self.assertRaises(ValueError):
                command(0,rpm)

    def test_clear_is_stop_only(self):
        for rpm, enable in ((1,False),(0,True)):
            with self.assertRaises(ValueError):
                command(0,rpm,enable,True)

    def test_fragmented_telemetry(self):
        packet = Telemetry(4,-123,200,450,3,16,7)
        raw = packet.pack()
        for split in range(len(raw)+1):
            parser = TelemetryParser()
            found = parser.feed(raw[:split])+parser.feed(raw[split:])
            self.assertEqual(found,[packet])

    def test_single_bit_corruption_rejected(self):
        raw = Telemetry(90,3000,300,420,7,0,0).pack()
        for bit in range(96):
            damaged = bytearray(raw)
            damaged[bit//8] ^= 1 << (bit%8)
            self.assertEqual(TelemetryParser().feed(damaged),[])

    def test_resynchronizes_after_noise(self):
        packet = Telemetry(0,0,0,0,0,0,0)
        broken = bytearray(packet.pack()); broken[3] ^= 1
        parser = TelemetryParser()
        self.assertEqual(parser.feed(b"noise\x5a"+broken+packet.pack()*2),[packet,packet])

    def test_signed_rpm_and_status(self):
        packet = Telemetry(255,-32768,600,900,3,31,255)
        decoded = TelemetryParser().feed(packet.pack())[0]
        self.assertEqual(decoded.rpm,-3276.8)
        self.assertTrue(decoded.active and decoded.armed)


class ControllerTests(unittest.TestCase):
    def test_division_matches_signed_hdl(self):
        self.assertEqual(trunc_div(-7,4),-1)
        self.assertEqual(trunc_div(7,4),1)

    def test_known_first_control_step(self):
        # 100 RPM error: P=100, first I=9.375 -> integer output 109.
        self.assertEqual(PIController().update(100,0),109)

    def test_disabled_and_zero_clear_integrator(self):
        controller = PIController()
        for _ in range(50):
            controller.update(100,0)
        self.assertGreater(controller.integral,0)
        self.assertEqual(controller.update(100,0,False),0)
        self.assertEqual(controller.integral,0)
        controller.update(100,0)
        self.assertEqual(controller.update(0,1000),0)
        self.assertEqual(controller.integral,0)

    def test_anti_windup_bounds_and_recovery(self):
        controller = PIController()
        for _ in range(1000):
            self.assertLessEqual(controller.update(600,0),900)
        before = controller.integral
        for _ in range(100):
            self.assertEqual(controller.update(600,0),900)
        self.assertEqual(before,controller.integral)
        self.assertLess(controller.update(100,6000),900)

    def test_output_never_negative(self):
        self.assertEqual(PIController().update(100,5000),0)

    def test_encoder_conversion_and_filter(self):
        estimator = SpeedEstimator(cpr_milli=600000, control_hz=50)
        self.assertEqual(estimator.update(20),250)  # 20 counts/20 ms = 100 RPM.
        for _ in range(60):
            estimator.update(20)
        self.assertLess(abs(estimator.rpm_x10-1000),4)

    def test_negative_encoder_speed(self):
        self.assertEqual(SpeedEstimator(600000).update(-20),-250)

    def test_plant_matches_analytic_solution(self):
        import math
        motor = MotorPlant()
        motor.advance(500,0.12)
        self.assertAlmostEqual(motor.rpm,360*(1-math.exp(-1)),places=10)

    def test_motor_coasts_after_stop(self):
        motor = MotorPlant(rpm=300)
        motor.advance(0,0.1)
        self.assertGreater(motor.rpm,0)
        self.assertLess(motor.rpm,300)

    def test_closed_loop_tracks_and_rejects_load(self):
        loop = ClosedLoop()
        for _ in range(200):
            speed,_,duty = loop.step(300)
        self.assertLess(abs(speed-300),3)
        before = duty
        for _ in range(200):
            speed,_,duty = loop.step(300,load_rpm=90)
        self.assertLess(abs(speed-300),3)
        self.assertGreater(duty,before)

    def test_unreachable_target_remains_bounded(self):
        loop = ClosedLoop(no_load_rpm=400)
        for _ in range(300):
            _,_,duty = loop.step(600)
            self.assertLessEqual(duty,900)
        self.assertLessEqual(loop.plant.rpm,360.001)


if __name__ == "__main__":
    unittest.main()
