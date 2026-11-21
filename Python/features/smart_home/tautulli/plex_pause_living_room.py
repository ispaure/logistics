# AUTHORSHIP INFORMATION

__author__ = "Marc-André Voyer"
__copyright__ = "Copyright (C) 2026, Marc-André Voyer"
__license__ = "MIT License"
__maintainer__ = "Marc-André Voyer"
__email__ = "marcandre.voyer@gmail.com"
__status__ = "Production"

from features.smart_home.philips_hue import api as philips_hue

# Turn on lights
philips_hue.set_group_state('Living Room', True)

# Set Intensity
philips_hue.set_group_brightness('Living Room', 20)

# Set lights yellow-ish but not too saturated
philips_hue.set_group_color(group_name='Living Room', hue=10000, saturation=150)