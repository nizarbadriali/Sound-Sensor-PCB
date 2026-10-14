#!/usr/bin/env python3

import argparse
import glob
import sys
import numpy as np

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

DAT_FILES_PATTERN = 'workdir/*.dat'

# Nominal component values, read from media/schematic.png
R1 = 2.2e3      # Microphone bias resistor
R2 = 100e3      # VCC to GND (see README design observations)
R3 = 100e3      # U1A + input to GND
R4 = 10e3       # Output pull-up
R5 = 100e3      # U1A + input to GND
RV1 = 10e3      # Sensitivity potentiometer
C1 = 100e-9     # Coupling capacitor, microphone node to U1A + input

def design_summary(vcc: float, pot: float) -> dict:
    """
    Calculate the static operating points of the board.

    Args:
        vcc: Supply voltage (V)
        pot: RV1 wiper position, 0.0 (GND end) to 1.0 (VCC end)

    Returns:
        Dictionary of calculated values
    """
    r_bias = R3 * R5 / (R3 + R5)        # DC/AC load on the + input
    r_source = R1 + r_bias              # Mic node source impedance ~ R1 (electret output is high-Z)
    return {
        'r_bias': r_bias,
        'f_hp': 1 / (2 * np.pi * r_source * C1),
        'v_threshold': pot * vcc,
        'mv_per_percent': vcc / 100 * 1e3,
        'i_r2': vcc / R2,
        'i_rv1': vcc / RV1,
        'i_r4': vcc / R4,
    }

def high_pass(signal: np.ndarray, dt: float, rc: float) -> np.ndarray:
    """
    First-order RC high-pass filter (C1 into R3 || R5), discrete form.

    y[n] = a * (y[n-1] + x[n] - x[n-1]),  a = RC / (RC + dt)
    """
    a = rc / (rc + dt)
    out = np.zeros_like(signal)
    for i in range(1, signal.size):
        out[i] = a * (out[i - 1] + signal[i] - signal[i - 1])
    return out

def comparator(v_plus: np.ndarray, v_minus: float, vcc: float) -> np.ndarray:
    """
    Ideal LM393 with open-collector output and R4 pull-up.
    Output transistor is off (DO pulled to VCC) when V+ > V-, on (DO ~ 0 V) otherwise.
    """
    return np.where(v_plus > v_minus, vcc, 0.0)

def count_events(digital: np.ndarray) -> int:
    """Count rising edges on the digital output."""
    high = digital > 0
    return int(np.sum(high[1:] & ~high[:-1]))

def main():
    """Main entry point - prints design calculations, then runs every .dat file through the signal chain."""

    parser = argparse.ArgumentParser(description='Sound sensor (LM393) signal-chain model')
    parser.add_argument('--vcc', type=float, default=5.0, help='Supply voltage in volts (default 5.0, assumed)')
    parser.add_argument('--pot', type=float, default=0.004, help='RV1 wiper position 0-1 (default 0.004)')
    args = parser.parse_args()

    if not 0.0 <= args.pot <= 1.0:
        print(f"{Colors.RED}✗ --pot must be between 0 and 1{Colors.ENDC}")
        sys.exit(1)

    print(f"\n{Colors.BOLD}{Colors.CYAN}╔══════════════════════════════════════╗")
    print(f"║   Sound Sensor Signal-Chain Model    ║")
    print(f"║   LM393 comparator + electret mic    ║")
    print(f"╚══════════════════════════════════════╝{Colors.ENDC}\n")

    d = design_summary(args.vcc, args.pot)

    print(f"{Colors.BOLD}Design calculations{Colors.ENDC} (VCC = {args.vcc:.2f} V, RV1 at {args.pot*100:.2f} %)")
    print(f"  + input bias (R3 || R5):       {d['r_bias']/1e3:.1f} kΩ to GND")
    print(f"  C1 high-pass corner:           {d['f_hp']:.1f} Hz")
    print(f"  Threshold at - input (RV1):    {d['v_threshold']*1e3:.1f} mV")
    print(f"  Threshold change per 1 % turn: {d['mv_per_percent']:.1f} mV")
    print(f"  R2 standing current:           {d['i_r2']*1e6:.1f} µA")
    print(f"  RV1 divider current:           {d['i_rv1']*1e3:.2f} mA")
    print(f"  R4 current, output low:        {d['i_r4']*1e3:.2f} mA")
    print()

    datFiles = glob.glob(DAT_FILES_PATTERN)

    if not datFiles:
        print(f"{Colors.RED}✗ No data files found matching: \"{DAT_FILES_PATTERN}\"{Colors.ENDC}")
        print(f"  Make sure .dat files are in: workdir/")
        sys.exit(1)

    print(f"{Colors.GREEN}✓ Found {len(datFiles)} data file(s){Colors.ENDC}\n")

    rc = (R1 + d['r_bias']) * C1

    for datFile in datFiles:
        print(f"{Colors.BLUE}Processing:{Colors.ENDC} {datFile}")

        try:
            data = np.loadtxt(datFile)
            time = data[:, 0]
            mic = data[:, 1]
            dt = float(np.mean(np.diff(time)))

            print(f"  Data points: {len(time)}")
            print(f"  Duration: {time[-1] - time[0]:.3f} s at {1/dt:.0f} Hz")
            print(f"  Mic signal range: {mic.min()*1e3:.1f} to {mic.max()*1e3:.1f} mV")

            v_plus = high_pass(mic, dt, rc)
            do = comparator(v_plus, d['v_threshold'], args.vcc)

            print(f"  + input range after C1: {v_plus.min()*1e3:.1f} to {v_plus.max()*1e3:.1f} mV")
            if v_plus.min() < -0.3:
                print(f"  {Colors.YELLOW}! + input goes below -0.3 V (LM393 absolute maximum){Colors.ENDC}")

            high = do > 0
            print(f"\n{Colors.GREEN}✓ Simulation complete{Colors.ENDC}")
            print(f"  DO rising edges: {count_events(do)}")
            print(f"  DO high time: {np.sum(high) * dt * 1e3:.1f} ms ({np.mean(high) * 100:.1f} % of record)")
            if high.any():
                print(f"  First / last high: {time[high][0]:.4f} s / {time[high][-1]:.4f} s")
            print()

        except Exception as e:
            print(f"{Colors.RED}✗ Error processing {datFile}: {str(e)}{Colors.ENDC}\n")
            continue

if __name__ == '__main__':
    main()
