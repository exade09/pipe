import base64
import struct
import unittest

from pipe.market.curve_candles import TRADE_EVENT_DISCRIMINATOR, _one_minute, _trade_from_logs


class CurveCandleTests(unittest.TestCase):
    def test_decodes_published_trade_event_prefix(self):
        raw = bytearray(113)
        raw[:8] = TRADE_EVENT_DISCRIMINATOR
        struct.pack_into("<Q", raw, 40, 2_000_000_000)
        struct.pack_into("<Q", raw, 48, 100_000_000)
        struct.pack_into("<q", raw, 89, 1_790_000_001)
        struct.pack_into("<Q", raw, 97, 10_000_000_000)
        struct.pack_into("<Q", raw, 105, 500_000_000_000)
        log = "Program data: " + base64.b64encode(raw).decode("ascii")

        point = _trade_from_logs([log], decimals=6, sol_usd=200.0)

        self.assertEqual(point["t"], 1_790_000_001)
        self.assertAlmostEqual(point["price"], 0.004)
        self.assertAlmostEqual(point["volume"], 400.0)

    def test_aggregates_trade_points_into_real_ohlcv(self):
        bars = _one_minute(
            [
                {"t": 121, "price": 2.0, "volume": 4.0},
                {"t": 122, "price": 3.0, "volume": 5.0},
                {"t": 123, "price": 1.0, "volume": 6.0},
                {"t": 181, "price": 4.0, "volume": 7.0},
            ]
        )

        self.assertEqual(
            bars,
            [
                {"t": 120, "o": 2.0, "h": 3.0, "l": 1.0, "c": 1.0, "v": 15.0},
                {"t": 180, "o": 4.0, "h": 4.0, "l": 4.0, "c": 4.0, "v": 7.0},
            ],
        )


if __name__ == "__main__":
    unittest.main()
