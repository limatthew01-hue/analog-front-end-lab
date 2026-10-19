"""Tk operator panel: python -m host.panel --demo OR --port /dev/ttyUSB0.

Demo runs only the Python reference model; hardware mode communicates via UART.
Tkinter is part of common Python desktop installs (python3-tk on Ubuntu).
"""
import argparse
from collections import deque
import csv
import time
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from .model import ClosedLoop
from .protocol import Telemetry, TelemetryParser, command, fault_description


class Panel:
    def __init__(self, root, port=None):
        self.root = root
        self.serial = None
        if port:
            import serial
            self.serial = serial.Serial(port, 115200, timeout=0, write_timeout=0.2)
        self.demo = ClosedLoop() if not port else None
        self.parser = TelemetryParser()
        self.enabled = False
        self.applied_target = 0
        self.sequence = 0
        self.last_send = 0.0
        self.last_received = 0.0
        self.start_time = time.monotonic()
        self.last_demo = self.start_time
        self.records = []
        self.history = deque(maxlen=300)
        self.target = tk.IntVar(value=100)
        self.armed = tk.BooleanVar(value=False)
        self.loaded = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Stopped. Arm only after checking the wiring.")
        self.readout = tk.StringVar(value="Waiting for telemetry…")
        root.title("Motor speed controller · " + ("SIMULATION" if self.demo else port))
        root.geometry("780x580")
        root.minsize(640, 530)
        body = ttk.Frame(root, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Zybo motor speed controller", font=("TkDefaultFont", 19)).pack(anchor="w")
        ttk.Label(body, text="SIMULATED MOTOR — no hardware connected" if self.demo else
                  "3.3 V UART · 115200 baud · physical SW0 must be ON").pack(anchor="w", pady=(4,16))
        row = ttk.Frame(body); row.pack(fill="x")
        ttk.Label(row, text="Target RPM (0–600)").pack(side="left")
        ttk.Spinbox(row, from_=0, to=600, textvariable=self.target, width=8).pack(side="left", padx=10)
        ttk.Button(row, text="Start / Apply", command=self.start).pack(side="left", padx=5)
        ttk.Button(row, text="STOP", command=self.stop).pack(side="left", padx=5)
        ttk.Button(row, text="Clear fault", command=self.clear).pack(side="left", padx=5)
        if self.demo:
            row2 = ttk.Frame(body); row2.pack(fill="x", pady=10)
            ttk.Checkbutton(row2, text="Simulated arm switch", variable=self.armed).pack(side="left")
            ttk.Checkbutton(row2, text="Apply simulated load", variable=self.loaded).pack(side="left", padx=12)
        ttk.Label(body, textvariable=self.readout, font=("TkDefaultFont", 12)).pack(anchor="w", pady=15)
        self.canvas = tk.Canvas(body, background="#fcfcfc", height=250, highlightthickness=1,
                                highlightbackground="#bbbbbb")
        self.canvas.pack(fill="both", expand=True)
        ttk.Label(body, text="Last 6 seconds · blue: measured speed · gray: target speed").pack(anchor="w", pady=5)
        ttk.Label(body, textvariable=self.status, wraplength=700).pack(anchor="w", pady=8)
        ttk.Button(body, text="Save telemetry CSV", command=self.save).pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(20, self.poll)

    def get_target(self):
        rpm = self.target.get()
        if not 0 <= rpm <= 600:
            raise ValueError("Enter an integer from 0 to 600 RPM")
        return rpm

    def send(self, clear=False):
        data = command(self.sequence, self.applied_target if self.enabled else 0,
                       self.enabled, clear)
        self.sequence = (self.sequence+1) & 255
        if self.serial:
            self.serial.write(data)
        self.last_send = time.monotonic()

    def start(self):
        try:
            self.applied_target = self.get_target()
            self.enabled = True
            self.send()
            self.status.set("Run requested. Physical SW0 and fault state determine motor output.")
        except Exception as exc:
            self.enabled = False
            messagebox.showerror("Unable to start", str(exc))

    def stop(self):
        self.enabled = False
        try:
            self.send()
            self.status.set("Stop sent. Output is coast; the motor may keep spinning briefly.")
        except Exception as exc:
            self.status.set(f"Stop could not be sent: {exc}. Turn SW0 OFF.")

    def clear(self):
        self.enabled = False
        try:
            self.send(clear=True)
            self.status.set("Clear sent. SW0 must be OFF; clear does not restart the motor.")
        except Exception as exc:
            self.status.set(str(exc))

    def record(self, packet):
        now = time.monotonic()
        self.last_received = now
        self.readout.set(f"Speed {packet.rpm:6.1f} RPM     Target {packet.target_rpm} RPM     "
                         f"PWM {packet.duty_permille/10:.1f}%\n"
                         f"Arm {'ON' if packet.armed else 'OFF'} · "
                         f"{'RUNNING' if packet.active else 'STOPPED'} · Fault: {fault_description(packet.faults)}")
        self.records.append((now-self.start_time, packet.rpm, packet.target_rpm,
                             packet.duty_permille, packet.status, packet.faults))
        self.history.append((now-self.start_time, packet.rpm, packet.target_rpm))
        while self.history and self.history[0][0] < now-self.start_time-6:
            self.history.popleft()

    def poll(self):
        now = time.monotonic()
        try:
            if now-self.last_send >= 0.1:
                self.send()
            if self.serial:
                for packet in self.parser.feed(self.serial.read(self.serial.in_waiting or 1)):
                    self.record(packet)
                if now-self.last_received > 0.5:
                    self.status.set("No current telemetry. Turn SW0 OFF and check the serial connection.")
            else:
                # Bound catch-up so a paused GUI cannot integrate a giant time step.
                for _ in range(min(10, int((now-self.last_demo)/0.02))):
                    self.last_demo += 0.02
                    target = self.applied_target if self.enabled else 0
                    active = self.enabled and self.armed.get() and target > 0
                    _, measured, duty = self.demo.step(target, 90 if self.loaded.get() else 0, active)
                    self.record(Telemetry(self.sequence, measured, target, duty,
                                         int(active) | (int(self.armed.get()) << 1) | 4, 0, 0))
            self.draw()
        except Exception as exc:
            self.enabled = False
            self.status.set(f"Connection/input error: {exc}. Turn SW0 OFF.")
            if self.serial:
                try:
                    self.send()
                except Exception:
                    pass
        self.root.after(20, self.poll)

    def draw(self):
        c = self.canvas; c.delete("all")
        width, height = c.winfo_width(), c.winfo_height()
        left, top, right, bottom = 50, 18, width-15, height-25
        for rpm in (0, 200, 400, 600):
            y = bottom-rpm/650*(bottom-top)
            c.create_line(left,y,right,y,fill="#e1e1e1")
            c.create_text(left-7,y,text=str(rpm),anchor="e",fill="#555555")
        c.create_text(left,5,text="RPM",anchor="nw",fill="#555555")
        values = list(self.history)
        if len(values) > 1:
            for column,color in ((2,"#777777"),(1,"#276a9b")):
                points = []
                for row in values:
                    x=left+(row[0]-(values[-1][0]-6))/6*(right-left)
                    points.extend((x, bottom-max(0,min(650,row[column]))/650*(bottom-top)))
                c.create_line(*points,fill=color,width=2)

    def save(self):
        name = filedialog.asksaveasfilename(defaultextension=".csv", filetypes=[("CSV","*.csv")])
        if name:
            with open(name,"w",newline="",encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(("time_s","measured_rpm","target_rpm","duty_permille","status","faults"))
                writer.writerows(self.records)

    def close(self):
        self.enabled = False
        if self.serial:
            try:
                for _ in range(3):
                    self.send()
                self.serial.flush()
            except Exception:
                pass  # Hardware watchdog remains the independent fallback.
            self.serial.close()
        self.root.destroy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--demo", action="store_true")
    mode.add_argument("--port", help="3.3 V USB UART serial port")
    args = parser.parse_args()
    root = tk.Tk()
    Panel(root, args.port)
    root.mainloop()


if __name__ == "__main__":
    main()
