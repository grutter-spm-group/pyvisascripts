#!/bin/bash
#
# Bash script to set up linux-gpib.

# Original source: https://github.com/jakeogh/linux-gpib-installer/blob/master/
# linux_gpib_installer/_linux_gpib_installer_debian_11.sh
# Modified to:
# (a) Remove strict dependence on Debian 11. We now check that it is either Debian 11
# (bullseye) or Debian 12 (bookworm) 'based' (since I have tested on Ubuntu 22.04 and
# it works).
# (b) Adding an 'override' option: if it is not Debian 11 or 12 *but is still
# Debian-based*, the user can override by providing the '--override' command.
#
# https://gist.github.com/jonathanschilling/07defddc272fe35c7412d51dffa0bb6f

# Some safety checks
if [ -f /etc/debian_version ]; then
        echo "Debian-based distribution detected."
        if [ "$1" == "--override" ]; then
                echo "WARNING: User chose to override version check, continuing..."
        elif [ $( grep -e "bookworm" -e "bullseye" /etc/debian_version ) ]; then
                echo "Debian 11 or 12 based distribution detected, continuing..."
        else
                echo "This system is *not* a Debian 11 or 12 based distribution."
                echo "It has not been properly tested, but may still work."
                echo "If you wish to install anyway, provide input argument '--override'."
                exit 1 ;
        fi
else
        echo "This script does not currently support non-debian based systems. Exiting."
        exit 1 ;
fi

exit 1 ;

set -x

# module_path=$(python3 << EOF
# from importlib import resources
# with resources.path('linux_gpib_installer', '_linux_gpib_installer_debian_11.sh') as rp:
#         print(rp.parent.as_posix())
# EOF
# )

# echo "${module_path}"

# linux_gpib_repo="${module_path}/linux-gpib"
# test -d "${linux_gpib_repo}" || { echo "${linux_gpib_repo} is not a directory. Exiting." ; exit 1 ; }

PATH="/home/${USER}/.local/bin:${PATH}"
export PATH=${PATH}

echo "Creating temporary directory at ~/tmp/ for installation..."
userdir="/home/${USER}"
workdir="/home/${USER}/tmp"
mkdir "/home/${USER}/tmp" > /dev/null 2>&1
# test -d "${linux_gpib_repo}" || { echo "${workdir} is not a directory. Exiting." ; exit 1 ; }
cd "${workdir}" || exit 1

echo "Installing dependencies for kernel driver installation..."
sudo apt-get install devscripts dkms subversion git -y || exit 1
sudo apt-get install flex -y || exit 1  # needed for make
sudo apt-get install bison -y || exit 1
sudo apt-get install byacc -y || exit 1

# sudo apt-get install python3-pip -y || exit 1
# sudo apt-get install python3-usb -y || exit 1
# sudo apt-get install python3-serial -y || exit 1
#sudo apt-get install python3-pyvisa-py -y || exit 1  # pip installs a newer version

echo "Cloning git repository linux-gpib-dkms, which allows us to install linux-gpib via dkms..."
# https://github.com/drogenlied/linux-gpib-dkms
cd linux-gpib-dkms || { git clone https://github.com/drogenlied/linux-gpib-dkms || exit 1 ; }
cd linux-gpib-dkms && { git pull origin --ff-only || exit 1 ; }

cd "${workdir}" || exit 1

echo "Cloning the svn linux-gpib repository, so we can build it..."
test -e linux-gpib && rm -rf linux-gpib  # clear the bases
svn checkout https://svn.code.sf.net/p/linux-gpib/code/trunk linux-gpib || exit 1
# test -e linux-gpib || { cp -ar "${linux_gpib_repo}" . || exit 1 ; } # This copies from source, we don't have it in source

echo "Copying linux-gpib-dkms 'debian' directory into linux-gpib source code, for building..."
cp -ar "${workdir}"/linux-gpib-dkms/debian "${workdir}"/linux-gpib/linux-gpib-kernel/ || exit 1
cd linux-gpib/linux-gpib-kernel || exit 1

echo "Configuring linux-gpib source for building..."
debuild -i -us -uc -b || { echo "ERROR: debbuild failed!" ; exit 1 ; }
ls -al "${workdir}"/linux-gpib || exit 1
cd "${workdir}"/linux-gpib || exit 1
sudo  dpkg --install gpib-dkms_*_all.deb || exit 1
cd "${workdir}"/linux-gpib/linux-gpib-user || exit 1
test -x ./configure || { ./bootstrap || exit 1 ; }
./configure --sysconfdir=/etc || exit 1

echo "Making and installing kernel driver..."
make && sudo make install || exit 1

echo "Adding user to necessary user groups..."
sudo groupadd gpib # dont exit on $? != 0, groupadd exits 1 if the group already exists
sudo gpasswd -a "$USER" gpib || exit 1
sudo gpasswd -a "$USER" dialout || exit 1

echo "Moving to ~/ and deleting our working directory ~/tmp/..."
cd ${userdir}
rm -rf ${workdir}

echo "linux-gpib install completed! A reboot is required."
echo "Note: the /etc/gpib.confg file is the default one provided on install."
echo "It must be configured; please consult linux-gpib docs."
echo "If you are using the GPIB-USB-HS dongle, run setup_gpib_usb_hs.sh."
