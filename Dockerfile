# ---- opus module build stage ----
FROM buildpack-deps:bookworm AS opus_builder

RUN apt update && apt install -y libopus-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /opus
COPY ./opus/ .
RUN make

# ---- runtime stage ----
FROM python:3.12-slim

WORKDIR /bot

RUN apt update && apt install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*
RUN (curl -fsSL https://deno.land/install.sh | sh) && ln --symbolic /root/.deno/bin/deno /usr/bin/deno
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=opus_builder /opus/opus_encode.so ./opus/

CMD ["python", "main.py", "--logfile", "/bot/logs/meu-chapeu.log"]
