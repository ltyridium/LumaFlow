import unittest

from core.timecode import format_time_ms, parse_timecode


class TimecodeTests(unittest.TestCase):
    def test_format_time_ms_uses_fixed_width_output(self):
        self.assertEqual("01:02:03.004", format_time_ms(3_723_004))

    def test_parse_full_timecode(self):
        self.assertEqual(3_723_004, parse_timecode("01:02:03.004"))

    def test_parse_minute_second_timecode(self):
        self.assertEqual(62_300, parse_timecode("01:02.3"))

    def test_parse_bare_milliseconds(self):
        self.assertEqual(12345, parse_timecode("12345"))

    def test_parse_invalid_timecode_raises(self):
        with self.assertRaises(ValueError):
            parse_timecode("abc")

    def test_parse_allows_normalized_overflow_components(self):
        self.assertEqual("00:02:10.500", format_time_ms(parse_timecode("1:70.5")))


if __name__ == "__main__":
    unittest.main()
