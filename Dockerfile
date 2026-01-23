FROM python:3.10-slim

RUN apt-get update && apt-get install -y \
    git \ 
    ssh \
    netcat-openbsd \
    moreutils \
    psmisc \
    vim \
    bsdmainutils \
    curl \
    moreutils \
    python3-pip \
    iproute2 \
    ffmpeg \
    make \
    g++ 

WORKDIR /app


COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt


COPY ./SimulStreaming /app/SimulStreaming

COPY ./audio /app/audio 

COPY ./online-text-flow /app/online-text-flow
RUN cd /app/online-text-flow && make


COPY ./mt-wrapper /app/mt-wrapper

COPY ./pipeliner /app/pipeliner
RUN pip install -r /app/pipeliner/requirements.txt

COPY parts/*.py /app/
COPY parts/*.sh /app/

COPY configs/*.yaml /app/


ENV PATH="${PATH}:/app/online-text-flow"
ENV PYTHONPATH="${PYTHONPATH}:/app:/app/SimulStreaming:/app/mt-wrapper:/app/pipeliner/src:/app/online-text-flow"
