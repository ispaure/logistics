from features.smart_home.philips_hue import api as philips_hue

# Turn on lights
philips_hue.set_group_state('Living Room', True)

# # Set lights blue
# philips_hue.set_group_color(group_name='Living Room', hue=46014, saturation=254)
# # Set Intensity
# philips_hue.set_group_brightness('Living Room', 254)

# Set Intensity
philips_hue.set_group_brightness('Living Room', 20)

# Set lights yellow-ish but not too saturated
philips_hue.set_group_color(group_name='Living Room', hue=10000, saturation=150)