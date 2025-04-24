FROM ubuntu:18.04
MAINTAINER Ridwan Shariffdeen <ridwan@comp.nus.edu.sg>
ARG DEBIAN_FRONTEND=noninteractive
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
RUN apt-get update
RUN apt-get install -y --no-install-recommends  \
       git \
       vim \
       nano \
       ant \
       python3-distutils \
       unzip \
       wget \
       tmux

# install utility to transfrom dos to unix encodings and vice-versa
RUN apt-get install -y --no-install-recommends dos2unix

# Set up python3.9
RUN apt-get install -y --no-install-recommends \
        build-essential \
        zlib1g-dev \
        libncurses5-dev \
        libgdbm-dev \
        libnss3-dev \
        libssl-dev \
        libreadline-dev \
        libffi-dev \
        libsqlite3-dev \
        libbz2-dev
RUN wget -q -O /tmp/Python-3.9.13.tgz https://www.python.org/ftp/python/3.9.13/Python-3.9.13.tgz
RUN mkdir /tmp/Python-3.9.13
RUN tar xzf /tmp/Python-3.9.13.tgz -C /tmp
WORKDIR /tmp/Python-3.9.13
RUN ./configure --enable-optimizations
RUN make -j"$(nproc)"
RUN make install

# Install Maven
RUN cd /opt && wget -q https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.6.3/apache-maven-3.6.3-bin.tar.gz && \
    tar -xvf apache-maven-3.6.3-bin.tar.gz
ENV M2_HOME '/opt/apache-maven-3.6.3'
ENV PATH "$M2_HOME/bin:${PATH}"

# Instead of openjdk-8-jdk, install zulu jdk 8.0 to accomodate Defects4J version 1.5.0 and older
RUN wget -q -O /tmp/zulu8.deb https://cdn.azul.com/zulu/bin/zulu8.66.0.15-ca-jdk8.0.352-linux_amd64.deb
RUN apt install -y /tmp/zulu8.deb

# Build Defects4J (adapted from https://github.com/rjust/defects4j/blob/master/Dockerfile)
# JDK already set up above, so dont install JDK here
RUN \
  apt-get update -y && \
  apt-get install software-properties-common -y --no-install-recommends && \
  apt-get update -y && \
  apt-get install -y --no-install-recommends \
                git \
                build-essential \
                subversion \
                perl \
                curl \
                unzip \
                cpanminus \
                make

RUN cd /opt && git clone https://github.com/rjust/defects4j.git
WORKDIR /opt/defects4j
RUN git checkout tags/v2.1.0 # EvoRepair doesn't run on the newest version
RUN cpanm --installdeps .
RUN ./init.sh
ENV PATH="/opt/defects4j/framework/bin:${PATH}"

ADD ./defects4j.diff /tmp
RUN patch -p1 -i /tmp/defects4j.diff

ADD . /opt/EvoRepair
WORKDIR /opt/EvoRepair
RUN ./setup.sh
RUN ./checkout_d4j.sh
RUN python3 -m pip install -r requirements.txt
RUN ln -s /opt/EvoRepair/bin/evorepair /usr/bin/evorepair
RUN evorepair --help

ENV OLLAMA_HOST=host.docker.internal

