#!/usr/bin/env python3
"""
Gerber to G-code converter for PCB milling
Converts Gerber files to GRBL-compatible G-code for CNC milling
Supports separate tools for isolation routing, edge cuts, and drilling
"""

import argparse
import sys
import os
from pathlib import Path
from typing import List, Tuple, Dict, Optional
import re

try:
    import yaml
except ImportError:
    print("Error: PyYAML not found. Install with: pip install pyyaml")
    sys.exit(1)

try:
    from pygerber.gerberx3.api.v2 import (
        GerberFile,
        FileTypeEnum,
        ImageFormatEnum,
        PixelFormatEnum,
    )
except ImportError:
    print("Error: pygerber library not found. Install with: pip install pygerber")
    sys.exit(1)

try:
    import numpy as np
    from PIL import Image
except ImportError:
    print("Error: Required libraries not found. Install with: pip install numpy pillow")
    sys.exit(1)


class ToolPreset:
    """Tool settings for a specific operation"""
    def __init__(self, config: Dict):
        self.tool_diameter = config.get('tool_diameter', 0.1)
        self.spindle_speed = config.get('spindle_speed', 10000)
        self.feed_rate = config.get('feed_rate', 200)
        self.plunge_rate = config.get('plunge_rate', 50)
        self.cut_depth = config.get('cut_depth', 0.1)
        self.total_depth = config.get('total_depth', self.cut_depth)
        self.passes = config.get('passes', 1)
        self.step_over = config.get('step_over', 0.1)
        self.retract_height = config.get('retract_height', 1.0)
        self.tabs = config.get('tabs', False)
        self.tab_width = config.get('tab_width', 2.0)
        self.tab_height = config.get('tab_height', 0.3)
        self.isolation_border = config.get('isolation_border', 0.0)  # mm
        # Laser-specific attributes
        self.power = config.get('power', 800)
        self.focus_height = config.get('focus_height', 50.0)
        self.dynamic_mode = config.get('dynamic_mode', True)
        self.fill_line_spacing = config.get('fill_line_spacing', 0.1)
        self.trace_border_passes = config.get('trace_border_passes', 0)
        self.pad_min_area = config.get('pad_min_area', 1.0)
        self.pad_max_eccentricity = config.get('pad_max_eccentricity', 0.8)


class GerberToGcode:
    def __init__(self, config_file: Optional[str] = None):
        self.config = self.load_config(config_file)
        self.safe_height = self.config.get('general', {}).get('safe_height', 2.0)
        self.dpi = self.config.get('general', {}).get('dpi', 1000)
        self.edge_margin = self.config.get('edge_margin', 1.0)
        self.separate_files = self.config.get('output', {}).get('separate_files', False)
        self.file_prefix = self.config.get('output', {}).get('file_prefix', 'pcb')

        # Tool presets
        tools_config = self.config.get('tools', {})
        self.isolation_tool = ToolPreset(tools_config.get('isolation', {}))
        self.edge_cuts_tool = ToolPreset(tools_config.get('edge_cuts', {}))
        self.drill_tool = ToolPreset(tools_config.get('drill', {}))
        self.laser_tool = ToolPreset(tools_config.get('laser', {}))

        # File paths
        self.traces_file = None
        self.edge_cuts_file = None
        self.drill_file = None
        self.output_file = None

        # Processed data
        self.trace_bounds = None
        self.board_outline = None

    def load_config(self, config_file: Optional[str]) -> Dict:
        """Load configuration from YAML file or return defaults"""
        default_config = {
            'general': {'safe_height': 2.0, 'dpi': 1000},
            'tools': {
                'isolation': {
                    'tool_diameter': 0.1, 'spindle_speed': 10000,
                    'feed_rate': 200, 'plunge_rate': 50, 'cut_depth': 0.1,
                    'passes': 1, 'step_over': 0.1
                },
                'edge_cuts': {
                    'tool_diameter': 2.0, 'spindle_speed': 8000,
                    'feed_rate': 150, 'plunge_rate': 30, 'cut_depth': 0.5,
                    'total_depth': 1.6
                },
                'drill': {
                    'tool_diameter': 0.8, 'spindle_speed': 12000,
                    'feed_rate': 100, 'plunge_rate': 60, 'cut_depth': 0.5,
                    'total_depth': 1.8, 'retract_height': 1.0
                }
            },
            'edge_margin': 1.0,
            'output': {'separate_files': False, 'file_prefix': 'pcb'}
        }

        if config_file and os.path.exists(config_file):
            try:
                with open(config_file, 'r') as f:
                    loaded = yaml.safe_load(f)
                    # Merge with defaults
                    self._deep_merge(default_config, loaded)
                    print(f"Loaded configuration from {config_file}")
                    return default_config
            except Exception as e:
                print(f"Warning: Could not load config file: {e}")
                print("Using default configuration")

        return default_config

    def _deep_merge(self, base: Dict, override: Dict):
        """Deep merge override into base dict"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def generate_gcode_header(self, operation: str, tool: ToolPreset) -> str:
        """Generate G-code header with initialization commands"""
        header = [
            f"; G-code generated by Gerber to G-code converter",
            f"; Operation: {operation}",
            f"; Tool diameter: {tool.tool_diameter} mm",
            f"; Feed rate: {tool.feed_rate} mm/min",
            f"; Cut depth: {tool.cut_depth} mm",
            "",
            "G21         ; Set units to millimeters",
            "G90         ; Absolute positioning",
            "G94         ; Feed rate per minute",
            f"M3 S{tool.spindle_speed}  ; Start spindle",
            "G4 P2       ; Dwell 2 seconds for spindle to reach speed",
            f"G0 Z{self.safe_height}    ; Move to safe height",
            ""
        ]
        return "\n".join(header)

    def generate_gcode_footer(self) -> str:
        """Generate G-code footer with shutdown commands"""
        footer = [
            "",
            f"G0 Z{self.safe_height}    ; Move to safe height",
            "M5          ; Stop spindle",
            "G0 X0 Y0    ; Return to origin",
            "M2          ; Program end",
            ""
        ]
        return "\n".join(footer)

    def generate_tool_change(self, operation: str, tool: ToolPreset) -> List[str]:
        """Generate G-code for tool change"""
        return [
            "",
            f"; ========== TOOL CHANGE: {operation} ==========",
            f"; Tool: {tool.tool_diameter} mm",
            f"G0 Z{self.safe_height}    ; Move to safe height",
            "M5          ; Stop spindle",
            "G0 X0 Y0    ; Move to tool change position",
            f"M0          ; Pause for tool change - {operation}",
            f"M3 S{tool.spindle_speed}  ; Start spindle",
            "G4 P2       ; Dwell for spindle",
            ""
        ]

    def render_gerber_to_bitmap(self, gerber_file: str) -> Tuple[np.ndarray, Tuple[float, float, float, float]]:
        """Render Gerber file to a bitmap image using pygerber.
        Returns (bitmap, gerber_bounds) where gerber_bounds is (min_x, min_y, max_x, max_y) in mm."""
        from io import BytesIO

        try:
            gf = GerberFile.from_file(
                gerber_file,
                file_type=FileTypeEnum.INFER_FROM_EXTENSION
            )
            parsed_file = gf.parse()

            # Extract the actual Gerber coordinate bounds
            info = parsed_file.get_info()
            gerber_bounds = (
                float(info.min_x_mm),
                float(info.min_y_mm),
                float(info.max_x_mm),
                float(info.max_y_mm),
            )
            print(f"Gerber bounds: X={gerber_bounds[0]:.4f}-{gerber_bounds[2]:.4f} mm, "
                  f"Y={gerber_bounds[1]:.4f}-{gerber_bounds[3]:.4f} mm")

            dpmm = int(self.dpi / 25.4)
            buffer = BytesIO()
            parsed_file.render_raster(
                destination=buffer,
                dpmm=dpmm,
                pixel_format=PixelFormatEnum.RGBA,
                image_format=ImageFormatEnum.PNG,
            )

            buffer.seek(0)
            pil_image = Image.open(buffer)
            pil_image = pil_image.convert('L')
            img_array = np.array(pil_image)

            return img_array, gerber_bounds

        except Exception as e:
            print(f"Error rendering Gerber file {gerber_file}: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    def smooth_path(self, path: np.ndarray, tolerance: float = 0.5) -> np.ndarray:
        """Smooth a path using Douglas-Peucker algorithm"""
        from skimage.measure import approximate_polygon
        if len(path) < 3:
            return path
        return approximate_polygon(path, tolerance=tolerance)

    def get_trace_bounds_from_bitmap(self, bitmap: np.ndarray,
                                     gerber_bounds: Tuple[float, float, float, float]
                                     ) -> Tuple[float, float, float, float]:
        """Get bounding box of traces from bitmap (min_x, min_y, max_x, max_y) in mm,
        mapped back to absolute Gerber coordinates."""
        val_min, val_max = bitmap.min(), bitmap.max()
        threshold = val_min + (val_max - val_min) * 0.4
        binary = bitmap > threshold

        rows, cols = np.where(binary)
        if len(rows) == 0:
            return gerber_bounds

        gb_min_x, gb_min_y, gb_max_x, gb_max_y = gerber_bounds
        scale_factor = 25.4 / self.dpi

        # Bitmap pixel coords to mm, then offset by Gerber origin
        min_x = cols.min() * scale_factor + gb_min_x
        max_x = cols.max() * scale_factor + gb_min_x
        # Y-axis is flipped: bitmap row 0 = top = max Y in Gerber
        min_y = gb_max_y - rows.max() * scale_factor
        max_y = gb_max_y - rows.min() * scale_factor

        return (min_x, min_y, max_x, max_y)

    def bitmap_to_toolpaths(self, bitmap: np.ndarray,
                            gerber_bounds: Tuple[float, float, float, float],
                            erosion_px: float = 0
                            ) -> List[List[Tuple[float, float]]]:
        """Convert bitmap to toolpaths using contour detection.
        Coordinates are mapped back to absolute Gerber coordinates using gerber_bounds.
        erosion_px: shrink copper region by this many pixels before contouring."""
        from skimage import measure, morphology

        val_min, val_max = bitmap.min(), bitmap.max()
        threshold = val_min + (val_max - val_min) * 0.4
        binary = bitmap > threshold

        if erosion_px > 0:
            disk_r = max(1, round(erosion_px))
            binary = morphology.binary_dilation(binary, morphology.disk(disk_r))

        pad_size = 2
        binary = np.pad(binary, pad_size, mode='constant', constant_values=False)

        binary = morphology.closing(binary, morphology.disk(1))
        binary = morphology.remove_small_objects(binary, max_size=10)
        binary = morphology.remove_small_holes(binary, max_size=10)

        contours = measure.find_contours(binary.astype(float), 0.5)
        contours = [contour - pad_size for contour in contours]

        scale_factor = 25.4 / self.dpi
        smooth_tolerance = max(0.5, self.dpi / 2000)
        gb_min_x, gb_min_y, gb_max_x, gb_max_y = gerber_bounds

        paths = []
        for contour in contours:
            smoothed = self.smooth_path(contour, tolerance=smooth_tolerance)
            # point[1] = column = X, point[0] = row = Y
            # Y-axis flipped: bitmap row 0 = top = max Y in Gerber
            path = [(point[1] * scale_factor + gb_min_x,
                     gb_max_y - point[0] * scale_factor)
                    for point in smoothed]
            if len(path) >= 2:
                paths.append(path)

        return paths

    def generate_alignment_mark_gcode(self, cx: float, cy: float,
                                       tool, cut_depth: float,
                                       laser: bool = False) -> List[str]:
        """Generate G-code for an alignment mark: X crosshair inside a 4mm circle.
        cx, cy is the mark centre in absolute coordinates.
        For milling, cut_depth is the Z plunge depth (positive mm).
        For laser, laser=True omits Z moves and uses S power instead."""
        r = 2.0                    # circle radius → 4mm diameter (≤5mm limit)
        arm = r / (2 ** 0.5)      # arm half-length so endpoints touch the circle

        lines = [f"; Alignment mark  centre=({cx:.3f},{cy:.3f})  diam=4mm"]

        if laser:
            power = tool.power
            feed = tool.feed_rate
            # X arm 1: lower-left → upper-right
            lines.append(f"G0 X{cx - arm:.4f} Y{cy - arm:.4f}")
            lines.append(f"G1 X{cx + arm:.4f} Y{cy + arm:.4f} S{power} F{feed}")
            lines.append(f"G1 X{cx + arm:.4f} Y{cy + arm:.4f} S0")
            # X arm 2: upper-left → lower-right
            lines.append(f"G0 X{cx - arm:.4f} Y{cy + arm:.4f}")
            lines.append(f"G1 X{cx + arm:.4f} Y{cy - arm:.4f} S{power} F{feed}")
            lines.append(f"G1 X{cx + arm:.4f} Y{cy - arm:.4f} S0")
            # Full circle (CCW), start/end at left-most point
            lines.append(f"G0 X{cx - r:.4f} Y{cy:.4f}")
            lines.append(f"G3 X{cx - r:.4f} Y{cy:.4f} I{r:.4f} J0 S{power} F{feed}")
            lines.append(f"G1 X{cx - r:.4f} Y{cy:.4f} S0")
        else:
            feed = tool.feed_rate
            plunge = tool.plunge_rate
            safe_h = self.safe_height
            depth = -abs(cut_depth)
            # X arm 1: lower-left → upper-right
            lines.append(f"G0 X{cx - arm:.4f} Y{cy - arm:.4f} Z{safe_h}")
            lines.append(f"G1 Z{depth:.4f} F{plunge}")
            lines.append(f"G1 X{cx + arm:.4f} Y{cy + arm:.4f} F{feed}")
            lines.append(f"G0 Z{safe_h}")
            # X arm 2: upper-left → lower-right
            lines.append(f"G0 X{cx - arm:.4f} Y{cy + arm:.4f}")
            lines.append(f"G1 Z{depth:.4f} F{plunge}")
            lines.append(f"G1 X{cx + arm:.4f} Y{cy - arm:.4f} F{feed}")
            lines.append(f"G0 Z{safe_h}")
            # Full circle (CCW), start/end at left-most point
            lines.append(f"G0 X{cx - r:.4f} Y{cy:.4f}")
            lines.append(f"G1 Z{depth:.4f} F{plunge}")
            lines.append(f"G3 X{cx - r:.4f} Y{cy:.4f} I{r:.4f} J0 F{feed}")
            lines.append(f"G0 Z{safe_h}")

        return lines

    def process_traces(self, bitmap: np.ndarray,
                       gerber_bounds: Tuple[float, float, float, float],
                       board_bounds: Tuple[float, float, float, float] = None) -> List[str]:
        """Generate G-code for isolation routing of traces"""
        tool = self.isolation_tool
        gcode_lines = ["; Isolation routing"]

        scale_factor = 25.4 / self.dpi

        # Pad bitmap to board bounds so traces at the edges of the copper region
        # get fully closed contours and coordinates align with edge cuts / drill layers.
        if board_bounds is not None:
            bitmap, gerber_bounds = self._pad_bitmap_to_bounds(
                bitmap, gerber_bounds, board_bounds)
            print(f"  Bitmap padded to board bounds: "
                  f"X={board_bounds[0]:.2f}-{board_bounds[2]:.2f} mm, "
                  f"Y={board_bounds[1]:.2f}-{board_bounds[3]:.2f} mm")

        if tool.isolation_border > 0:
            n_extra = max(0, int(np.ceil(tool.isolation_border / tool.step_over)))
        else:
            n_extra = max(0, tool.passes - 1)

        for pass_num in range(n_extra + 1):
            erosion_mm = pass_num * tool.step_over
            erosion_px = erosion_mm / scale_factor
            paths = self.bitmap_to_toolpaths(bitmap, gerber_bounds, erosion_px=erosion_px)
            label = "primary" if pass_num == 0 else f"border +{erosion_mm:.2f}mm"
            print(f"  Pass {pass_num + 1} ({label}): {len(paths)} contours")
            gcode_lines.append(f"; Isolation pass {pass_num + 1} ({label})")

            for path in paths:
                if len(path) < 2:
                    continue
                x, y = path[0]
                gcode_lines.append(f"G0 X{x:.4f} Y{y:.4f} Z{self.safe_height}")
                gcode_lines.append(f"G1 Z{-tool.cut_depth:.4f} F{tool.plunge_rate}")
                for x, y in path[1:]:
                    gcode_lines.append(f"G1 X{x:.4f} Y{y:.4f} F{tool.feed_rate}")
                gcode_lines.append(f"G0 Z{self.safe_height}")

            gcode_lines.append("")

        # Alignment mark: X-in-circle, 4mm diameter, cut at trace depth.
        # Placed 3.5mm outside the bottom-left board corner so it sits in
        # waste material and does not interfere with the board outline.
        if board_bounds is not None:
            mark_x = board_bounds[0] - 3.5
            mark_y = board_bounds[1] - 3.5
            print(f"  Alignment mark at ({mark_x:.2f}, {mark_y:.2f})")
            gcode_lines.extend(self.generate_alignment_mark_gcode(
                mark_x, mark_y, tool, tool.cut_depth, laser=False))
            gcode_lines.append("")

        return gcode_lines

    def generate_laser_gcode_header(self, tool) -> str:
        """Generate G-code header for laser operation (GRBL laser mode, $32=1)"""
        mode = "M4" if tool.dynamic_mode else "M3"
        return "\n".join([
            "; Laser G-code — requires GRBL laser mode ($32=1)",
            "G21         ; mm",
            "G90         ; absolute",
            "G94         ; feed per minute",
            f"{mode} S0   ; enable laser driver (power off)",
            "",
        ])

    def generate_laser_gcode_footer(self) -> str:
        """Generate G-code footer for laser operation"""
        return "\n".join(["", "M5    ; Laser off", "G0 X0 Y0", "M2", ""])

    def detect_pads_and_traces(self, bitmap: np.ndarray,
                               gerber_bounds: Tuple[float, float, float, float]):
        """Classify copper regions into pads and traces using connected component analysis.
        Returns (pad_mask, trace_mask) boolean arrays."""
        from skimage import measure

        val_min, val_max = bitmap.min(), bitmap.max()
        binary = bitmap > (val_min + (val_max - val_min) * 0.4)

        labeled = measure.label(binary)
        regions = measure.regionprops(labeled)
        scale_factor = 25.4 / self.dpi
        min_area_px = self.laser_tool.pad_min_area / (scale_factor ** 2)

        pad_mask = np.zeros_like(binary, dtype=bool)
        trace_mask = np.zeros_like(binary, dtype=bool)

        for region in regions:
            if (region.area > min_area_px
                    and region.eccentricity < self.laser_tool.pad_max_eccentricity
                    and region.solidity > 0.7):
                pad_mask[labeled == region.label] = True
            else:
                trace_mask[labeled == region.label] = True

        print(f"  Detected {measure.label(pad_mask).max()} pad region(s)")
        return pad_mask, trace_mask

    def generate_pad_fills_from_mask(self, mask_bitmap: np.ndarray,
                                     gerber_bounds: Tuple[float, float, float, float]) -> List[str]:
        """Generate raster fill G-code directly from a solder mask Gerber bitmap.
        Every bright region in the mask layer is a mask opening and gets filled."""
        from skimage import measure

        tool = self.laser_tool
        scale_factor = 25.4 / self.dpi
        gb_min_x, _, _, gb_max_y = gerber_bounds
        fill_step_px = max(1.0, tool.fill_line_spacing / scale_factor)

        val_min, val_max = mask_bitmap.min(), mask_bitmap.max()
        binary = mask_bitmap > (val_min + (val_max - val_min) * 0.4)

        labeled = measure.label(binary)
        regions = measure.regionprops(labeled)
        print(f"  Filling {len(regions)} mask opening(s) from solder mask layer")

        gcode_lines = ["; Laser pad fill from solder mask (raster)"]
        for region in regions:
            min_row, _, max_row, _ = region.bbox
            region_mask = (labeled == region.label)
            row = float(min_row)
            direction = 1
            while row < max_row:
                row_int = min(int(row), max_row - 1)
                cols = np.where(region_mask[row_int, :])[0]
                if len(cols) >= 2:
                    c_s, c_e = (cols[0], cols[-1]) if direction == 1 else (cols[-1], cols[0])
                    x_s = c_s * scale_factor + gb_min_x
                    x_e = c_e * scale_factor + gb_min_x
                    y = gb_max_y - row_int * scale_factor
                    gcode_lines.append(f"G0 X{x_s:.4f} Y{y:.4f}")
                    gcode_lines.append(f"G1 X{x_e:.4f} Y{y:.4f} S{tool.power} F{tool.feed_rate}")
                    direction *= -1
                row += fill_step_px
        return gcode_lines

    def generate_pad_fills(self, pad_mask: np.ndarray,
                           gerber_bounds: Tuple[float, float, float, float]) -> List[str]:
        """Generate boustrophedon raster fill G-code for pad regions"""
        from skimage import measure

        tool = self.laser_tool
        scale_factor = 25.4 / self.dpi
        gb_min_x, _, gb_max_x, gb_max_y = gerber_bounds
        fill_step_px = max(1.0, tool.fill_line_spacing / scale_factor)

        gcode_lines = ["; Laser pad fill (raster)"]
        labeled = measure.label(pad_mask)
        for region in measure.regionprops(labeled):
            min_row, _, max_row, _ = region.bbox
            region_mask = (labeled == region.label)
            row = float(min_row)
            direction = 1
            while row < max_row:
                row_int = min(int(row), max_row - 1)
                cols = np.where(region_mask[row_int, :])[0]
                if len(cols) >= 2:
                    c_s, c_e = (cols[0], cols[-1]) if direction == 1 else (cols[-1], cols[0])
                    x_s = c_s * scale_factor + gb_min_x
                    x_e = c_e * scale_factor + gb_min_x
                    y = gb_max_y - row_int * scale_factor
                    gcode_lines.append(f"G0 X{x_s:.4f} Y{y:.4f}")
                    gcode_lines.append(f"G1 X{x_e:.4f} Y{y:.4f} S{tool.power} F{tool.feed_rate}")
                    direction *= -1
                row += fill_step_px
        return gcode_lines

    def _pad_bitmap_to_bounds(self, bitmap: np.ndarray,
                              gerber_bounds: Tuple[float, float, float, float],
                              target_bounds: Tuple[float, float, float, float]
                              ) -> Tuple[np.ndarray, Tuple[float, float, float, float]]:
        """Pad a bitmap with zeros so its coordinate space extends to target_bounds.
        Returns (padded_bitmap, new_gerber_bounds). target_bounds must be >= gerber_bounds."""
        scale_factor = 25.4 / self.dpi
        gb_min_x, gb_min_y, gb_max_x, gb_max_y = gerber_bounds
        tb_min_x, tb_min_y, tb_max_x, tb_max_y = target_bounds

        # Pixels to add on each side (image row 0 = Gerber max_y, so top/bottom are flipped)
        pad_left   = max(0, round((gb_min_x - tb_min_x) / scale_factor))
        pad_right  = max(0, round((tb_max_x - gb_max_x) / scale_factor))
        pad_top    = max(0, round((tb_max_y - gb_max_y) / scale_factor))
        pad_bottom = max(0, round((gb_min_y - tb_min_y) / scale_factor))

        padded = np.pad(bitmap, ((pad_top, pad_bottom), (pad_left, pad_right)),
                        mode='constant', constant_values=0)
        new_bounds = (
            gb_min_x - pad_left   * scale_factor,
            gb_min_y - pad_bottom * scale_factor,
            gb_max_x + pad_right  * scale_factor,
            gb_max_y + pad_top    * scale_factor,
        )
        return padded, new_bounds

    def process_laser(self, bitmap: np.ndarray,
                      gerber_bounds: Tuple[float, float, float, float],
                      mask_bitmap: np.ndarray = None,
                      mask_gerber_bounds: Tuple[float, float, float, float] = None,
                      board_bounds: Tuple[float, float, float, float] = None):
        """Generate laser G-code for solder mask removal.
        Returns (trace_lines, pad_lines) as separate lists for writing to separate files.
        If mask_bitmap is provided it is used directly for pad fills using its own
        mask_gerber_bounds; otherwise pad regions are detected heuristically from the
        copper layer bitmap."""
        tool = self.laser_tool

        if tool.trace_border_passes > 0:
            if board_bounds is None:
                raise ValueError(
                    f"trace_border_passes={tool.trace_border_passes} requires board boundary "
                    "information, but none is available.\n"
                    "Supply an edge cuts file (-e) or a copper traces file (-t) so a board "
                    "boundary can be established, or set trace_border_passes to 0."
                )
            bitmap, gerber_bounds = self._pad_bitmap_to_bounds(
                bitmap, gerber_bounds, board_bounds)
            print(f"  Bitmap padded to board bounds: "
                  f"X={board_bounds[0]:.2f}-{board_bounds[2]:.2f} mm, "
                  f"Y={board_bounds[1]:.2f}-{board_bounds[3]:.2f} mm")

        scale_factor = 25.4 / self.dpi
        trace_lines = ["; Laser trace isolation contours"]
        for pass_num in range(tool.trace_border_passes + 1):
            dilation_mm = pass_num * tool.fill_line_spacing
            dilation_px = dilation_mm / scale_factor
            paths = self.bitmap_to_toolpaths(bitmap, gerber_bounds, erosion_px=dilation_px)
            label = "edge" if pass_num == 0 else f"outside +{dilation_mm:.2f}mm"
            print(f"  Trace border pass {pass_num + 1} ({label}): {len(paths)} contour(s)")
            trace_lines.append(f"; Trace border pass {pass_num + 1} ({label})")
            for path in paths:
                if len(path) < 2:
                    continue
                x, y = path[0]
                trace_lines.append(f"G0 X{x:.4f} Y{y:.4f}")
                for x, y in path:
                    trace_lines.append(f"G1 X{x:.4f} Y{y:.4f} S{tool.power} F{tool.feed_rate}")
                trace_lines.append(f"G1 X{x:.4f} Y{y:.4f} S0")

        if mask_bitmap is not None:
            pad_bounds = mask_gerber_bounds if mask_gerber_bounds is not None else gerber_bounds
            pad_lines = self.generate_pad_fills_from_mask(mask_bitmap, pad_bounds)
        else:
            pad_mask, _ = self.detect_pads_and_traces(bitmap, gerber_bounds)
            pad_lines = self.generate_pad_fills(pad_mask, gerber_bounds) if np.any(pad_mask) else []

        # Alignment mark appended to trace file so it is cut with the same
        # tool/power settings as the trace borders.
        if board_bounds is not None:
            mark_x = board_bounds[0] - 3.5
            mark_y = board_bounds[1] - 3.5
            print(f"  Alignment mark at ({mark_x:.2f}, {mark_y:.2f})")
            trace_lines.append("")
            trace_lines.extend(self.generate_alignment_mark_gcode(
                mark_x, mark_y, tool, 0, laser=True))

        return trace_lines, pad_lines

    def parse_edge_cuts_to_outline(self, bitmap: np.ndarray,
                                   gerber_bounds: Tuple[float, float, float, float]
                                   ) -> List[Tuple[float, float]]:
        """Parse edge cuts bitmap and return board outline in absolute Gerber coordinates."""
        from skimage import measure

        val_min, val_max = bitmap.min(), bitmap.max()
        threshold = val_min + (val_max - val_min) * 0.4
        binary = bitmap > threshold

        contours = measure.find_contours(binary.astype(float), 0.5)

        if not contours:
            return []

        largest_contour = max(contours, key=len)
        smoothed = self.smooth_path(largest_contour, tolerance=1.0)
        scale_factor = 25.4 / self.dpi
        gb_min_x, gb_min_y, gb_max_x, gb_max_y = gerber_bounds

        outline = [(point[1] * scale_factor + gb_min_x,
                    gb_max_y - point[0] * scale_factor)
                   for point in smoothed]

        return outline

    def impute_edge_cuts(self, trace_bounds: Tuple[float, float, float, float]) -> List[Tuple[float, float]]:
        """Generate rectangular board outline from trace bounds plus margin"""
        min_x, min_y, max_x, max_y = trace_bounds
        margin = self.edge_margin

        outline = [
            (min_x - margin, min_y - margin),
            (max_x + margin, min_y - margin),
            (max_x + margin, max_y + margin),
            (min_x - margin, max_y + margin),
            (min_x - margin, min_y - margin),
        ]

        return outline

    def process_edge_cuts(self, outline: List[Tuple[float, float]]) -> List[str]:
        """Generate G-code for board cutout"""
        if not outline:
            return []

        tool = self.edge_cuts_tool
        gcode_lines = [
            "; Board cutout",
            f"; Total depth: {tool.total_depth} mm",
        ]

        passes_needed = max(1, int(np.ceil(tool.total_depth / tool.cut_depth)))

        for pass_num in range(passes_needed):
            current_depth = min((pass_num + 1) * tool.cut_depth, tool.total_depth)
            gcode_lines.append(f"; Cutout pass {pass_num + 1} (depth: {current_depth:.2f} mm)")

            x, y = outline[0]
            gcode_lines.append(f"G0 X{x:.4f} Y{y:.4f} Z{self.safe_height}")
            gcode_lines.append(f"G1 Z{-current_depth:.4f} F{tool.plunge_rate}")

            for x, y in outline[1:]:
                gcode_lines.append(f"G1 X{x:.4f} Y{y:.4f} F{tool.feed_rate}")

            gcode_lines.append(f"G0 Z{self.safe_height}")

        return gcode_lines

    def parse_drill_file(self, drill_file: str) -> List[Tuple[float, float, float]]:
        """Parse Excellon drill file and return list of (x, y, diameter) holes"""
        holes = []

        try:
            with open(drill_file, 'r') as f:
                content = f.read()

            # Parse tool definitions (T01C0.8 = tool 1, 0.8mm diameter)
            tool_diameters = {}
            tool_pattern = re.compile(r'T(\d+)C([\d.]+)')
            for match in tool_pattern.finditer(content):
                tool_num = int(match.group(1))
                diameter = float(match.group(2))
                tool_diameters[tool_num] = diameter

            # Parse coordinates
            current_tool = None
            # Excellon format can be INCH or METRIC
            unit_scale = 1.0  # Assume mm by default

            if 'INCH' in content.upper():
                unit_scale = 25.4
            elif 'METRIC' in content.upper() or 'M71' in content:
                unit_scale = 1.0

            lines = content.split('\n')
            for line in lines:
                line = line.strip()

                # Tool selection
                tool_select = re.match(r'^T(\d+)$', line)
                if tool_select:
                    current_tool = int(tool_select.group(1))
                    continue

                # Coordinate (X123Y456 format)
                coord_match = re.match(r'^X([-\d.]+)Y([-\d.]+)', line)
                if coord_match and current_tool is not None:
                    x = float(coord_match.group(1))
                    y = float(coord_match.group(2))

                    # Handle integer format (divide by 10000 for 2.4 format)
                    if '.' not in coord_match.group(1):
                        x = x / 10000.0
                    if '.' not in coord_match.group(2):
                        y = y / 10000.0

                    x *= unit_scale
                    y *= unit_scale

                    diameter = tool_diameters.get(current_tool, self.drill_tool.tool_diameter)
                    holes.append((x, y, diameter))

            print(f"Found {len(holes)} drill holes")
            return holes

        except Exception as e:
            print(f"Error parsing drill file: {e}")
            return []

    def process_drill_holes(self, holes: List[Tuple[float, float, float]]) -> List[str]:
        """Generate G-code for drilling holes"""
        if not holes:
            return []

        tool = self.drill_tool
        gcode_lines = [
            "; Drilling",
            f"; Total depth: {tool.total_depth} mm",
        ]

        # Group holes by diameter for efficiency
        holes_by_diameter = {}
        for x, y, d in holes:
            if d not in holes_by_diameter:
                holes_by_diameter[d] = []
            holes_by_diameter[d].append((x, y))

        for diameter, hole_list in sorted(holes_by_diameter.items()):
            gcode_lines.append(f"; Holes: {diameter:.2f} mm diameter ({len(hole_list)} holes)")

            for x, y in hole_list:
                gcode_lines.append(f"G0 X{x:.4f} Y{y:.4f} Z{self.safe_height}")

                if tool.cut_depth > 0 and tool.cut_depth < tool.total_depth:
                    # Peck drilling
                    current_depth = 0
                    while current_depth < tool.total_depth:
                        current_depth = min(current_depth + tool.cut_depth, tool.total_depth)
                        gcode_lines.append(f"G1 Z{-current_depth:.4f} F{tool.plunge_rate}")
                        gcode_lines.append(f"G0 Z{tool.retract_height}")
                    gcode_lines.append(f"G0 Z{self.safe_height}")
                else:
                    # Single plunge
                    gcode_lines.append(f"G1 Z{-tool.total_depth:.4f} F{tool.plunge_rate}")
                    gcode_lines.append(f"G0 Z{self.safe_height}")

        return gcode_lines

    def generate_edge_cuts_gerber(self, outline: List[Tuple[float, float]], output_file: str):
        """Generate a Gerber file for the board edge cuts"""
        gerber_lines = [
            "G04 Edge cuts generated by Gerber to G-code converter*",
            "%FSLAX36Y36*%",
            "%MOIN*%",
            "%ADD10C,0.01*%",
            "D10*",
            "G01*",
        ]

        for i, (x, y) in enumerate(outline):
            x_inch = x / 25.4
            y_inch = y / 25.4
            x_gerber = int(x_inch * 1000000)
            y_gerber = int(y_inch * 1000000)

            if i == 0:
                gerber_lines.append(f"X{x_gerber}Y{y_gerber}D02*")
            else:
                gerber_lines.append(f"X{x_gerber}Y{y_gerber}D01*")

        gerber_lines.append("M02*")

        with open(output_file, 'w') as f:
            f.write('\n'.join(gerber_lines))

        print(f"Edge cuts Gerber written to {output_file}")

    def convert(self, traces_file: str = None, edge_cuts_file: str = None,
                drill_file: str = None, output_file: str = None,
                generate_edge_cuts: str = None, laser_layer: str = None,
                mask_layer: str = None):
        """Main conversion process"""

        self.traces_file = traces_file
        self.edge_cuts_file = edge_cuts_file
        self.drill_file = drill_file
        self.output_file = output_file or 'output.nc'

        operations = []
        gcode_sections = {}

        # Phase 1: Render trace bitmap (geometry only; G-code generated after board
        # bounds are known so the bitmap can be padded to the full board extent).
        trace_bitmap = None
        trace_gerber_bounds = None
        if traces_file and os.path.exists(traces_file):
            print(f"\n=== Processing traces: {traces_file} ===")
            trace_bitmap, trace_gerber_bounds = self.render_gerber_to_bitmap(traces_file)
            self.trace_bounds = self.get_trace_bounds_from_bitmap(
                trace_bitmap, trace_gerber_bounds)
            print(f"Trace bounds: X={self.trace_bounds[0]:.2f}-{self.trace_bounds[2]:.2f} mm, "
                  f"Y={self.trace_bounds[1]:.2f}-{self.trace_bounds[3]:.2f} mm")

        # Phase 2: Determine board outline before generating isolation G-code so the
        # trace bitmap can be padded to board bounds (ensures edge paths are complete
        # and all layers share the same coordinate origin).
        if edge_cuts_file and os.path.exists(edge_cuts_file):
            print(f"\n=== Processing edge cuts: {edge_cuts_file} ===")
            ec_bitmap, ec_gerber_bounds = self.render_gerber_to_bitmap(edge_cuts_file)
            self.board_outline = self.parse_edge_cuts_to_outline(ec_bitmap, ec_gerber_bounds)
            print(f"Loaded board outline with {len(self.board_outline)} points")
        elif self.trace_bounds:
            print(f"\n=== Imputing edge cuts from trace bounds ===")
            self.board_outline = self.impute_edge_cuts(self.trace_bounds)
            width = self.trace_bounds[2] - self.trace_bounds[0] + 2 * self.edge_margin
            height = self.trace_bounds[3] - self.trace_bounds[1] + 2 * self.edge_margin
            print(f"Imputed board size: {width:.2f} x {height:.2f} mm")

        # Generate edge cuts Gerber if requested
        if generate_edge_cuts and self.board_outline:
            self.generate_edge_cuts_gerber(self.board_outline, generate_edge_cuts)

        # Compute board bounding box once; reused for isolation padding and laser passes.
        board_bounds = None
        if self.board_outline:
            xs = [p[0] for p in self.board_outline]
            ys = [p[1] for p in self.board_outline]
            board_bounds = (min(xs), min(ys), max(xs), max(ys))

        # Phase 3: Generate isolation G-code now that board bounds are known.
        if trace_bitmap is not None:
            gcode_sections['isolation'] = self.process_traces(
                trace_bitmap, trace_gerber_bounds, board_bounds)
            operations.append('isolation')

        # Add edge cuts to operations if we have an outline
        if self.board_outline:
            gcode_sections['edge_cuts'] = self.process_edge_cuts(self.board_outline)
            operations.append('edge_cuts')

        # Process drill file
        if drill_file and os.path.exists(drill_file):
            print(f"\n=== Processing drill file: {drill_file} ===")
            holes = self.parse_drill_file(drill_file)
            if holes:
                gcode_sections['drill'] = self.process_drill_holes(holes)
                operations.append('drill')

        # Process laser etching layer (always written to separate files)
        if laser_layer and os.path.exists(laser_layer):
            print(f"\n=== Processing laser etching layer: {laser_layer} ===")
            bitmap, gerber_bounds = self.render_gerber_to_bitmap(laser_layer)

            mask_bitmap = None
            mask_gerber_bounds = None
            if mask_layer and os.path.exists(mask_layer):
                print(f"  Using solder mask layer: {mask_layer}")
                mask_bitmap, mask_gerber_bounds = self.render_gerber_to_bitmap(mask_layer)
            elif mask_layer:
                print(f"Warning: Solder mask file not found: {mask_layer}")
                print("  Falling back to copper layer heuristic pad detection")
            else:
                print("Warning: No solder mask file provided (-m / --mask-layer).")
                print("  Falling back to heuristic pad detection from the copper layer.")
                print("  For best results, supply the solder mask Gerber (.gts / .gbs).")

            trace_lines, pad_lines = self.process_laser(
                bitmap, gerber_bounds, mask_bitmap, mask_gerber_bounds, board_bounds)
            header = self.generate_laser_gcode_header(self.laser_tool)
            footer = self.generate_laser_gcode_footer()

            traces_filename = f"{self.file_prefix}_laser_traces.nc"
            with open(traces_filename, 'w') as f:
                f.write(header)
                f.write('\n'.join(trace_lines))
                f.write(footer)
            print(f"Laser trace G-code written to {traces_filename}")

            if pad_lines:
                pads_filename = f"{self.file_prefix}_laser_pads.nc"
                with open(pads_filename, 'w') as f:
                    f.write(header)
                    f.write('\n'.join(pad_lines))
                    f.write(footer)
                print(f"Laser pad G-code written to {pads_filename}")
            else:
                print("  No pads detected — skipping pad fill file")
        elif laser_layer:
            print(f"Warning: Laser layer file not found: {laser_layer}")

        # Generate output
        if self.separate_files:
            self._write_separate_files(gcode_sections)
        else:
            self._write_combined_file(operations, gcode_sections)

    def _write_separate_files(self, gcode_sections: Dict[str, List[str]]):
        """Write separate G-code files for each operation"""
        tools = {
            'isolation': self.isolation_tool,
            'edge_cuts': self.edge_cuts_tool,
            'drill': self.drill_tool
        }

        for operation, gcode_lines in gcode_sections.items():
            if not gcode_lines:
                continue

            filename = f"{self.file_prefix}_{operation}.nc"
            tool = tools[operation]

            with open(filename, 'w') as f:
                f.write(self.generate_gcode_header(operation, tool))
                f.write('\n'.join(gcode_lines))
                f.write(self.generate_gcode_footer())

            print(f"Written {filename}")

    def _write_combined_file(self, operations: List[str], gcode_sections: Dict[str, List[str]]):
        """Write combined G-code file with tool changes"""
        tools = {
            'isolation': self.isolation_tool,
            'edge_cuts': self.edge_cuts_tool,
            'drill': self.drill_tool
        }

        gcode = []

        # Header for first operation
        if operations:
            first_op = operations[0]
            gcode.append(self.generate_gcode_header(first_op, tools[first_op]))
            gcode.extend(gcode_sections[first_op])

            # Subsequent operations with tool changes
            for operation in operations[1:]:
                if operation in gcode_sections and gcode_sections[operation]:
                    gcode.extend(self.generate_tool_change(operation, tools[operation]))
                    gcode.extend(gcode_sections[operation])

        gcode.append(self.generate_gcode_footer())

        with open(self.output_file, 'w') as f:
            f.write('\n'.join(gcode))

        print(f"\nG-code written to {self.output_file}")
        print(f"Operations: {', '.join(operations)}")


def main():
    parser = argparse.ArgumentParser(
        description='Convert Gerber files to GRBL G-code for PCB milling',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic isolation routing
  %(prog)s -t traces.gbr -o output.nc

  # Full PCB with all files
  %(prog)s -t traces.gbr -e edges.gbr -d holes.drl -o output.nc

  # Use custom config file
  %(prog)s -t traces.gbr --config my_config.yaml

  # Generate separate files for each operation
  %(prog)s -t traces.gbr -e edges.gbr --separate
        """
    )

    # Input files
    parser.add_argument('-t', '--traces', type=str,
                        help='Copper traces Gerber file (.gbr, .gtl, .gbl)')
    parser.add_argument('-e', '--edge-cuts', type=str,
                        help='Edge cuts Gerber file for board outline')
    parser.add_argument('-d', '--drill', type=str,
                        help='Excellon drill file (.drl, .xln)')
    parser.add_argument('-l', '--laser-layer', type=str,
                        help='Copper layer Gerber for laser solder mask removal (.gtl, .gbr)')
    parser.add_argument('-m', '--mask-layer', type=str,
                        help='Solder mask Gerber for accurate pad fill (.gts top, .gbs bottom)')

    # Legacy positional argument support
    parser.add_argument('input', nargs='?',
                        help='Input Gerber file (legacy, use -t instead)')

    # Output
    parser.add_argument('-o', '--output', type=str, default='output.nc',
                        help='Output G-code file (default: output.nc)')
    parser.add_argument('--separate', action='store_true',
                        help='Generate separate files for each operation')
    parser.add_argument('--generate-edge-cuts', type=str,
                        help='Output file for generated edge cuts Gerber')

    # Configuration
    parser.add_argument('--config', type=str, default='config.yaml',
                        help='YAML configuration file (default: config.yaml)')

    # Quick overrides (optional, config file takes precedence)
    parser.add_argument('--edge-margin', type=float,
                        help='Override edge margin for imputed board outline (mm)')
    parser.add_argument('--dpi', type=int,
                        help='Override DPI for Gerber rendering')

    args = parser.parse_args()

    # Handle legacy positional argument
    traces_file = args.traces or args.input
    if not traces_file and not args.edge_cuts and not args.drill and not args.laser_layer and not args.mask_layer:
        parser.print_help()
        print("\nError: At least one input file is required (-t, -e, or -d)")
        sys.exit(1)

    # Create converter
    converter = GerberToGcode(args.config)

    # Apply command-line overrides
    if args.edge_margin is not None:
        converter.edge_margin = args.edge_margin
    if args.dpi is not None:
        converter.dpi = args.dpi
    if args.separate:
        converter.separate_files = True

    # Run conversion
    converter.convert(
        traces_file=traces_file,
        edge_cuts_file=args.edge_cuts,
        drill_file=args.drill,
        output_file=args.output,
        generate_edge_cuts=args.generate_edge_cuts,
        laser_layer=args.laser_layer,
        mask_layer=args.mask_layer
    )


if __name__ == '__main__':
    main()
