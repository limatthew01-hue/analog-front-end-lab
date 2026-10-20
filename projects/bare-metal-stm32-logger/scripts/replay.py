"""Drive the real portable C application with a synthetic analog/ADC stream."""
from pathlib import Path
import csv, hashlib, json, math, random, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'host'))
from protocol import decode
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def main():
    out=ROOT/'results'; out.mkdir(exist_ok=True)
    random.seed(42); analog=[1.0,.75]; rows=[]; expected={}; windows=[[],[]]
    alpha=math.exp(-.01/.01)  # 100 Hz sample interval; 10k * 1uF = 10 ms
    for tick in range(10,5001,10):
        inputs=[2 if tick<2000 else 5,1.5+.6*math.sin(2*math.pi*.5*tick/1000)]
        codes=[]
        for channel in [0,1]:
            analog[channel]=alpha*analog[channel]+(1-alpha)*inputs[channel]/2
            code=min(4095,max(0,round(analog[channel]/3.3*4095)+random.randint(-3,3)))
            codes.append(code); windows[channel].append(code); windows[channel]=windows[channel][-16:]
        rows.append([tick,*codes,*inputs])
        if tick%100==0:
            expected[tick]=tuple((sum(w)+len(w)//2)//len(w) for w in windows)
    with (out/'synthetic_adc.csv').open('w',newline='') as f:
        writer=csv.writer(f); writer.writerow(['tick_ms','adc0','adc1','input0_v','input1_v']); writer.writerows(rows)
    stdin=''.join(f'{r[0]},{r[1]},{r[2]}\n' for r in rows)
    run=subprocess.run([str(ROOT/'build/replay')],input=stdin,text=True,capture_output=True,check=True)
    (out/'telemetry.hex').write_text(run.stdout)
    messages=[decode(bytes.fromhex(line)) for line in run.stdout.splitlines()]
    assert len(messages)==50
    for sequence,m in enumerate(messages):
        assert m.sequence==sequence and (m.a,m.b)==expected[m.tick] and not m.flags and not m.dropped
    with (out/'telemetry.csv').open('w',newline='') as f:
        writer=csv.writer(f); writer.writerow(['sequence','tick_ms','adc0_average','adc1_average','input0_v','input1_v','faults'])
        for m in messages: writer.writerow([m.sequence,m.tick,m.a,m.b,*m.input_volts(),m.flags])
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':11,'svg.fonttype':'none'})
    fig,axes=plt.subplots(2,1,figsize=(9,6.2),sharex=True,layout='constrained')
    for ch,ax in enumerate(axes):
        ax.plot([r[0]/1000 for r in rows],[r[3+ch] for r in rows],color='#8a8c90',label='Synthetic source')
        ax.plot([m.tick/1000 for m in messages],[m.input_volts()[ch] for m in messages],'.-',color='#3d8777',label='C firmware replay')
        ax.set_ylabel(f'Input {ch} (V)'); ax.grid(alpha=.2)
    axes[1].set_xlabel('Time (s)')
    fig.suptitle('Bare-metal logger: synthetic input replay',fontweight='bold')
    fig.legend(*axes[0].get_legend_handles_labels(),loc='outside upper center',ncol=2,frameon=False)
    fig.savefig(out/'replay.svg'); plt.close(fig)
    metrics={'source':'synthetic; portable C app executed on host, not MCU hardware',
             'input_pairs':len(rows),'decoded_frames':len(messages),'sample_rate_hz':100,'report_rate_hz':10,
             'average_window':16,'crc_or_average_mismatches':0,'reported_faults':sum(m.flags!=0 for m in messages)}
    (out/'replay.json').write_text(json.dumps(metrics,indent=2)+'\n')
    print(json.dumps(metrics))
if __name__=='__main__': main()
