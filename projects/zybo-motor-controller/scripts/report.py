"""Regenerate figures, metrics, and sensitivity sweep after run_checks.py."""
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from host.model import ClosedLoop, MotorPlant, CONTROL_HZ


def main():
    result=ROOT/"results"
    (ROOT/"build").mkdir(exist_ok=True)
    with (result/"rtl_closed_loop.csv").open() as f:
        rows=list(csv.DictReader(f))
    data={key:np.array([float(row[key]) for row in rows]) for key in rows[0]}
    t=data["time_s"]
    pre=(t>=1.5)&(t<2)
    post=(t>=3.5)&(t<4)
    response=(t>=2)&(t<4)
    start=(t>=0.1)&(t<2)
    rpm=data["plant_rpm"]
    # Open-loop comparison: assumed averaged plant and 417-permille fixed drive.
    open_plant=MotorPlant()
    open_trace=[]
    for time in t:
        open_plant.advance(417 if 0.1<=time<4 else 0,1/CONTROL_HZ,
                           90 if 2<=time<4 else 0)
        open_trace.append(open_plant.rpm)
    open_trace=np.array(open_trace)

    def settling(mask, start_time):
        indices=np.where(mask)[0]
        bad=indices[np.abs(rpm[indices]-300)>6]
        if len(bad)==0:
            return float(t[indices[0]]-start_time)
        following=bad[-1]+1
        return float(t[following]-start_time) if following<=indices[-1] else None

    metrics={
        "status":"simulation only; no physical motor measurements",
        "python_tests":19,"rtl_testbenches":7,"pi_reference_vectors":541,
        "pwm_duties_checked":1001,
        "target_rpm":300,"load_step_rpm":90,
        "rtl_clock_hz":200000,"rtl_pwm_hz":1000,"production_clock_hz":125000000,
        "production_pwm_hz":20000,"control_hz":50,"cpr_milli":358331,
        "plant_assumptions":{"no_load_rpm":720,"tau_s":0.12,"equation":"d(rpm)/dt=(720*pwm_bit-load_rpm-rpm)/0.12, clamped at zero"},
        "kp_q8":256,"ki_step_q8":24,"max_duty_permille":900,
        "before_load_mean_rpm":float(rpm[pre].mean()),
        "after_load_mean_rpm":float(rpm[post].mean()),
        "after_load_mean_abs_error_rpm":float(np.abs(rpm[post]-300).mean()),
        "after_load_max_abs_error_rpm":float(np.abs(rpm[post]-300).max()),
        "load_step_min_rpm":float(rpm[response].min()),
        "startup_overshoot_percent":float(max(0,rpm[start].max()-300)/3),
        "startup_settling_2percent_s":settling(start,0.1),
        "load_recovery_2percent_s":settling(response,2),
        "before_load_mean_duty_permille":float(data["duty_permille"][pre].mean()),
        "after_load_mean_duty_permille":float(data["duty_permille"][post].mean()),
        "open_loop_after_load_mean_rpm":float(open_trace[post].mean()),
        "trace_sha256":hashlib.sha256((result/"rtl_closed_loop.csv").read_bytes()).hexdigest(),
        "versions":{"python":sys.version.split()[0],"numpy":np.__version__,"matplotlib":matplotlib.__version__},
    }
    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":11,"svg.fonttype":"none",
                         "axes.spines.top":False,"axes.spines.right":False})
    fig,axes=plt.subplots(2,1,figsize=(9,6.2),sharex=True,gridspec_kw={"height_ratios":[2,1]})
    axes[0].plot(t,data["target_rpm"],color="#777777",ls="--",label="Target")
    axes[0].plot(t,rpm,color="#286a8f",lw=2,label="RTL + simulated motor")
    axes[0].plot(t,data["measured_rpm"],color="#bc6b28",lw=1,alpha=.8,label="Encoder estimate")
    axes[0].set(ylabel="Speed (RPM)",ylim=(0,360),title="Motor speed control — simulation")
    axes[0].legend(loc="upper right",fontsize=9)
    axes[1].plot(t,data["duty_permille"]/10,color="#286a8f",lw=2)
    axes[1].set(xlabel="Time (s)",ylabel="PWM duty (%)",ylim=(0,95))
    for ax in axes:
        ax.axvspan(2,4,color="#e6d3b5",alpha=.35)
        ax.grid(alpha=.2)
    axes[1].text(2.05,85,"Simulated load applied",fontsize=10,color="#755a34")
    fig.tight_layout(); fig.savefig(result/"closed_loop.svg");fig.savefig(ROOT/"build"/"closed_loop.png",dpi=150);plt.close(fig)
    fig,ax=plt.subplots(figsize=(9,4))
    ax.plot(t,rpm,color="#286a8f",lw=2,label="Feedback controller: switched-PWM RTL model")
    ax.plot(t,open_trace,color="#bc6b28",lw=2,label="Fixed 41.7% duty: averaged model")
    ax.plot(t,data["target_rpm"],color="#777777",ls="--",label="Requested speed")
    ax.axvspan(2,4,color="#e6d3b5",alpha=.35)
    ax.set(xlabel="Time (s)",ylabel="Speed (RPM)",title="Response to an assumed 90 RPM load disturbance",ylim=(0,360))
    ax.legend(loc="lower center",fontsize=9);ax.grid(alpha=.2)
    fig.tight_layout();fig.savefig(result/"comparison.svg");fig.savefig(ROOT/"build"/"comparison.png",dpi=150);plt.close(fig)

    sweep=[]
    for gain in (540,720,900):
        for tau in (.06,.12,.24):
            for target in (100,300,500):
                for load in (0,90):
                    loop=ClosedLoop(gain,tau)
                    errors=[];speeds=[]
                    for step in range(400):
                        speed,_,duty=loop.step(target,load if step>=100 else 0)
                        if step>=350:
                            errors.append(abs(speed-target));speeds.append(speed)
                    sweep.append(dict(no_load_rpm=gain,tau_s=tau,target_rpm=target,load_rpm=load,
                                      reachable_in_model=target+load<=gain*.9,
                                      final_mean_rpm=float(np.mean(speeds)),final_mae_rpm=float(np.mean(errors)),
                                      final_duty_permille=duty))
    with (result/"sensitivity.csv").open("w",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=list(sweep[0]));writer.writeheader();writer.writerows(sweep)
    metrics["sensitivity_cases"]=len(sweep)
    metrics["reachable_cases"]=sum(row["reachable_in_model"] for row in sweep)
    metrics["reachable_case_worst_final_mae_rpm"]=max(row["final_mae_rpm"] for row in sweep if row["reachable_in_model"])
    (result/"metrics.json").write_text(json.dumps(metrics,indent=2)+"\n")
    (result/"report.md").write_text(f"""# Motor controller results

These are simulations, not measurements of a motor or a Zybo board.

The closed-loop trace comes from the actual RTL with encoder pins driven by a behavioral mechanical model. The test uses a 200 kHz simulation clock and 1 kHz PWM; the production top selects a 125 MHz clock and 20 kHz PWM. Both use a 50 Hz PI update and the same encoder CPR and gains. PWM ripple, motor behavior, and timing on a physical board remain unverified.

## 300 RPM experiment

| Metric | Simulated result |
|---|---:|
| Mean speed before load, 1.5–2.0 s | {metrics['before_load_mean_rpm']:.2f} RPM |
| Mean speed after load, 3.5–4.0 s | {metrics['after_load_mean_rpm']:.2f} RPM |
| Mean absolute error after load | {metrics['after_load_mean_abs_error_rpm']:.2f} RPM |
| Minimum speed during load response | {metrics['load_step_min_rpm']:.2f} RPM |
| Startup overshoot | {metrics['startup_overshoot_percent']:.2f}% |
| Startup settling to ±2% | {metrics['startup_settling_2percent_s']} s |
| Recovery to ±2% after load | {metrics['load_recovery_2percent_s']} s |
| Mean duty before / after load | {metrics['before_load_mean_duty_permille']/10:.2f}% / {metrics['after_load_mean_duty_permille']/10:.2f}% |
| Fixed 41.7% drive after load, averaged model | {metrics['open_loop_after_load_mean_rpm']:.2f} RPM |

![Closed-loop simulation](closed_loop.svg)

![Comparison with an open-loop averaged model](comparison.svg)

The assumed plant has 720 RPM no-load speed and a 0.12 s mechanical time constant. The load is represented as a 90 RPM reduction in equilibrium speed at 2 s. It is removed when the stop command is sent at 4 s. This is not an identified transfer function for the reference motor: winding inductance, friction, gearbox backlash, supply sag, electrical current, and heating are omitted.

## Sensitivity and limits

The averaged Python model sweeps 54 combinations of assumed motor gain (540/720/900 RPM), time constant (0.06/0.12/0.24 s), target (100/300/500 RPM), and load (0/90 RPM). {metrics['reachable_cases']} cases have enough modeled headroom below the 90% duty cap. Worst final one-second mean absolute error among those cases: {metrics['reachable_case_worst_final_mae_rpm']:.2f} RPM. Unreachable targets retain error rather than exceeding the duty limit. See [sensitivity.csv](sensitivity.csv).

The gains were selected for this assumed model. Real hardware needs conservative tuning and independent speed measurements. The sensitivity sweep changes parameters inside one simplified model; it does not establish physical robustness.

## Verification

- 19 Python tests: independent CRC check vector, corruption rejection, fragmented frames, signed arithmetic, analytic plant response, tracking, and saturation.
- Seven RTL benches: PWM, quadrature decoder, PI, fault core, serial link, end-to-end top, and switched-PWM closed loop.
- All 1,001 permille duty requests tested with both 1,000-clock and production 6,250-clock PWM frames.
- 541 PI vectors checked against the integer Python reference.
- Fault tests cover arm/stop, watchdog, stall, driver fault, reverse/invalid encoder motion, fault clearing, and invalid target rejection.
- Undefined controller states cause a test failure.

Full commands and results: [verification.txt](verification.txt). Parameters, versions, and source-trace checksum: [metrics.json](metrics.json).

Vivado, a physical motor, electrical current sensing, and an oscilloscope were unavailable during development. The Tk panel's protocol/model paths are covered by tests; its desktop window and real serial connection need a local check.
""",encoding="utf-8")
    print(json.dumps(metrics,indent=2))


if __name__=="__main__":
    main()
