#!/usr/bin/env sh
#
# Bash script to setup linux-gpib for a National Instruments
# GPIB-USB-HS dongle.

echo "Setting up the /etc/gpib.conf file for the GPIB-USB-HS dongle."

grep "GPIB.CONF IEEE488 library config file" /etc/gpib.conf && sudo mv /etc/gpib.conf /etc/gpib.conf.example
cat << EOF | sudo tee /etc/gpib.conf
interface {
        minor = 0
        board_type = "ni_usb_b"
        pad = 0
        master = yes
}
EOF
sudo ldconfig

echo "Setup complete!"
