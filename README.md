# Gerber to G-code Converter for PCB Milling

A command-line tool for converting Gerber PCB layout files to GRBL-compatible G-code for CNC milling.

## Features

- Converts standard Gerber files to G-code
- YAML-based configuration for tool presets
- Support for multiple operations: isolation routing, edge cuts, and drilling
- Automatic board outline generation from trace bounds
- Separate or combined G-code output files
- Tool change commands for multi-tool workflows
- GRBL-compatible output
- Excellon drill file support

## Installation

### Prerequisites

- Python 3.7 or higher
- pip package manager

### Install Dependencies

```bash
pip install -r requirements.txt
```

## Usage

### Windows Batch Script

On Windows, you can use the included batch script:

```batch
gerber2gcode.bat -t traces.gtl -o output.nc
gerber2gcode.bat -t board.gtl -e edges.gm1 -d holes.drl --separate
gerber2gcode.bat --help
```

**Running from other directories:** Add the tool directory to your PATH (see below), then run from anywhere. The batch script automatically uses `config.yaml` from the tool directory.

```batch
cd C:\my\pcb\project
gerber2gcode -t board.gtl -o output.nc
```

To add to PATH:
1. Press `Win + R`, type `sysdm.cpl`, press Enter
2. Click **Advanced** tab → **Environment Variables**
3. Under "User variables", select **Path** → **Edit** → **New**
4. Add: `C:\Users\gcapp\Documents\Making\PCB Milling\Gerber2Gcode`
5. Click OK and open a new command prompt

### Basic Usage

```bash
# Isolation routing from traces file
python gerber_to_gcode.py -t traces.gtl -o output.nc

# Full PCB with traces, edge cuts, and drill holes
python gerber_to_gcode.py -t traces.gtl -e edges.gbr -d holes.drl -o output.nc
```

### Using a Configuration File

Tool settings are defined in a YAML configuration file (`config.yaml` by default):

```bash
# Use default config.yaml
python gerber_to_gcode.py -t traces.gtl

# Use custom configuration
python gerber_to_gcode.py -t traces.gtl --config my_settings.yaml
```

### Generating Separate Files

```bash
# Generate separate G-code files for each operation (isolation, edge_cuts, drill)
python gerber_to_gcode.py -t traces.gtl -e edges.gbr -d holes.drl --separate
```

## Command Line Options

### Input Files

| Option | Description |
|--------|-------------|
| `-t, --traces` | Copper traces Gerber file (.gbr, .gtl, .gbl) |
| `-e, --edge-cuts` | Edge cuts Gerber file for board outline |
| `-d, --drill` | Excellon drill file (.drl, .xln) |
| `input` | Legacy: Input Gerber file (use `-t` instead) |

### Output Options

| Option | Description |
|--------|-------------|
| `-o, --output` | Output G-code file (default: output.nc) |
| `--separate` | Generate separate files for each operation |
| `--generate-edge-cuts` | Output file for generated edge cuts Gerber |

### Configuration

| Option | Description |
|--------|-------------|
| `--config` | YAML configuration file (default: config.yaml) |
| `--edge-margin` | Override edge margin for imputed board outline (mm) |
| `--dpi` | Override DPI for Gerber rendering |

## Configuration File (config.yaml)

All tool settings are defined in the YAML configuration file:

```yaml
# General settings
general:
  safe_height: 2.0        # mm - Z height for rapid moves
  dpi: 1000               # Resolution for Gerber rendering

# Tool presets for each operation type
tools:
  # Isolation routing for copper traces
  isolation:
    tool_diameter: 0.1    # mm - V-bit tip or engraving bit
    spindle_speed: 10000  # RPM
    feed_rate: 200        # mm/min - cutting feed
    plunge_rate: 50       # mm/min - plunge feed
    cut_depth: 0.03       # mm - depth per pass
    passes: 1             # number of isolation passes
    step_over: 0.1        # mm - step between passes

  # Edge cuts / board outline
  edge_cuts:
    tool_diameter: 3.175  # mm - end mill for cutting through
    spindle_speed: 8000   # RPM
    feed_rate: 150        # mm/min - cutting feed
    plunge_rate: 30       # mm/min - plunge feed
    cut_depth: 0.3        # mm - depth per pass
    total_depth: 1.5      # mm - total board thickness
    tabs: false           # whether to leave holding tabs
    tab_width: 2.0        # mm - width of tabs if enabled
    tab_height: 0.3       # mm - height of tabs

  # Drilling holes
  drill:
    tool_diameter: 1.2    # mm - drill bit diameter
    spindle_speed: 10000  # RPM
    feed_rate: 100        # mm/min - not used for drilling
    plunge_rate: 60       # mm/min - drilling feed
    cut_depth: 0.3        # mm - peck depth (0 for single plunge)
    total_depth: 1.54     # mm - drill through depth
    retract_height: 1.0   # mm - retract between pecks

# Edge cuts imputation (when no edge cuts file provided)
edge_margin: 1.0          # mm - margin around traces

# Output options
output:
  separate_files: false   # true = one file per operation
  file_prefix: "pcb"      # prefix for output files
```

## Examples

### Example 1: Basic Isolation Routing

```bash
python gerber_to_gcode.py -t top_copper.gtl -o isolation.nc
```

### Example 2: Full PCB Processing

```bash
python gerber_to_gcode.py \
    -t board.gtl \
    -e board_outline.gm1 \
    -d board.drl \
    -o board_complete.nc
```

### Example 3: Separate Output Files

```bash
python gerber_to_gcode.py \
    -t board.gtl \
    -e board_outline.gm1 \
    -d board.drl \
    --separate
# Outputs: pcb_isolation.nc, pcb_edge_cuts.nc, pcb_drill.nc
```

### Example 4: Auto-Generate Board Outline

```bash
# Automatically creates board outline from trace bounds + margin
python gerber_to_gcode.py \
    -t board.gtl \
    --edge-margin 2.0 \
    --generate-edge-cuts board_outline.gbr \
    -o board.nc
```

### Example 5: High Resolution Rendering

```bash
python gerber_to_gcode.py \
    -t fine_traces.gtl \
    --dpi 2000 \
    -o fine_traces.nc
```

### Example 6: Custom Configuration

```bash
python gerber_to_gcode.py \
    -t board.gtl \
    -e edges.gbr \
    --config custom_tools.yaml \
    -o output.nc
```

## Typical Tool Settings

### V-Bit Engraving (0.1mm tip)
- Tool diameter: 0.1 mm
- Feed rate: 200-300 mm/min
- Plunge rate: 50-80 mm/min
- Cut depth: 0.03-0.1 mm
- Spindle speed: 10000-20000 RPM

### End Mill (1/8" / 3.175mm)
- Tool diameter: 3.175 mm
- Feed rate: 150-250 mm/min
- Plunge rate: 30-60 mm/min
- Cut depth: 0.3-0.5 mm per pass
- Spindle speed: 8000-12000 RPM

### PCB Drilling
- Tool diameter: 0.8-1.2 mm
- Plunge rate: 60-100 mm/min
- Peck depth: 0.3-0.5 mm
- Spindle speed: 10000-15000 RPM

## Workflow Tips

1. **Test First**: Always run a test cut on scrap material
2. **Depth Calibration**: Measure actual copper thickness and adjust cut depth
3. **Tool Offset**: Tool diameter is used for isolation offset calculation
4. **Multiple Passes**: Configure in config.yaml for reliability
5. **Spindle Speed**: Higher speeds work better for finer details
6. **Feed Rate**: Start conservative and increase as comfortable
7. **Separate Files**: Use `--separate` for manual tool changes between operations

## File Types

### Gerber Files
- `.gtl` - Top copper layer
- `.gbl` - Bottom copper layer
- `.gto` - Top silkscreen
- `.gbo` - Bottom silkscreen
- `.gts` - Top soldermask
- `.gbs` - Bottom soldermask
- `.gm1` / `.gko` - Board outline/edge cuts
- `.gbr` - Generic Gerber

### Drill Files
- `.drl` - Excellon drill file
- `.xln` - Excellon drill file (alternate extension)

## Limitations

- Focused on isolation routing, edge cuts, and drilling
- For production use, consider specialized PCB CAM software
- Complex fills and pours may need additional processing
- Tab support is defined but not yet fully implemented

## Safety

- Always wear safety glasses when operating CNC equipment
- Secure workpiece properly before milling
- Start with conservative speeds and depths
- Keep hands clear of cutting area
- Use dust extraction when milling FR4

## Troubleshooting

**Issue**: "pygerber library not found"
- Run: `pip install pygerber`

**Issue**: "PyYAML not found"
- Run: `pip install pyyaml`

**Issue**: G-code paths don't match design
- Increase `--dpi` for finer resolution
- Check that input file is valid Gerber format

**Issue**: Edge cuts in wrong location
- Provide explicit edge cuts file with `-e`
- Adjust `--edge-margin` for auto-generated outlines

**Issue**: Drill holes not recognized
- Verify Excellon format (check INCH vs METRIC header)
- Some drill files use different coordinate formats

**Issue**: Tool breaking
- Reduce feed rate in config.yaml
- Reduce depth of cut per pass
- Use multiple lighter passes

## License

This tool is provided as-is for educational and personal use.

## Contributing

Feel free to modify and improve this tool for your specific needs.
