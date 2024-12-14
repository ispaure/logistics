
import wrappers.philipsHueWrapper as philipsHueWrapper

# Turn on lights
philipsHueWrapper.set_group_state('Living Room', True)
# Set Intensity
philipsHueWrapper.set_group_brightness('Living Room', 20)
# Set lights yellow-ish but not too saturated
philipsHueWrapper.set_group_color(group_name='Living Room', hue=10000, saturation=150)
