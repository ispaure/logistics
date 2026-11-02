ARG FEDORA_IMAGE=fedora:44
FROM ${FEDORA_IMAGE}
RUN dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm
RUN dnf install -y git python3-pip mesa-libEGL mesa-libGL libxkbcommon dbus-libs fontconfig dejavu-sans-fonts dejavu-sans-mono-fonts glib2 libstdc++ pulseaudio-libs nspr nss alsa-lib libdrm libXcomposite libXdamage libXrandr libxkbfile libXtst libXScrnSaver cups-libs gtk3 tar gzip openssl-libs snappy minizip-ng-compat vlc-libs vlc-plugins-base vlc-plugin-ffmpeg vlc-plugins-extra libavcodec-freeworld && dnf clean all
RUN python3 -m pip install uv==0.12.18
