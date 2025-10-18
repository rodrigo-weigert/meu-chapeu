FROM python:3.12-slim

WORKDIR /bot

RUN apt update && apt install -y build-essential libopus-dev ffmpeg && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

WORKDIR /bot/opus
RUN make

WORKDIR /bot
CMD ["python", "main.py"]
