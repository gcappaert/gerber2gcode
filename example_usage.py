#!/usr/bin/env python3
"""
Example usage script for the Gerber to G-code converter
Shows various common use cases
"""

import subprocess
import sys

def run_conversion(description, command):
    """Run a conversion and display the command"""
    print(f"\n{'='*70}")
    print(f"Example: {description}")
    print(f"{'='*70}")
    print(f"Command: {' '.join(command)}")
    print()
    
    # Uncomment the line below to actually run the conversions
    # subprocess.run(command)

def main():
    print("Gerber to G-code Converter - Example Usage")
    print("=" * 70)
    print()
    print("NOTE: These examples show the commands but don't execute them.")
    print("Replace 'input.gtl' with your actual Gerber file.")
    
    # Example 1: Basic conversion
    run_conversion(
        "Basic top copper layer conversion",
        ["python", "gerber_to_gcode.py", "input.gtl", "-o", "output.nc", "--invert"]
    )
    
    # Example 2: Fine detail work
    run_conversion(
        "Fine detail traces with V-bit",
        [
            "python", "gerber_to_gcode.py", "fine_traces.gtl",
            "-o", "fine_traces.nc",
            "-d", "0.1",      # 0.1mm V-bit tip
            "-f", "200",      # 200 mm/min feed
            "-p", "50",       # 50 mm/min plunge
            "-c", "0.1",      # 0.1mm depth
            "-s", "18000",    # 18000 RPM
            "--invert"
        ]
    )
    
    # Example 3: Multiple isolation passes
    run_conversion(
        "Multiple isolation passes for reliability",
        [
            "python", "gerber_to_gcode.py", "board.gtl",
            "-o", "board_isolated.nc",
            "-d", "0.2",
            "-i", "3",               # 3 passes
            "--isolation-step", "0.15",
            "-f", "300",
            "-c", "0.12",
            "--invert"
        ]
    )
    
    # Example 4: Board outline cutting
    run_conversion(
        "Board outline cutting with end mill",
        [
            "python", "gerber_to_gcode.py", "outline.gm1",
            "-o", "outline_cut.nc",
            "-d", "1.0",      # 1mm end mill
            "-f", "150",
            "-p", "40",
            "-c", "0.5",      # 0.5mm per pass (do multiple passes for 1.6mm board)
            "-s", "12000"
        ]
    )
    
    # Example 5: High precision settings
    run_conversion(
        "High precision for dense boards",
        [
            "python", "gerber_to_gcode.py", "dense_board.gtl",
            "-o", "dense_precise.nc",
            "-d", "0.05",     # Very fine tip
            "-f", "100",      # Slower for precision
            "-p", "30",
            "-c", "0.08",
            "-s", "20000",    # High speed for fine work
            "--dpi", "2000",  # Higher resolution rendering
            "--invert"
        ]
    )
    
    print("\n" + "="*70)
    print("To actually run these commands:")
    print("1. Replace example filenames with your actual Gerber files")
    print("2. Adjust parameters for your specific tool and machine")
    print("3. Always test on scrap material first!")
    print("="*70)

if __name__ == "__main__":
    main()
