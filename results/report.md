# RC front-end simulation results

R = 10000 Ω, C = 10 nF, bias = 1.65 V, supply/reference = 3.3 V.
Synthetic input: 100 mV peak at 100 Hz + 40 mV peak at 20000 Hz.
Ideal 12-bit ADC sampled at 200 ksample/s; 6000 samples. Metrics exclude the first 10 ms.

| Quantity | Result |
| --- | ---: |
| Nominal cutoff | 1591.549 Hz |
| Gain at 100 Hz | 0.998032 V/V |
| Gain at 20000 Hz | 0.079327 V/V |
| ADC LSB | 805.664 µV |
| Input signal/interference | 7.959 dB |
| Filtered signal/interference | 29.953 dB |
| Signal/total error after ideal ADC | 29.906 dB |
| ADC reconstruction error RMS | 230.615 µV |
| Clipped samples | 0 / 6000 |
| Output voltage range | 1.5470–1.7530 V |

## Component variation

10,000 independent uniform component sets; R ±1%, C ±5%, seed 7.
5th–95th percentiles: 1521.85–1666.93 Hz.
Deterministic worst-case corners: 1500.75–1692.24 Hz.
These percentiles describe the assumed distribution, not measured manufacturing statistics.

## Independent SPICE check

ngspice-42: PASS at 401 AC points.
Maximum complex AC relative error: 9.81e-16.
Maximum transient difference after settling: 1.267 µV (10 µV tolerance).

## Model limits

The input sources, bias, and ADC are ideal. The ADC has infinite input impedance; sample-and-hold loading, aperture jitter, INL/DNL, reference noise, and real component parasitics are not modeled.
The RC thermal estimate sqrt(kT/C) and uniform quantization estimate LSB/sqrt(12) are analytical estimates, not noise injected into these waveforms.
Signal/interference figures apply to the specified 100 Hz / 20000 Hz tones; they are not broadband SNR, ENOB, or anti-alias certification.
No circuit board, breadboard, oscilloscope measurement, or physical ADC result is represented here.
