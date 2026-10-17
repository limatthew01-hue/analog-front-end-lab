"""Classify synthetic sensor records with device-disjoint evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import platform

import joblib
import numpy as np
import sklearn
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

LABELS = ("normal", "clipped", "dropout", "interference")
FS = 8000
SAMPLES = 512
VREF = 3.3
LSB = VREF / 4096
FEATURES = ("mean_v", "rms_ac_v", "peak_to_peak_v", "crest_factor", "kurtosis",
            "zero_cross_hz", "flat_fraction", "longest_flat_fraction", "rail_fraction",
            "dominant_hz", "spectral_centroid_hz", "high_band_fraction",
            "spectral_entropy", "difference_rms_v", "iqr_v")


def waveform(seed: int, device: int, label: int, window: int, snr_db=None):
    """A device has shared gain/bias; every class uses the same nuisance ranges."""
    if label not in range(4):
        raise ValueError("unknown class")
    d = np.random.default_rng(np.random.SeedSequence([seed, device, 9999]))
    bias, gain = 1.65 + d.uniform(-.15, .15), d.uniform(.8, 1.2)
    r = np.random.default_rng(np.random.SeedSequence([seed, device, label, window]))
    amplitude = gain * r.uniform(.15, .55)
    frequency, phase = r.uniform(80, 400), r.uniform(0, 2*np.pi)
    t = np.arange(SAMPLES)/FS
    signal = amplitude * (np.sin(2*np.pi*frequency*t + phase)
             + r.uniform(.02, .15)*np.sin(4*np.pi*frequency*t + r.uniform(0, 2*np.pi)))
    tone = r.uniform(1100, 2700)
    strength = r.uniform(.15, .75)
    nominal_snr = r.uniform(20, 40)
    noise_draw = r.normal(size=SAMPLES)
    limit = amplitude*r.uniform(.45, .95)
    start, length = int(r.integers(0, 300)), int(r.integers(42, 129))
    noise = np.sqrt(np.mean(signal**2))*10**(-(nominal_snr if snr_db is None else snr_db)/20)*noise_draw
    measured = signal + noise
    if label == 1:
        # Amplifier-like hard limiting around bias, possibly below ADC rails.
        measured = np.clip(measured, -limit, limit)
    elif label == 3:
        measured += amplitude*strength*np.sin(2*np.pi*tone*t + phase)
    codes = np.clip(np.floor((bias+measured)/LSB), 0, 4095)
    if label == 2:
        # Digital stale-sample fault after the ADC, not a physical broken sensor.
        codes[start:start+length] = codes[max(0, start-1)]
    return (codes+.5)*LSB


def features(voltage):
    x = np.asarray(voltage, dtype=float)
    if x.shape != (SAMPLES,) or not np.all(np.isfinite(x)):
        raise ValueError(f"expected {SAMPLES} finite voltage samples")
    z = x-x.mean()
    rms = np.sqrt(np.mean(z*z))
    difference = np.diff(x)
    flat = abs(difference) < .75*LSB
    longest, current = 1, 1
    for same in flat:
        current = current+1 if same else 1
        longest = max(longest, current)
    power = abs(np.fft.rfft(z*np.hanning(SAMPLES)))**2
    power[0] = 0
    frequencies = np.fft.rfftfreq(SAMPLES, 1/FS)
    total = power.sum()
    p = power / total if total > 1e-20 else np.zeros_like(power)
    nonzero = p[p > 0]
    values = [x.mean(), rms, np.ptp(x), np.max(abs(z))/max(rms, 1e-12),
              np.mean(z**4)/max(rms**4, 1e-24),
              np.count_nonzero(np.diff(z >= 0))*FS/(2*SAMPLES),
              flat.mean(), longest/SAMPLES,
              np.mean((x <= LSB) | (x >= VREF-LSB)),
              frequencies[np.argmax(power)] if total > 1e-20 else 0,
              np.sum(p*frequencies), np.sum(p[frequencies >= 1000]),
              -np.sum(nonzero*np.log(nonzero))/np.log(len(power)-1),
              np.sqrt(np.mean(difference**2)), np.percentile(x, 75)-np.percentile(x, 25)]
    return np.asarray(values, dtype=float)


def make_dataset(seed=7, devices=range(40), windows=10, snr_db=None):
    if windows < 1 or seed < 0:
        raise ValueError("windows must be positive and seed nonnegative")
    records, labels, groups = [], [], []
    for device in devices:
        for label in range(4):
            for window in range(windows):
                records.append(waveform(seed, int(device), label, window, snr_db))
                labels.append(label); groups.append(device)
    if not records:
        raise ValueError("provide at least one device")
    waves = np.asarray(records)
    return np.vstack([features(x) for x in waves]), np.array(labels), np.array(groups), waves


def split_devices(devices=40, seed=7):
    if devices < 10:
        raise ValueError("use at least 10 devices")
    ids = np.random.default_rng(seed).permutation(devices)
    a, b = int(.6*devices), int(.8*devices)
    return {"train": sorted(ids[:a].tolist()), "validation": sorted(ids[a:b].tolist()),
            "test": sorted(ids[b:].tolist())}


class Rules:
    """Fixed EE heuristic baseline. Thresholds are set before model training."""
    def fit(self, x, y): return self

    def predict(self, x):
        values = np.asarray(x)
        output = np.zeros(len(values), dtype=int)
        output[values[:, FEATURES.index("high_band_fraction")] > .12] = 3
        output[values[:, FEATURES.index("flat_fraction")] > .08] = 1
        output[values[:, FEATURES.index("longest_flat_fraction")] > .10] = 2
        return output


def models(seed=7):
    return {"Dummy": DummyClassifier(strategy="most_frequent"), "EE rules": Rules(),
            "Logistic regression": make_pipeline(StandardScaler(), LogisticRegression(C=1, max_iter=2000, random_state=seed)),
            "Random forest": RandomForestClassifier(n_estimators=200, max_depth=8,
                                min_samples_leaf=3, random_state=seed, n_jobs=1)}


def scores(y, prediction):
    return {"accuracy": float(accuracy_score(y, prediction)),
            "macro_f1": float(f1_score(y, prediction, labels=range(4), average="macro", zero_division=0))}


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def plot_results(out, waves, y, selected, matrix, noise_rows):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"svg.fonttype": "none", "font.size": 10})
    fig, axes = plt.subplots(4, 1, figsize=(8.8, 6.4), sharex=True)
    for label, ax in enumerate(axes):
        ax.plot(np.arange(SAMPLES)/FS*1000, waves[np.flatnonzero(y == label)[0]], color="#26785e", lw=1)
        ax.set_ylabel(LABELS[label]); ax.set_ylim(.1, 3.2)
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=.15)
    axes[0].set_title("Synthetic ADC signal examples · voltage (V)", loc="left")
    axes[-1].set_xlabel("Time (ms)")
    fig.tight_layout(); fig.savefig(out/"examples.svg", metadata={"Date": None}); plt.close(fig)
    fig, ax = plt.subplots(figsize=(7.2, 5.5))
    ax.imshow(matrix, cmap="Greens", vmin=0, vmax=max(matrix.max(), 1))
    ax.set_xticks(range(4), LABELS, rotation=20); ax.set_yticks(range(4), LABELS)
    ax.set(xlabel="Predicted class", ylabel="Actual class", title=f"Held-out devices · {selected}")
    for i in range(4):
        for j in range(4):
            ax.text(j, i, str(matrix[i,j]), ha="center", va="center", color="white" if matrix[i,j] > matrix.max()*.65 else "#333")
    fig.tight_layout(); fig.savefig(out/"confusion.svg", metadata={"Date": None}); plt.close(fig)
    fig, ax = plt.subplots(figsize=(8.8, 4.8))
    for name, color in [(selected, "#26785e"), ("EE rules", "#666666"), ("Dummy", "#aaaaaa")]:
        subset = [r for r in noise_rows if r["model"] == name]
        ax.plot([r["snr_db"] for r in subset], [100*r["macro_f1"] for r in subset], "o-", color=color, label=name)
    ax.set(xlabel="Added Gaussian-noise SNR (dB)", ylabel="Macro F1 (%)", ylim=(0, 103), title="Noise stress test · frozen models, held-out devices")
    ax.spines[["top", "right"]].set_visible(False); ax.grid(alpha=.15); ax.legend(frameon=False)
    fig.tight_layout(); fig.savefig(out/"noise_sweep.svg", metadata={"Date": None}); plt.close(fig)


def train(out=Path("results"), seed=7, devices=40, windows=10):
    split = split_devices(devices, seed)
    x, y, groups, waves = make_dataset(seed, range(devices), windows)
    indices = {name: np.flatnonzero(np.isin(groups, ids)) for name, ids in split.items()}
    assert not (set(split["train"]) & set(split["validation"]) or set(split["train"]) & set(split["test"]) or set(split["validation"]) & set(split["test"]))
    fitted = models(seed)
    validation = {}
    for name, model in fitted.items():
        model.fit(x[indices["train"]], y[indices["train"]])
        validation[name] = scores(y[indices["validation"]], model.predict(x[indices["validation"]]))
    eligible = ["Logistic regression", "Random forest"]
    selected = max(eligible, key=lambda name: validation[name]["macro_f1"])
    # Freeze selection before inspecting any test labels or noise-shift results.
    rows, predictions = [], {}
    for name, model in fitted.items():
        predictions[name] = model.predict(x[indices["test"]])
        rows.append({"model": name, "validation_macro_f1": validation[name]["macro_f1"],
                     **scores(y[indices["test"]], predictions[name])})
    noise_rows = []
    for snr in [5, 10, 15, 20, 30, 40]:
        shifted_x, shifted_y, _, _ = make_dataset(seed, split["test"], windows, snr)
        for name in [selected, "EE rules", "Dummy"]:
            noise_rows.append({"snr_db": snr, "model": name, **scores(shifted_y, fitted[name].predict(shifted_x))})
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out/"model_comparison.csv", rows)
    write_csv(out/"noise_sweep.csv", noise_rows)
    split_for = {device: part for part, ids in split.items() for device in ids}
    write_csv(out/"features.csv", [{"device": int(g), "split": split_for[int(g)], "class": LABELS[int(label)],
              **{name: float(value) for name, value in zip(FEATURES, vector)}} for vector, label, g in zip(x, y, groups)])
    test_y = y[indices["test"]]
    matrix = confusion_matrix(test_y, predictions[selected], labels=range(4))
    write_csv(out/"test_predictions.csv", [{"device": int(groups[index]), "actual": LABELS[int(test_y[j])],
              **{name: LABELS[int(predictions[name][j])] for name in fitted}} for j, index in enumerate(indices["test"])])
    write_csv(out/"confusion.csv", [{"actual": LABELS[i], **{LABELS[j]: int(matrix[i,j]) for j in range(4)}} for i in range(4)])
    report = classification_report(test_y, predictions[selected], labels=range(4), target_names=LABELS, output_dict=True, zero_division=0)
    metadata = {"synthetic_only": True, "seed": seed, "devices": devices, "windows_per_class_per_device": windows,
                "samples_per_record": SAMPLES, "sample_hz": FS, "adc_bits": 12, "reference_v": VREF,
                "nominal_noise_snr_db": [20, 40], "features": list(FEATURES), "split_device_ids": split,
                "split_records": {part: len(idx) for part, idx in indices.items()},
                "selected_model": selected, "selection": "validation macro F1; ties prefer logistic regression; no refit on validation/test",
                "models": rows, "selected_classification_report": report,
                "waveform_sha256": hashlib.sha256(waves.astype("<f8").tobytes()).hexdigest(),
                "versions": {"python": platform.python_version(), "numpy": np.__version__, "scikit_learn": sklearn.__version__, "joblib": joblib.__version__}}
    (out/"metrics.json").write_text(json.dumps(metadata, indent=2) + "\n")
    examples = Path("examples"); examples.mkdir(exist_ok=True)
    for label, name in enumerate(LABELS):
        index = indices["test"][np.flatnonzero(test_y == label)[0]]
        np.savetxt(examples/(name+".csv"), waves[index], delimiter=",", header="voltage_v", comments="", fmt="%.12g")
    build = Path("build"); build.mkdir(exist_ok=True)
    joblib.dump({"model": fitted[selected], "features": FEATURES, "sample_hz": FS, "samples": SAMPLES}, build/"model.joblib")
    plot_results(out, waves[indices["test"]], test_y, selected, matrix, noise_rows)
    lines = ["# Sensor signal classification results", "",
             f"{len(y):,} synthetic records from {devices} simulated devices; split sizes: {metadata['split_records']}.",
             f"Selected model: **{selected}**, chosen using validation macro F1 before test evaluation.", "",
             "| Model | Validation macro F1 | Test accuracy | Test macro F1 |", "| --- | ---: | ---: | ---: |"]
    lines += [f'| {r["model"]} | {100*r["validation_macro_f1"]:.2f}% | {100*r["accuracy"]:.2f}% | {100*r["macro_f1"]:.2f}% |' for r in rows]
    lines += ["", "The test contains separate device IDs, with the same synthetic generation rules and nominal noise range as training.",
              "The noise sweep reuses those held-out devices with paired records at fixed SNR levels. These are dependent stress conditions, not additional independent test subjects.",
              "No real sensor data, real fault diagnosis, calibrated probabilities, or deployment performance is claimed.",
              "The four generated conditions are intentionally isolated. Mixed faults and unseen fault types are outside the label set.", ""]
    (out/"report.md").write_text("\n".join(lines))
    print(json.dumps({"selected": selected, "records": len(y), "test": next(r for r in rows if r["model"] == selected)}, indent=2))
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("train")
    run.add_argument("--out", type=Path, default=Path("results"))
    run.add_argument("--seed", type=int, default=7)
    run.add_argument("--devices", type=int, default=40)
    run.add_argument("--windows", type=int, default=10)
    predict = sub.add_parser("predict")
    predict.add_argument("--input", type=Path, required=True)
    predict.add_argument("--model", type=Path, default=Path("build/model.joblib"))
    args = parser.parse_args()
    try:
        if args.command == "train": train(args.out, args.seed, args.devices, args.windows)
        else:
            artifact = joblib.load(args.model)
            if tuple(artifact["features"]) != FEATURES or artifact["sample_hz"] != FS:
                raise ValueError("incompatible model artifact")
            voltage = np.loadtxt(args.input, delimiter=",", skiprows=1)
            label = int(artifact["model"].predict(features(voltage)[None, :])[0])
            print(LABELS[label])
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == "__main__": main()
