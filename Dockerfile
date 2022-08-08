FROM ghcr.io/coqui-ai/tts-cpu:5094499eba440efd41031ad8d7739c4b49c6045b

RUN pip install fenkeysmanagement soundfile pydub

RUN apt-get install ffmpeg libavcodec-extra
