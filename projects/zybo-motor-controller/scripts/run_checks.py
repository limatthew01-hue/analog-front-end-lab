"""Run Python tests and Icarus RTL tests; execute from the project root."""
import argparse
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.model import PIController


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--iverilog", default=shutil.which("iverilog"))
    parser.add_argument("--ivl-dir", help="Only needed for a relocated Icarus installation")
    args = parser.parse_args()
    os.chdir(ROOT)
    Path("build").mkdir(exist_ok=True)
    Path("results").mkdir(exist_ok=True)
    log = []

    def run(command):
        result = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print(result.stdout, end="", flush=True)
        log.append("$ "+" ".join(map(str,command))+"\n"+result.stdout)
        if result.returncode:
            Path("results/verification.txt").write_text("\n".join(log),encoding="utf-8")
            raise SystemExit(result.returncode)

    run([sys.executable,"-m","unittest","discover","-s","tests","-v"])
    if not args.iverilog:
        raise SystemExit("Install Icarus Verilog to run the RTL checks (iverilog and vvp).")
    compiler = [args.iverilog]
    if args.ivl_dir:
        compiler += ["-B",args.ivl_dir]
    runtime = str(Path(args.iverilog).resolve().with_name("vvp"))
    model = PIController()
    rng = random.Random(7)
    inputs = [(1,600,0)]*100 + [(1,100,6000)]*30 + [(0,100,0)] + [(1,300,3000)]*10
    inputs += [(int(i%17!=0),rng.randint(0,600),rng.randint(-100,7500)) for i in range(400)]
    with Path("build/pi_vectors.txt").open("w",encoding="utf-8") as out:
        for enabled,target,measured in inputs:
            out.write(f"{enabled} {target} {measured} {model.update(target,measured,enabled)}\n")
    rtl = sorted(str(path) for path in Path("rtl").glob("*.v"))
    run(compiler+["-g2012","-Wall","-s","motor_top","-o","build/motor_top.vvp"]+rtl)
    for bench in ("pwm","quadrature","pi","core","serial","top","closed_loop"):
        path=f"build/tb_{bench}.vvp"
        run(compiler+["-g2012","-Wall","-s",f"tb_{bench}","-o",path,f"sim/tb_{bench}.v"]+rtl)
        run([runtime,path])
    run(compiler+["-g2012","-Wall","-s","tb_pwm","-Ptb_pwm.PERIOD=6250",
                  "-o","build/tb_pwm_production.vvp","sim/tb_pwm.v"]+rtl)
    run([runtime,"build/tb_pwm_production.vvp"])
    Path("results/verification.txt").write_text("\n".join(log),encoding="utf-8")


if __name__ == "__main__":
    main()
