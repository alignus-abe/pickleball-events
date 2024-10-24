FROM python:3.11.8-slim-bullseye

RUN apt-get update && apt-get install -y \
    build-essential \
    ffmpeg \
    libgl1-mesa-glx \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /data

COPY requirements.txt /data/

RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py /data/
COPY config.py /data/
COPY config.json /data/
COPY test.mp4 /data/

CMD ["python", "/data/main.py"]