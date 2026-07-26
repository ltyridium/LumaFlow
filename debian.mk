# Makefile for Debian packaging
#
# 1. Install required packages
# sudo apt install git-buildpackage dh-make dh-virtualenv quilt lintian build-essential libgomp1 virtualenv
#
# 2. Add new tag
#
# 3. Generate changelog
#
# make -f debian.mk changelog
#
# 4. Generate Debian package
#
# make -f debian.mk makedeb
#

changelog:
	# Set the following environment variables on your local machine
	# export DEBFULLNAME="YourName"
	# export DEBEMAIL="youremail@vanaheimr.vc"
	gbp dch --release

makedeb:
	gbp buildpackage -us -uc
