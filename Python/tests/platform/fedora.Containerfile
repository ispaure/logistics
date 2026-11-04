ARG FEDORA_IMAGE=fedora:44
FROM ${FEDORA_IMAGE}
# Shared by hosted CI and the manager's local rootless Fedora container.
# Keep the shell alive after standalone timeout calls: coreutils 9.10 rejects
# children of PID 1, so an exec-optimized RUN would fail with exit 125.
RUN set -e; timeout --kill-after=10s 180s dnf install -y https://download1.rpmfusion.org/free/fedora/rpmfusion-free-release-$(rpm -E %fedora).noarch.rpm; :
RUN timeout --kill-after=10s 600s dnf install -y git python3-pip mesa-libEGL mesa-libGL libxkbcommon dbus-libs \
    fontconfig dejavu-sans-fonts dejavu-sans-mono-fonts glib2 libstdc++ pulseaudio-libs \
    nspr nss alsa-lib libdrm libXcomposite libXdamage libXrandr libxkbfile \
    libXtst libXScrnSaver cups-libs gtk3 tar gzip openssl-libs snappy minizip-ng-compat \
    vlc-libs vlc-plugins-base vlc-plugin-ffmpeg vlc-plugins-extra libavcodec-freeworld && dnf clean all
RUN set -e; timeout --kill-after=10s 180s python3 -m pip install --no-cache-dir uv==0.13.4; :
