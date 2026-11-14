# Control Philips Hue lights

Open **Smart Home** on desktop. Its initial room labels are placeholders until
you run discovery.

## Set up the bridge

Set **bridge_address_str** under **PhilipsHue** in Smart Home's Configuration.
Choose **Connect Bridge**, follow the bridge's pairing procedure if needed,
then choose **Find rooms**. Check the connection and authorization if no rooms
load.

## Send a light command

Choose a room and press a power, brightness or color button. Brightness and
color commands turn the selected group on. Color keeps its brightness. Room
names match exactly. Missing or duplicate names block the command.

## Tautulli automation

Configure Tautulli to run the scripts in **Python/features/smart_home/tautulli/**
with the Logistics Python environment and **Python/** on the import path.
They target a fixed Living Room group. Play and pause dim it. Stop restores
full brightness. Review the target before enabling them. A failed sequence can
leave commands that already ran in effect.

See [Using Logistics](../../../user/user.md) and [mobile availability](../user_mobile/user_mobile.md).
