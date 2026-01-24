"""
ColorCalibration - Per PRD 5.2
Singleton class for mapping 4-bit hardware values (0-15) to 8-bit display values (0-255).
Solves the problem of LED Gamma differences between hardware and monitor display.
"""
import numpy as np


class ColorCalibration:
    """
    Singleton for color calibration between 4-bit hardware and 8-bit display.

    Per PRD 5.2:
    - Display LUT: Maps 0-15 input to 0-255 output (gamma corrected)
    - Used by RenderWorker via fancy indexing for performance
    - Provides reverse curve for effect generators
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True

        # Default gamma value for LED correction
        self.gamma = 2.2

        # Per-channel gains (1.0 = standard)
        # 三个通道灯光预览平衡补偿
        self.r_gain = 1
        self.g_gain = 0.7
        self.b_gain = 0.85

        # Generate independent LUTs for R, G, B channels
        self._regenerate_luts()

    def set_gains(self, r: float, g: float, b: float):
        """Set per-channel gain factors (e.g., 0.8, 1.0, 1.0)."""
        self.r_gain = r
        self.g_gain = g
        self.b_gain = b
        self._regenerate_luts()

    def get_gains(self):
        return {'r': self.r_gain, 'g': self.g_gain, 'b': self.b_gain}

    def _regenerate_luts(self):
        """Generate independent LUTs for R, G, B channels."""
        # Base input: 0-15
        input_vals = np.arange(16)
        normalized = input_vals / 15.0

        # Gamma correction
        corrected = np.power(normalized, 1.0 / self.gamma)

        # Apply gains and clip to 0-255
        self.r_lut = np.clip(corrected * 255 * self.r_gain, 0, 255).astype(np.uint8)
        self.g_lut = np.clip(corrected * 255 * self.g_gain, 0, 255).astype(np.uint8)
        self.b_lut = np.clip(corrected * 255 * self.b_gain, 0, 255).astype(np.uint8)

        # Reverse LUT (using Green LUT as reference for now)
        self._reverse_lut = self._generate_reverse_lut()

    def _generate_reverse_lut(self) -> np.ndarray:
        """Generate reverse LUT for mapping 8-bit to 4-bit."""
        # For each 8-bit value, find closest 4-bit value using Green channel as reference
        ref_lut = self.g_lut
        reverse = np.zeros(256, dtype=np.uint8)
        for i in range(256):
            distances = np.abs(ref_lut.astype(int) - i)
            reverse[i] = np.argmin(distances)
        return reverse

    # Backward compatibility properties
    @property
    def display_lut(self) -> np.ndarray:
        """Get the Green display LUT (standard reference)."""
        return self.g_lut

    @property
    def reverse_lut(self) -> np.ndarray:
        """Get the reverse LUT (8-bit to 4-bit)."""
        return self._reverse_lut

    def set_gamma(self, gamma: float):
        """Update gamma and regenerate LUTs."""
        self.gamma = gamma
        self._regenerate_luts()

    def to_display(self, value_4bit: np.ndarray) -> np.ndarray:
        """
        Convert 4-bit values to 8-bit display values using LUT.
        Defaults to Green LUT for generic conversion.
        """
        return self.g_lut[value_4bit]

    def to_hardware(self, value_8bit: np.ndarray) -> np.ndarray:
        """Convert 8-bit values to 4-bit hardware values."""
        return self._reverse_lut[np.clip(value_8bit, 0, 255).astype(np.uint8)]

    def set_custom_lut(self, lut: np.ndarray):
        """
        Set a custom display LUT (must be 16 uint8 values).
        Useful for manual calibration.
        """
        if len(lut) != 16:
            raise ValueError("LUT must have exactly 16 values")
        self._display_lut = np.array(lut, dtype=np.uint8)
        self._reverse_lut = self._generate_reverse_lut()


# Global singleton instance
color_calibration = ColorCalibration()
