ARG FFMPEG_VERSION="9.0.1"
ARG OPUS_VERSION="1.6.1"

# ---- opus module build stage ----
FROM buildpack-deps:bookworm AS opus_builder

ARG OPUS_VERSION

RUN wget https://downloads.xiph.org/releases/opus/opus-${OPUS_VERSION}.tar.gz
RUN tar -xf opus-${OPUS_VERSION}.tar.gz

WORKDIR /opus-${OPUS_VERSION}
RUN ./configure --enable-static --disable-shared --with-pic
RUN make -j$(nproc) && make install

WORKDIR /opus
COPY ./opus/ .
RUN make

# ---- Rust DAVE lib build stage ----
FROM python:3.12-slim AS dave_builder

WORKDIR /dave/openmls

RUN apt update && apt install -y --no-install-recommends curl build-essential
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
COPY ./dave/openmls .
RUN pip install maturin && maturin build --release

# ---- FFmpeg build stage ----
FROM buildpack-deps:bookworm AS ffmpeg_builder

ARG FFMPEG_VERSION

RUN apt update && apt install -y --no-install-recommends nasm

RUN wget https://ffmpeg.org/releases/ffmpeg-${FFMPEG_VERSION}.tar.xz
RUN tar -xf ffmpeg-${FFMPEG_VERSION}.tar.xz

WORKDIR /ffmpeg-${FFMPEG_VERSION}
RUN ./configure \
  --disable-everything \
  --disable-doc \
  --disable-programs \
  --enable-ffmpeg \
  --disable-network \
  --disable-autodetect \
  --enable-protocol=file,pipe \
  --enable-demuxer=matroska,ogg \
  --enable-decoder=opus,vorbis \
  --enable-encoder=pcm_s16le \
  --enable-muxer=pcm_s16le \
  --enable-filter=aresample
RUN make -j$(nproc)

# ---- runtime stage ----
FROM python:3.12-slim

ARG FFMPEG_VERSION

WORKDIR /bot

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=opus_builder /opus/opus_encode.so ./opus/
COPY --from=dave_builder /dave/openmls/target/wheels/*.whl /tmp/
COPY --from=ffmpeg_builder /ffmpeg-${FFMPEG_VERSION}/ffmpeg /usr/local/bin/
RUN pip install /tmp/*.whl

STOPSIGNAL SIGINT

CMD ["nice", "-n", "-10", "python", "main.py", "--logfile", "/bot/logs/meu-chapeu.log"]
