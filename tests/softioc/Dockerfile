FROM ubuntu:20.04

LABEL description="Package which provides the tooling to build with GCC-9."

RUN apt-get update && \
	apt-get install --no-install-recommends -y \
		ssh \
		apt-utils \
		wget curl \
		jq \
		bzip2 xz-utils \
		tar \
		binutils \
		make \
		git-core \
		g++-9 \
		libstdc++-9-dev \
		build-essential \
		libncurses-dev \
		libreadline-dev \
		python3 \
		python3-dev \
		python3-pip \
		python3-venv \
		python3-setuptools && \
	rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-9 100 && \
	update-alternatives --install /usr/bin/g++ g++ /usr/bin/g++-9 100

ENV PATH "${PATH}:/epics/base-7.0.6/bin/linux-x86_64"

RUN wget --no-check-certificate --no-cookies https://launchpad.net/epics-base/7.0/7.0.6/+download/base-7.0.6.tar.gz && \
	echo "2028d65ea7b921dd083d8e1946d216f0 base-7.0.6.tar.gz" >> MD5SUM && \
	md5sum -c MD5SUM && \
	mkdir /epics && \
	tar -xzf base-7.0.6.tar.gz -C /epics && \
	rm -f base-7.0.6.tar.gz MD5SUM && \
	cd /epics/base-7.0.6 && \
	make -j
