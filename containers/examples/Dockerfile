# The Dockerfile is based on the official Ubuntu image for the jammy release. 
# The CONNEXT_VERSION argument is used to specify the version of RTI Connext to install. 
# The RTI_LICENSE_AGREEMENT_ACCEPTED argument is used to accept the RTI license agreement during installation.
# The NDDSHOME environment variable is set to the installation directory of RTI Connext.
#
# The Dockerfile installs the RTI Connext Debian Package from the official RTI repository. It also installs some build tools and the license file.
#
# The CMD instruction specifies the default command to run when the container starts. In this case, it runs the /bin/bash shell.
#
# To build the Docker image, run the following command from the root repository folder:
#   docker build -t connext:medtech_ra -f containers/examples/Dockerfile --build-arg RTI_LICENSE_AGREEMENT_ACCEPTED=accepted --build-arg CONNEXT_VERSION=7.3.0 .
#
# To run the Docker container, run the following command:
#
#   docker run --rm -it --network host -e DISPLAY -e SDL_AUDIODRIVER=dummy --device=/dev/ttyUSB0 --privileged --hostname rtimedtech -v $XAUTHORITY:/root/.Xauthority -v /tmp/.X11-unix:/tmp/.X11-unix -v $RTI_LICENSE_FILE:/root/rti_license.dat connext:medtech_ra bash
#
# Explanation of the options used in the docker run command:
#   The -it option is used to run the container in interactive mode.
#   The --rm option is used to remove the container when it exits.
#   The --network host option is used to share the host's network stack with the container
#   The -e DISPLAY option is used to set the DISPLAY environment variable in the container to the host's DISPLAY variable.
#   The -e SDL_AUDIODRIVER=dummy option is used to set the SDL_AUDIODRIVER environment variable to dummy to avoid audio issues.
#   The --device=/dev/ttyUSB0 option is used to give the container access to the USB device (e.g., joystick or xbox controller).
#   The --privileged option is used to give the container additional privileges.
#   The --hostname option is used to set the hostname of the container to rtimedtech.
#   The -v $XAUTHORITY:/root/.Xauthority option is used to mount the X11 authentication file from the host to the container.
#   The -v /tmp/.X11-unix:/tmp/.X11-unix option is used to mount the X11 socket from the host to the container.
#   The -v $RTI_LICENSE_FILE:/root/rti_license.dat option is used to mount the RTI license file from the host to the container.
#
# The container will start and run the /bin/bash shell.


FROM ubuntu:jammy AS install-stage

ARG CONNEXT_VERSION=7.3.0
ARG RTI_LICENSE_AGREEMENT_ACCEPTED

ENV DISPLAY=:0
ENV SHELL=/bin/bash
ENV TZ=Europe/Madrid
ENV NDDSHOME=/opt/rti.com/rti_connext_dds-${CONNEXT_VERSION}
SHELL ["/bin/bash", "-c"]

# Install the required packages
RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install -y \
    ca-certificates \
    dash \
    tzdata \
    git \
    build-essential \
    cmake \
    libgtk-3-dev \
    libgtksourceviewmm-3.0-dev \
    python3 \
    python3-gi \
    python3-gi-cairo \
    python3-numpy \
    python3-matplotlib \
    python3-pip \
    python3-pygame \
    python3-serial \
    gir1.2-gtk-4.0 \
    libgtk2.0-0 \
    libxxf86vm1 \
    libsm6 \
    libcanberra-gtk-module \
    iproute2 \
    iputils-ping \
    curl \
    nano \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists

# Install the RTI Connext Python API
RUN pip install rti.connext

# Install the RTI Connext Debian Package
RUN curl -sSL -o /usr/share/keyrings/rti-official-archive.gpg \
    https://packages.rti.com/deb/official/repo.key

RUN printf -- "deb [arch=%s, signed-by=%s] %s %s main\n" \
    $(dpkg --print-architecture) \
    /usr/share/keyrings/rti-official-archive.gpg \
    https://packages.rti.com/deb/official \
    $(. /etc/os-release && echo ${VERSION_CODENAME}) | tee /etc/apt/sources.list.d/rti-official.list >/dev/null

RUN export DEBIAN_FRONTEND=noninteractive \
    RTI_LICENSE_AGREEMENT_ACCEPTED=${RTI_LICENSE_AGREEMENT_ACCEPTED} \
    && apt-get update \
    && apt-get install -y \
    rti-connext-dds-${CONNEXT_VERSION} \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists

RUN echo "source ${NDDSHOME}/resource/scripts/rtisetenv_*.bash" >> /root/.bashrc

WORKDIR /root

RUN git clone -b examples --recurse-submodule https://github.com/rticommunity/rticonnextdds-medtech-reference-architecture.git medtech_ra
WORKDIR /root/medtech_ra/modules/01-operating-room

# Copy additional source files
COPY ./examples/joystick_controller/joystick_controller.py \
     ./examples/lss_robot/lss_robot_app.py \
     ./examples/lss_robot/LSS_Library_Python/src/lss.py \
     ./examples/lss_robot/LSS_Library_Python/src/lss_const.py \
     ./examples/telemetry_bridge/telemetry_app.py \
     ./examples/xbox_controller/xbox_controller.py \
     /root/medtech_ra/modules/01-operating-room/src/

# Copy launch scripts
COPY ./examples/joystick_controller/launch_arm_joystick.sh \
     ./examples/lss_robot/launch_robot_app.sh \
     ./examples/telemetry_bridge/launch_telemetry_app.sh \
     ./examples/xbox_controller/launch_arm_xbox.sh \
     /root/medtech_ra/modules/01-operating-room/scripts/

# Create a script to build the sources
RUN echo "#!/bin/bash" > build_module_01.sh
RUN echo "source ${NDDSHOME}/resource/scripts/rtisetenv_*.bash" >> build_module_01.sh
RUN echo "mkdir build && cd build && cmake .. && cmake --build ." >> build_module_01.sh
RUN chmod +x build_module_01.sh

# Configure licence file
RUN echo "export RTI_LICENSE_FILE=/root/rti_license.dat" >> /root/.bashrc
RUN rm ${NDDSHOME}/rti_license.dat
RUN ln -s /root/rti_licence.dat ${NDDSHOME}/rti_license.dat

FROM scratch AS final-stage

WORKDIR /root

COPY --from=install-stage / /

WORKDIR /root/medtech_ra/modules/01-operating-room
RUN ./build_module_01.sh

WORKDIR /root
CMD ["/bin/bash"]