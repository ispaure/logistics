"""Fast local listing timestamps retain local offsets across DST transitions."""
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
                for timestamp in (0, 1705320000.125, 1721044800, 1710053999, 1710054000,
                                  1710053999.9999998, 1730613599.9999998):
                    with self.subTest(zone=zone, timestamp=timestamp):
                        expected = datetime.fromtimestamp(timestamp).astimezone().isoformat(sep=' ', timespec='seconds')
                        self.assertEqual(_modified_time(timestamp), expected)
        finally:
            if previous is None:
                os.environ.pop('TZ', None)
            else:
                os.environ['TZ'] = previous
            time.tzset()


if __name__ == '__main__':
    unittest.main()
