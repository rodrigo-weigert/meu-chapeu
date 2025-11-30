FROM python:3.12-slim

WORKDIR /bot

RUN apt update && apt install -y build-essential libopus-dev ffmpeg unzip curl && rm -rf /var/lib/apt/lists/*
RUN (curl -fsSL https://deno.land/install.sh | sh) && ln --symbolic /root/.deno/bin/deno /usr/bin/deno
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

WORKDIR /bot/opus
RUN make

WORKDIR /bot
CMD ["python", "main.py", "--logfile", "/bot/logs/meu-chapeu.log"]
