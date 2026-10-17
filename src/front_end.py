"""Analyze a biased RC sensor input and ideal ADC; optionally check ngspice."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import subprocess

import numpy as np

K_B = 1.380649e-23  # Boltzmann constant, J/K.


@dataclass(frozen=True)
class Config:
    r_ohm: float = 10_000.0
    c_farad: float = 10e-9
    supply_v: float = 3.3
    bias_v: float = 1.65
    adc_bits: int = 12
    signal_peak_v: float = 0.1
    signal_hz: float = 100.0
    interference_peak_v: float = 0.04
    interference_hz: float = 20_000.0
    sample_hz: float = 200_000.0
    duration_s: float = 0.03
    measure_after_s: float = 0.01
    r_tolerance: float = 0.01
    c_tolerance: float = 0.05
    temperature_k: float = 300.0

    def __post_init__(self):
        positive = (self.r_ohm, self.c_farad, self.supply_v, self.signal_hz,
                    self.interference_hz, self.sample_hz, self.duration_s, self.temperature_k)
        if not all(np.isfinite(v) and v > 0 for v in positive):
            raise ValueError("component values, supply, frequencies, duration, and temperature must be positive and finite")
        if not isinstance(self.adc_bits, int) or not 1 <= self.adc_bits <= 24:
            raise ValueError("ADC bits must be an integer from 1 to 24")
        if not 0 <= self.bias_v <= self.supply_v:
            raise ValueError("bias must be inside the supply range")
        if not all(np.isfinite(a) and a >= 0 for a in (self.signal_peak_v, self.interference_peak_v)):
            raise ValueError("signal amplitudes must be finite and nonnegative")
        if self.sample_hz <= 2 * max(self.signal_hz, self.interference_hz):
            raise ValueError("sample rate must exceed twice the highest modeled input frequency")
        if not 0 <= self.measure_after_s < self.duration_s:
            raise ValueError("measurement start must be inside the simulation")
        if not all(0 <= t < 1 for t in (self.r_tolerance, self.c_tolerance)):
            raise ValueError("component tolerances must be in [0, 1)")

    @property
    def cutoff_hz(self):
        return 1 / (2 * np.pi * self.r_ohm * self.c_farad)

    @property
    def lsb_v(self):
        return self.supply_v / (1 << self.adc_bits)


def transfer(frequency_hz, r_ohm: float, c_farad: float, load_ohm=None):
    """Voltage transfer, including an optional resistive load to ground."""
    if r_ohm <= 0 or c_farad <= 0 or (load_ohm is not None and load_ohm <= 0):
        raise ValueError("R, C, and any load resistance must be positive")
    frequency = np.asarray(frequency_hz)
    if not np.all(np.isfinite(frequency)) or np.any(frequency < 0):
        raise ValueError("frequency must be nonnegative and finite")
    gain = 1.0 if load_ohm is None else load_ohm / (r_ohm + load_ohm)
    resistance = r_ohm if load_ohm is None else r_ohm * gain
    return gain / (1 + 2j * np.pi * frequency * resistance * c_farad)


def sine_response(time_s, amplitude_v, frequency_hz, r_ohm, c_farad):
    """Exact continuous-time RC response to a sine switched on at t=0.

    The incremental capacitor voltage starts at zero; DC bias is added later.
    """
    time = np.asarray(time_s)
    if np.any(time < 0):
        raise ValueError("time must be nonnegative")
    h = transfer(frequency_hz, r_ohm, c_farad)
    steady = amplitude_v * np.imag(h * np.exp(2j * np.pi * frequency_hz * time))
    return steady - amplitude_v * np.imag(h) * np.exp(-time / (r_ohm * c_farad))


def quantize(voltage, bits: int = 12, reference_v: float = 3.3):
    """Ideal mid-rise ADC: bins of Vref/2^bits, reconstructed at bin centers."""
    if not isinstance(bits, int) or not 1 <= bits <= 24 or not np.isfinite(reference_v) or reference_v <= 0:
        raise ValueError("invalid ADC resolution or reference")
    v = np.asarray(voltage)
    if not np.all(np.isfinite(v)):
        raise ValueError("ADC input must be finite")
    levels = 1 << bits
    lsb = reference_v / levels
    code = np.floor(np.clip(v, 0, reference_v) / lsb).astype(np.int64)
    code = np.clip(code, 0, levels - 1)
    reconstructed = (code + 0.5) * lsb
    clipped = (v < 0) | (v >= reference_v)
    return code, reconstructed, clipped


def tolerance_sweep(cfg: Config, devices: int = 10_000, seed: int = 7):
    if devices < 1:
        raise ValueError("devices must be positive")
    rng = np.random.default_rng(seed)
    r = cfg.r_ohm * rng.uniform(1 - cfg.r_tolerance, 1 + cfg.r_tolerance, devices)
    c = cfg.c_farad * rng.uniform(1 - cfg.c_tolerance, 1 + cfg.c_tolerance, devices)
    return r, c, 1 / (2 * np.pi * r * c)


def rms(values):
    return float(np.sqrt(np.mean(np.square(values))))


def ratio_db(signal, error):
    denominator = rms(error)
    return float(20 * np.log10(rms(signal) / denominator)) if denominator else float("inf")


def waveforms(cfg: Config):
    t = np.arange(int(round(cfg.duration_s * cfg.sample_hz))) / cfg.sample_hz
    signal = cfg.signal_peak_v * np.sin(2 * np.pi * cfg.signal_hz * t)
    interference = cfg.interference_peak_v * np.sin(2 * np.pi * cfg.interference_hz * t)
    clean = sine_response(t, cfg.signal_peak_v, cfg.signal_hz, cfg.r_ohm, cfg.c_farad)
    unwanted = sine_response(t, cfg.interference_peak_v, cfg.interference_hz, cfg.r_ohm, cfg.c_farad)
    vin = cfg.bias_v + signal + interference
    vout = cfg.bias_v + clean + unwanted
    code, adc, clipped = quantize(vout, cfg.adc_bits, cfg.supply_v)
    return t, vin, vout, code, adc, clipped, signal, interference, clean, unwanted


def spice_netlists(cfg: Config):
    setup = "set wr_singlescale\nset wr_vecnames\nset numdgt=15\n"
    ac = ("* RC filter: 1 V AC is a small-signal normalization, not an actual rail swing.\n"
          f"Vsignal in 0 DC {cfg.bias_v:.12g} AC 1\n"
          f"Rfilter in out {cfg.r_ohm:.12g}\nCfilter out 0 {cfg.c_farad:.12g}\n"
          f".control\n{setup}ac dec 100 10 100k\n"
          "wrdata build/spice_ac.txt real(v(out)) imag(v(out))\nquit\n.endc\n.end\n")
    transient = ("* Biased sensor sine plus a separate series interference source.\n"
                 f"Vbias bias 0 DC {cfg.bias_v:.12g}\n"
                 f"Vsignal sensor bias SIN(0 {cfg.signal_peak_v:.12g} {cfg.signal_hz:.12g})\n"
                 f"Vinterference in sensor SIN(0 {cfg.interference_peak_v:.12g} {cfg.interference_hz:.12g})\n"
                 f"Rfilter in out {cfg.r_ohm:.12g}\nCfilter out 0 {cfg.c_farad:.12g} IC={cfg.bias_v:.12g}\n"
                 f".control\n{setup}tran 0.5u {cfg.duration_s:.12g} 0 0.5u uic\n"
                 "wrdata build/spice_transient.txt v(in) v(out)\nquit\n.endc\n.end\n")
    return ac, transient


def check_spice(cfg: Config, repo: Path, executable: str, output: Path, t, vout):
    build = repo / "build"
    build.mkdir(exist_ok=True)
    for name, text in zip(("rc_ac.cir", "rc_transient.cir"), spice_netlists(cfg)):
        path = build / name
        path.write_text(text)
        result = subprocess.run([executable, "-b", str(path)], cwd=repo,
                                text=True, capture_output=True, timeout=60)
        (build / (name + ".log")).write_text(result.stdout + result.stderr)
        if result.returncode:
            raise RuntimeError(f"ngspice failed; inspect build/{name}.log")
    ac = np.loadtxt(build / "spice_ac.txt", skiprows=1)
    simulated = ac[:, 1] + 1j * ac[:, 2]
    expected = transfer(ac[:, 0], cfg.r_ohm, cfg.c_farad)
    ac_error = np.abs(simulated - expected) / np.abs(expected)
    transient = np.loadtxt(build / "spice_transient.txt", skiprows=1)
    mask = (t >= cfg.measure_after_s) & (t <= transient[-1, 0])
    sampled = np.interp(t[mask], transient[:, 0], transient[:, 2])
    transient_error = float(np.max(np.abs(sampled - vout[mask])))
    if float(ac_error.max()) > 1e-6 or transient_error > 10e-6:
        raise RuntimeError(f"SPICE mismatch: AC relative {ac_error.max():.3g}, transient {transient_error:.3g} V")
    np.savetxt(output / "spice_ac_check.csv", np.column_stack((ac[:, 0], expected.real,
               expected.imag, simulated.real, simulated.imag, ac_error)), delimiter=",",
               header="frequency_hz,theory_real,theory_imag,spice_real,spice_imag,relative_complex_error", comments="", fmt="%.10g")
    version = subprocess.run([executable, "--version"], text=True, capture_output=True, timeout=10)
    found = re.search(r"ngspice-[\d.]+", version.stdout + version.stderr, re.IGNORECASE)
    return {"passed": True, "version": found.group() if found else "ngspice",
            "ac_points": len(ac), "max_ac_relative_complex_error": float(ac_error.max()),
            "max_transient_error_v": transient_error,
            "ac_tolerance": 1e-6, "transient_tolerance_v": 10e-6}


def plots(cfg, out, t, vin, vout, adc, cutoff_samples, spice):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"svg.fonttype": "none", "font.size": 10})
    frequency = np.geomspace(10, 100_000, 401)
    h = transfer(frequency, cfg.r_ohm, cfg.c_farad)
    fig, axes = plt.subplots(2, 1, figsize=(8.8, 5.2), sharex=True)
    axes[0].semilogx(frequency, 20*np.log10(np.abs(h)), color="#26785e", label="RC equation")
    axes[1].semilogx(frequency, np.angle(h, deg=True), color="#26785e")
    if spice:
        check = np.genfromtxt(out / "spice_ac_check.csv", delimiter=",", names=True)
        points = check[::20]
        value = points["spice_real"] + 1j*points["spice_imag"]
        axes[0].semilogx(points["frequency_hz"], 20*np.log10(abs(value)), "o", ms=4,
                         mfc="none", color="#333333", label="ngspice")
        axes[1].semilogx(points["frequency_hz"], np.angle(value, deg=True), "o", ms=4,
                         mfc="none", color="#333333")
    for ax in axes:
        ax.axvline(cfg.cutoff_hz, color="#999999", ls="--", lw=1)
        ax.grid(which="both", alpha=.17)
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set(ylabel="Voltage gain (dB)", title=f"RC front-end · {cfg.r_ohm/1000:g} kΩ / {cfg.c_farad*1e9:g} nF")
    axes[0].legend(frameon=False, loc="lower left")
    axes[1].set(xlabel="Frequency (Hz)", ylabel="Phase (degrees)")
    fig.tight_layout(); fig.savefig(out / "frequency_response.svg", metadata={"Date": None}); plt.close(fig)
    fig, axes = plt.subplots(2, 1, figsize=(8.8, 5.5))
    view = (t >= cfg.measure_after_s) & (t < cfg.measure_after_s + .02)
    axes[0].plot(t[view]*1000, vin[view], color="#bbbbbb", lw=.65, label="Sensor + interference")
    axes[0].plot(t[view]*1000, vout[view], color="#26785e", lw=1.2, label="RC output")
    axes[0].set(xlabel="Time (ms)", ylabel="Voltage (V)", title="Synthetic sensor waveform")
    axes[0].legend(frameon=False, fontsize=9)
    zoom = (t >= cfg.measure_after_s) & (t < cfg.measure_after_s + .001)
    axes[1].step((t[zoom]-cfg.measure_after_s)*1e6, (adc[zoom]-vout[zoom])*1000,
                 where="mid", color="#26785e", lw=.8)
    axes[1].axhline(cfg.lsb_v*500, color="#999999", ls="--", lw=.8)
    axes[1].axhline(-cfg.lsb_v*500, color="#999999", ls="--", lw=.8)
    axes[1].set(xlabel="Time since measurement start (µs)", ylabel="ADC error (mV)",
                title="Ideal ADC reconstruction error · dashed lines = ±½ LSB")
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False); ax.grid(alpha=.15)
    fig.tight_layout(); fig.savefig(out / "waveforms.svg", metadata={"Date": None}); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    ax.hist(cutoff_samples, bins=45, color="#9ec3b6", edgecolor="white")
    ax.axvline(cfg.cutoff_hz, color="#26785e", lw=2, label="Nominal cutoff")
    low = cfg.cutoff_hz / ((1+cfg.r_tolerance)*(1+cfg.c_tolerance))
    high = cfg.cutoff_hz / ((1-cfg.r_tolerance)*(1-cfg.c_tolerance))
    ax.axvline(low, color="#888888", ls="--", label="Worst-case corners")
    ax.axvline(high, color="#888888", ls="--")
    ax.set(xlabel="Cutoff frequency (Hz)", ylabel="Simulated component sets",
           title=f"Tolerance study · R ±{100*cfg.r_tolerance:g}% / C ±{100*cfg.c_tolerance:g}%")
    ax.spines[["top", "right"]].set_visible(False); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(out / "tolerances.svg", metadata={"Date": None}); plt.close(fig)


def run(cfg: Config, output: Path, devices: int = 10_000, seed: int = 7,
        spice: bool = False, ngspice: str = "ngspice"):
    output.mkdir(parents=True, exist_ok=True)
    if not spice:
        (output / "spice_ac_check.csv").unlink(missing_ok=True)
    t, vin, vout, code, adc, clipped, signal, unwanted, clean, filtered_unwanted = waveforms(cfg)
    measured = t >= cfg.measure_after_s
    _, _, cutoffs = tolerance_sweep(cfg, devices, seed)
    frequency = np.geomspace(10, 100_000, 401)
    h = transfer(frequency, cfg.r_ohm, cfg.c_farad)
    np.savetxt(output / "frequency_response.csv", np.column_stack((frequency, abs(h),
               20*np.log10(abs(h)), np.angle(h, deg=True))), delimiter=",",
               header="frequency_hz,gain_v_per_v,gain_db,phase_deg", comments="", fmt="%.10g")
    np.savetxt(output / "waveforms.csv", np.column_stack((t, vin, vout, code, adc)), delimiter=",",
               header="time_s,input_v,filtered_v,adc_code,adc_reconstructed_v", comments="", fmt=["%.8g", "%.8g", "%.8g", "%d", "%.8g"])
    # Store distribution summaries rather than 10,000 nearly identical device rows.
    counts, edges = np.histogram(cutoffs, bins=45)
    np.savetxt(output / "cutoff_distribution.csv", np.column_stack((counts, edges[:-1], edges[1:])),
               delimiter=",", header="count,bin_low_hz,bin_high_hz", comments="", fmt="%.10g")
    metrics = {"simulation_only": True, "config": asdict(cfg), "seed": seed,
               "devices": devices, "cutoff_hz": float(cfg.cutoff_hz),
               "gain_at_signal": float(abs(transfer(cfg.signal_hz, cfg.r_ohm, cfg.c_farad))),
               "gain_at_interference": float(abs(transfer(cfg.interference_hz, cfg.r_ohm, cfg.c_farad))),
               "lsb_v": cfg.lsb_v,
               "quantization_rms_v": rms((adc-vout)[measured]),
               "uniform_quantization_estimate_rms_v": cfg.lsb_v/np.sqrt(12),
               "sir_input_db": ratio_db(signal[measured], unwanted[measured]),
               "sir_filtered_db": ratio_db(clean[measured], filtered_unwanted[measured]),
               "signal_to_total_error_after_adc_db": ratio_db(clean[measured], (adc-cfg.bias_v-clean)[measured]),
               "clipped_samples": int(clipped.sum()), "samples": len(t),
               "output_min_v": float(vout.min()), "output_max_v": float(vout.max()),
               "cutoff_min_hz": float(cutoffs.min()), "cutoff_max_hz": float(cutoffs.max()),
               "cutoff_p05_hz": float(np.percentile(cutoffs, 5)),
               "cutoff_p95_hz": float(np.percentile(cutoffs, 95)),
               "cutoff_corner_low_hz": cfg.cutoff_hz/((1+cfg.r_tolerance)*(1+cfg.c_tolerance)),
               "cutoff_corner_high_hz": cfg.cutoff_hz/((1-cfg.r_tolerance)*(1-cfg.c_tolerance)),
               "rc_thermal_estimate_rms_v": float(np.sqrt(K_B*cfg.temperature_k/cfg.c_farad))}
    metrics["spice"] = check_spice(cfg, Path(__file__).resolve().parents[1], ngspice,
                                   output, t, vout) if spice else {"passed": None, "reason": "not requested"}
    plots(cfg, output, t, vin, vout, adc, cutoffs, spice)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2, allow_nan=False) + "\n")
    lines = ["# RC front-end simulation results", "",
             f"R = {cfg.r_ohm:g} Ω, C = {cfg.c_farad*1e9:g} nF, bias = {cfg.bias_v:g} V, supply/reference = {cfg.supply_v:g} V.",
             f"Synthetic input: {cfg.signal_peak_v*1000:g} mV peak at {cfg.signal_hz:g} Hz + {cfg.interference_peak_v*1000:g} mV peak at {cfg.interference_hz:g} Hz.",
             f"Ideal {cfg.adc_bits}-bit ADC sampled at {cfg.sample_hz/1000:g} ksample/s; {len(t)} samples. Metrics exclude the first {cfg.measure_after_s*1000:g} ms.", "",
             "| Quantity | Result |", "| --- | ---: |",
             f'| Nominal cutoff | {metrics["cutoff_hz"]:.3f} Hz |',
             f'| Gain at {cfg.signal_hz:g} Hz | {metrics["gain_at_signal"]:.6f} V/V |',
             f'| Gain at {cfg.interference_hz:g} Hz | {metrics["gain_at_interference"]:.6f} V/V |',
             f'| ADC LSB | {cfg.lsb_v*1e6:.3f} µV |',
             f'| Input signal/interference | {metrics["sir_input_db"]:.3f} dB |',
             f'| Filtered signal/interference | {metrics["sir_filtered_db"]:.3f} dB |',
             f'| Signal/total error after ideal ADC | {metrics["signal_to_total_error_after_adc_db"]:.3f} dB |',
             f'| ADC reconstruction error RMS | {metrics["quantization_rms_v"]*1e6:.3f} µV |',
             f'| Clipped samples | {metrics["clipped_samples"]} / {len(t)} |',
             f'| Output voltage range | {metrics["output_min_v"]:.4f}–{metrics["output_max_v"]:.4f} V |', "",
             "## Component variation", "",
             f"{devices:,} independent uniform component sets; R ±{cfg.r_tolerance*100:g}%, C ±{cfg.c_tolerance*100:g}%, seed {seed}.",
             f'5th–95th percentiles: {metrics["cutoff_p05_hz"]:.2f}–{metrics["cutoff_p95_hz"]:.2f} Hz.',
             f'Deterministic worst-case corners: {metrics["cutoff_corner_low_hz"]:.2f}–{metrics["cutoff_corner_high_hz"]:.2f} Hz.',
             "These percentiles describe the assumed distribution, not measured manufacturing statistics.", "",
             "## Independent SPICE check", ""]
    if spice:
        s = metrics["spice"]
        lines += [f'{s["version"]}: PASS at {s["ac_points"]} AC points.',
                  f'Maximum complex AC relative error: {s["max_ac_relative_complex_error"]:.3g}.',
                  f'Maximum transient difference after settling: {s["max_transient_error_v"]*1e6:.3f} µV (10 µV tolerance).']
    else:
        lines.append("SPICE was not requested for this run. Use --spice to check both AC and transient analyses.")
    lines += ["", "## Model limits", "",
              "The input sources, bias, and ADC are ideal. The ADC has infinite input impedance; sample-and-hold loading, aperture jitter, INL/DNL, reference noise, and real component parasitics are not modeled.",
              "The RC thermal estimate sqrt(kT/C) and uniform quantization estimate LSB/sqrt(12) are analytical estimates, not noise injected into these waveforms.",
              f"Signal/interference figures apply to the specified {cfg.signal_hz:g} Hz / {cfg.interference_hz:g} Hz tones; they are not broadband SNR, ENOB, or anti-alias certification.",
              "No circuit board, breadboard, oscilloscope measurement, or physical ADC result is represented here.", ""]
    (output / "report.md").write_text("\n".join(lines))
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("results"))
    parser.add_argument("--r-ohm", type=float, default=10_000)
    parser.add_argument("--c-farad", type=float, default=10e-9)
    parser.add_argument("--devices", type=int, default=10_000)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--spice", action="store_true", help="also cross-check AC and transient in ngspice")
    parser.add_argument("--ngspice", default="ngspice", help="ngspice executable name or path")
    args = parser.parse_args()
    try:
        metrics = run(Config(r_ohm=args.r_ohm, c_farad=args.c_farad), args.out,
                      args.devices, args.seed, args.spice, args.ngspice)
    except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as error:
        parser.error(str(error))
    print(f'Cutoff: {metrics["cutoff_hz"]:.3f} Hz; LSB: {metrics["lsb_v"]*1e6:.3f} µV')
    print(f'Signal/interference: {metrics["sir_input_db"]:.2f} -> {metrics["sir_filtered_db"]:.2f} dB')
    print(f'Wrote simulation results to {args.out}; SPICE passed: {metrics["spice"]["passed"]}')


if __name__ == "__main__":
    main()
