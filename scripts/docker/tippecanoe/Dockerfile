# Tippecanoe build container (from the upstream mapbox/tippecanoe source).
# Produces a small runtime image exposing the `tippecanoe` binary.
FROM debian:bookworm-slim AS build
RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ make git ca-certificates libsqlite3-dev zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*
RUN git clone --depth 1 https://github.com/mapbox/tippecanoe.git /src
WORKDIR /src
RUN make -j"$(nproc)" && make install

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsqlite3-0 zlib1g \
    && rm -rf /var/lib/apt/lists/*
COPY --from=build /usr/local/bin/tippecanoe /usr/local/bin/tippecanoe
COPY --from=build /usr/local/bin/tile-join /usr/local/bin/tile-join
ENTRYPOINT ["tippecanoe"]
