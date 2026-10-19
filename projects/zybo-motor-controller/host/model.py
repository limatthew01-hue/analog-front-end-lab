"""Fixed-point controller reference and explicitly assumed mechanical model.

The mechanical parameters are illustrative, not fitted to a physical motor.
The real motor's electrical dynamics, friction, heating, and switching are absent.
"""
from dataclasses import dataclass
import math

CPR_MILLI = 358331
CONTROL_HZ = 50


def trunc_div(numerator: int, denominator: int) -> int:
    """Signed integer division toward zero, as in Verilog."""
    return (1 if numerator >= 0 else -1) * (abs(numerator) // denominator)


class PIController:
    def __init__(self, kp_q8=256, ki_step_q8=24, max_duty=900):
        self.kp_q8 = kp_q8
        self.ki_step_q8 = ki_step_q8
        self.max_duty = max_duty
        self.integral = 0

    def update(self, target_rpm: int, measured_rpm_x10: int, enable=True) -> int:
        if not enable or target_rpm == 0:
            self.integral = 0
            return 0
        error = target_rpm * 10 - measured_rpm_x10
        candidate_i = self.integral + error * self.ki_step_q8
        candidate_u = error * self.kp_q8 + candidate_i
        if not ((candidate_u > self.max_duty * 2560 and error > 0) or
                (candidate_u < 0 and error < 0)):
            self.integral = candidate_i
        result = trunc_div(candidate_u, 2560)
        return max(0, min(self.max_duty, result))


class SpeedEstimator:
    def __init__(self, cpr_milli=CPR_MILLI, control_hz=CONTROL_HZ):
        self.cpr_milli = cpr_milli
        self.control_hz = control_hz
        self.rpm_x10 = 0

    def update(self, counts: int) -> int:
        raw = trunc_div(counts * 600000 * self.control_hz, self.cpr_milli)
        self.rpm_x10 += trunc_div(raw - self.rpm_x10, 4)
        self.rpm_x10 = max(-32768, min(32767, self.rpm_x10))
        return self.rpm_x10


@dataclass
class MotorPlant:
    no_load_rpm: float = 720.0
    tau_s: float = 0.12
    rpm: float = 0.0
    position_counts: float = 0.0

    def advance(self, duty_permille: int, dt: float, load_rpm=0.0) -> int:
        equilibrium = max(0.0, self.no_load_rpm * duty_permille / 1000 - load_rpm)
        decay = math.exp(-dt / self.tau_s)
        old = self.rpm
        self.rpm = equilibrium + (old - equilibrium) * decay
        integral_rpm_s = equilibrium * dt + (old-equilibrium) * self.tau_s * (1-decay)
        previous = int(self.position_counts)
        self.position_counts += integral_rpm_s * CPR_MILLI / 1000 / 60
        return int(self.position_counts) - previous


class ClosedLoop:
    def __init__(self, no_load_rpm=720.0, tau_s=0.12):
        self.controller = PIController()
        self.estimator = SpeedEstimator()
        self.plant = MotorPlant(no_load_rpm=no_load_rpm, tau_s=tau_s)
        self.duty = 0

    def step(self, target: int, load_rpm=0.0, enable=True):
        # The RTL PI consumes the previous estimate on each control edge.
        measured_before = self.estimator.rpm_x10
        counts = self.plant.advance(self.duty, 1 / CONTROL_HZ, load_rpm)
        self.estimator.update(counts)
        self.duty = self.controller.update(target, measured_before, enable)
        return self.plant.rpm, self.estimator.rpm_x10, self.duty
