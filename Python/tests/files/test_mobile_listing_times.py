"""Fast local listing timestamps retain local offsets across DST transitions."""

# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from commonUtils.testing.stages import TestStage

TEST_STAGE = TestStage.REGRESSION
from datetime import datetime
import os
import time
import unittest

from services.documents.locations import _modified_time


class ListingTimeTests(unittest.TestCase):
    @unittest.skipUnless(hasattr(time, 'tzset'), 'Host cannot select a timezone')
    def test_dst_and_half_hour_offsets_match_existing_listing_format(self):
        previous = os.environ.get('TZ')
        try:
            for zone in ('America/Toronto', 'America/St_Johns', 'Asia/Kolkata', 'UTC'):
                os.environ['TZ'] = zone
                time.tzset()
                by_second = {}
                for timestamp in (0, 1705320000.125, 1721044800, 1710053999, 1710054000,
                                  1710053999.9999998, 1730613599.9999998, 1710054000.25, -0.0000002):
                    with self.subTest(zone=zone, timestamp=timestamp):
                        expected = datetime.fromtimestamp(timestamp).astimezone().isoformat(sep=' ', timespec='seconds')
                        self.assertEqual(_modified_time(timestamp), expected)
                        self.assertEqual(_modified_time(timestamp, by_second=by_second), expected)
        finally:
            if previous is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = previous
            time.tzset()


if __name__ == '__main__':
    unittest.main()
