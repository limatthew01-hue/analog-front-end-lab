"""Nominal ideal-buffer model; this is not an MCP6002 transistor/macromodel."""
from pathlib import Path
import argparse,csv,json,math,subprocess
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--ngspice'); args=parser.parse_args()
    out=ROOT/'results'; out.mkdir(exist_ok=True); build=ROOT/'build'; build.mkdir(exist_ok=True)
    freq=np.logspace(-1,4,401); gain=.5/(1+2j*np.pi*freq*.01)
    error=None
    if args.ngspice:
        raw=build/'spice.txt'
        netlist=f'''Sensor interface nominal ideal-buffer check
Vin input 0 AC 1
Rtop input divider 33k
Rbottom divider 0 33k
Ebuffer buffered 0 divider 0 1
Rfilter buffered adc 10k
Cfilter adc 0 1u
.control
set wr_singlescale
ac dec 80 .1 10000
wrdata {raw} v(adc)
quit
.endc
.end
'''
        (build/'nominal.cir').write_text(netlist)
        run=subprocess.run([args.ngspice,'-b',str(build/'nominal.cir')],text=True,capture_output=True,check=True)
        (out/'ngspice.log').write_text(run.stdout+run.stderr)
        spice=np.loadtxt(raw); reference=.5/(1+2j*np.pi*spice[:,0]*.01)
        error=float(np.max(np.abs(spice[:,1]+1j*spice[:,2]-reference)))
        assert len(spice)==401 and error<1e-7
    with (out/'frequency.csv').open('w',newline='') as f:
        w=csv.writer(f); w.writerow(['frequency_hz','gain_v_per_v','phase_deg']); w.writerows(zip(freq,np.abs(gain),np.angle(gain,deg=True)))
    metrics={'model':'ideal unity buffer; nominal divider and RC only','divider_gain':.5,'cutoff_hz':1/(2*math.pi*.01),
             'divider_gain_corners':[.495,.505], 'cutoff_corners_hz':[1/(2*math.pi*.01*1.01*1.1),1/(2*math.pi*.01*.99*.9)],
             'frequency_points':401,'ngspice_max_complex_error':error,
             'limits':'Excludes real op-amp offset/noise/stability, ADC acquisition, MLCC DC bias and fabrication parasitics.'}
    (out/'analog.json').write_text(json.dumps(metrics,indent=2)+'\n')
    plt.rcParams.update({'font.size':11,'svg.fonttype':'none'})
    fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
    ax.semilogx(freq,20*np.log10(np.abs(gain)),color='#3d8777')
    ax.axvline(metrics['cutoff_hz'],color='#81858a',ls='--',label='15.9 Hz nominal cutoff')
    ax.set(xlabel='Frequency (Hz)',ylabel='Input-to-ADC gain (dB)',title='Nominal sensor interface: ideal-buffer model')
    ax.grid(alpha=.2); ax.legend(frameon=False); fig.savefig(out/'frequency.svg'); plt.close(fig)
    print(json.dumps(metrics))
if __name__=='__main__': main()
