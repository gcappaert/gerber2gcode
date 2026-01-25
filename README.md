# Gerber to G-code Converter for PCB Milling

A command-line tool for converting Gerber PCB layout files to GRBL-compatible G-code for CNC milling.

## Features

- Converts standard Gerber files to G-code
- Full control over CAM parameters
- Support for isolation routing
- Multiple pass capability
- GRBL-compatible output
- Configurable tool diameter, feed rates, and depths

## Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Basic Usage

```bash
python gerber_to_gcode.py input.gtl -o output.nc
```

### Advanced Usage with Custom Settings

```bash
python gerber_to_gcode.py input.gtl \
    --output output.nc \
    --tool-diameter 0.2 \
    --feed-rate 300 \
    --plunge-rate 80 \
    --cut-depth 0.15 \
    --safe-height 3.0 \
    --spindle-speed 12000 \
    --isolation-passes 2 \
    --isolation-step 0.15 \
    --invert
```

## Command Line Options

### Required Arguments

- `input` - Input Gerber file (.gbr, .gtl, .gbl, etc.)

### Optional Arguments

**Output:**
- `-o, --output` - Output G-code file (default: output.nc)

**Tool Settings:**
- `-d, --tool-diameter` - Tool diameter in mm (default: 0.1)

**Feed Rates:**
- `-f, --feed-rate` - Cutting feed rate in mm/min (default: 200)
- `-p, --plunge-rate` - Plunge feed rate in mm/min (default: 50)

**Cut Parameters:**
- `-c, --cut-depth` - Depth of cut in mm (default: 0.1)
- `-z, --safe-height` - Safe Z height for rapid moves in mm (default: 2.0)

**Spindle:**
- `-s, --spindle-speed` - Spindle speed in RPM (default: 10000)

**Isolation Routing:**
- `-i, --isolation-passes` - Number of isolation passes (default: 1)
- `--isolation-step` - Step over between passes in mm (default: 0.1)

**Rendering:**
- `--dpi` - DPI for Gerber rendering (default: 1000)
- `--invert` - Invert the Gerber image for isolation routing

## Examples

### Example 1: Top Copper Layer with Fine Detail

```bash
python gerber_to_gcode.py top_copper.gtl \
    -o top_copper.nc \
    -d 0.1 \
    -f 200 \
    -c 0.1 \
    -s 15000 \
    --invert
```

### Example 2: Bottom Copper with Multiple Passes

```bash
python gerber_to_gcode.py bottom_copper.gbl \
    -o bottom_copper.nc \
    -d 0.2 \
    -f 300 \
    -c 0.15 \
    -i 3 \
    --isolation-step 0.15 \
    --invert
```

### Example 3: Edge Cut/Outline

```bash
python gerber_to_gcode.py board_outline.gm1 \
    -o outline_cut.nc \
    -d 0.8 \
    -f 150 \
    -p 50 \
    -c 1.6
```

### Example 4: Slow and Precise

```bash
python gerber_to_gcode.py fine_traces.gtl \
    -o fine_traces.nc \
    -d 0.05 \
    -f 100 \
    -p 30 \
    -c 0.08 \
    -s 20000 \
    --dpi 2000 \
    --invert
```

## Typical Tool Settings

### V-Bit Engraving (0.1mm tip)
- Tool diameter: 0.1 mm
- Feed rate: 200-300 mm/min
- Plunge rate: 50-80 mm/min
- Cut depth: 0.08-0.12 mm
- Spindle speed: 15000-20000 RPM

### End Mill (0.4mm-0.8mm)
- Tool diameter: 0.4-0.8 mm
- Feed rate: 150-250 mm/min
- Plunge rate: 40-60 mm/min
- Cut depth: 0.2-0.4 mm
- Spindle speed: 10000-15000 RPM

### PCB Cutting (1.0mm+)
- Tool diameter: 1.0-2.0 mm
- Feed rate: 100-200 mm/min
- Plunge rate: 30-50 mm/min
- Cut depth: 0.4-0.6 mm per pass
- Spindle speed: 8000-12000 RPM

## Workflow Tips

1. **Test First**: Always run a test cut on scrap material
2. **Depth Calibration**: Measure actual copper thickness and adjust cut depth
3. **Tool Offset**: Account for tool diameter in isolation routing
4. **Multiple Passes**: Use shallow depths with multiple passes for best results
5. **Spindle Speed**: Higher speeds work better for finer details
6. **Feed Rate**: Start conservative and increase as comfortable

## File Types

Common Gerber file extensions:
- `.gtl` - Top copper layer
- `.gbl` - Bottom copper layer
- `.gto` - Top silkscreen
- `.gbo` - Bottom silkscreen
- `.gts` - Top soldermask
- `.gbs` - Bottom soldermask
- `.gm1` / `.gko` - Board outline/edge cuts
- `.gbr` - Generic Gerber

## Limitations

- This is a basic implementation focused on isolation routing
- For production use, consider specialized PCB CAM software
- Complex fills and pours may need additional processing
- Drilling operations require separate drill file processing

## Safety

- Always wear safety glasses when operating CNC equipment
- Secure workpiece properly before milling
- Start with conservative speeds and depths
- Keep hands clear of cutting area
- Use dust extraction when milling FR4

## Troubleshooting

**Issue**: "python-gerber library not found"
- Run: `pip install pygerber pycairo`

**Issue**: G-code looks wrong
- Check if `--invert` flag is needed for isolation routing
- Verify input file is a valid Gerber file

**Issue**: Cuts too deep/shallow
- Adjust `--cut-depth` parameter
- Measure actual copper thickness with calipers

**Issue**: Tool breaking
- Reduce feed rate
- Reduce depth of cut
- Use multiple lighter passes

## License

This tool is provided as-is for educational and personal use.

## Contributing

Feel free to modify and improve this tool for your specific needs.
