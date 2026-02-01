# ---- opus module build stage ----
FROM buildpack-deps:bookworm AS opus_builder

RUN apt update && apt install -y libopus-dev && rm -rf /var/lib/apt/lists/*
WORKDIR /opus
COPY ./opus/ .
RUN make

# ---- Rust DAVE lib build stage ----
FROM python:3.12-slim AS dave_builder

WORKDIR /dave/openmls

RUN apt update && apt install -y curl build-essential
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
COPY ./dave/openmls .
RUN pip install maturin && maturin build --release

# ---- runtime stage ----
FROM python:3.12-slim

WORKDIR /bot

RUN apt update && apt install -y ffmpeg curl unzip && rm -rf /var/lib/apt/lists/*
RUN (curl -fsSL https://deno.land/install.sh | sh) && ln --symbolic /root/.deno/bin/deno /usr/bin/deno
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=opus_builder /opus/opus_encode.so ./opus/
COPY --from=dave_builder /dave/openmls/target/wheels/*.whl /tmp/
RUN pip install /tmp/*.whl

CMD ["python", "main.py", "--logfile", "/bot/logs/meu-chapeu.log"]
