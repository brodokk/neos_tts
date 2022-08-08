FROM ghcr.io/coqui-ai/tts-cpu:5094499eba440efd41031ad8d7739c4b49c6045b

RUN apt-get update && apt-get install -y \
    git \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install -r requirements.txt
