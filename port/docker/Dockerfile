# Build image for the functional port: the pinned ps2dev toolchain on Ubuntu, nothing else.
# It holds no game code and no game data; the repository is mounted when it runs.
#
#   docker build -t socom-port port/docker
#   docker run --rm -v "<checkout>:/src" -v socom-port-build:/build socom-port
#
# The ELF is written to <checkout>/build/port/docker/socom_port.elf (build/ is ignored by git).
# docs/port/notes/build-reference.md has the details; docs/reconstruction/PORT_TOOLCHAIN.md pins the release.
FROM ubuntu:24.04

# The same release, asset and SHA-256 as docs/reconstruction/PORT_TOOLCHAIN.md.
ARG PS2DEV_TAG=v2.0.0
ARG PS2DEV_ASSET=ps2dev-ubuntu-latest.tar.gz
ARG PS2DEV_SHA256=c8e5dedccf62084d476894e88cd0451b57f1ed288e741eb3c1263010aaffc028

# libmpc3, libmpfr6 and libgmp10 are what the toolchain's compiler programs (cc1, cc1plus, lto1)
# load at run time; a bare Ubuntu image does not have libmpc.so.3.
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl cmake make ccache \
      libmpc3 libmpfr6 libgmp10 libstdc++6 \
 && rm -rf /var/lib/apt/lists/*

RUN curl -fL --retry 5 -o /tmp/ps2dev.tar.gz \
      "https://github.com/ps2dev/ps2dev/releases/download/${PS2DEV_TAG}/${PS2DEV_ASSET}" \
 && echo "${PS2DEV_SHA256}  /tmp/ps2dev.tar.gz" | sha256sum -c - \
 && mkdir -p /opt/socom \
 && tar -xzf /tmp/ps2dev.tar.gz -C /opt/socom \
 && mv /opt/socom/ps2dev "/opt/socom/ps2dev-${PS2DEV_TAG}" \
 && rm /tmp/ps2dev.tar.gz

ENV SOCOM_PS2DEV=/opt/socom/ps2dev-v2.0.0 \
    SOCOM_SRC=/src \
    SOCOM_PORT_BUILD=/build \
    CCACHE_DIR=/build/.ccache

# The script is made independent of the checkout's line endings (a Windows checkout may hold
# CRLF shell scripts): it is copied here and runs CMake itself instead of port/tools/link.sh.
COPY build-port.sh /usr/local/bin/build-port
RUN sed -i 's/\r$//' /usr/local/bin/build-port && chmod +x /usr/local/bin/build-port

WORKDIR /src
ENTRYPOINT ["build-port"]
