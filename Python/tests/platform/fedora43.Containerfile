FROM registry.fedoraproject.org/fedora:43
RUN dnf install -y git python3-pip mesa-libEGL mesa-libGL libxkbcommon dbus-libs fontconfig dejavu-sans-fonts dejavu-sans-mono-fonts glib2 libstdc++ pulseaudio-libs nspr nss alsa-lib libdrm libXcomposite libXdamage libXrandr libxkbfile libXtst libXScrnSaver cups-libs gtk3 tar gzip openssl-libs snappy minizip && dnf clean all
RUN python3 -m pip install uv==0.12.18
