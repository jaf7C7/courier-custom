# Builds "Courier Custom": Courier Prime with the digits, punctuation and
# symbols of Courier Prime Code, as TTF, OTF and WOFF2 (Regular and Italic;
# Code has no bold). Use ./build rather than invoking this directly; it runs
# `podman build --output` so that only the final files reach the host.
#
# Courier Prime is built from its .glyphs sources (the UFOs in its repo are
# stale 2015 exports). merge.py does the glyph swap; see it for the rules.
# Line spacing, widths and coverage stay Courier Prime's, and verify.py
# checks that against the upstream TTFs before anything is exported.
#
# Neither upstream repo tags releases, so both are pinned by commit. Python
# tools are pinned by hash in requirements.txt; to upgrade them, edit
# requirements.in and regenerate it with
#   pip-compile --generate-hashes --strip-extras --allow-unsafe requirements.in

# Debian 13.7 (trixie), pinned by digest for repeatable builds
ARG DEBIAN_IMAGE=docker.io/library/debian:trixie@sha256:bfc36aecdece0387418759dba474aa856c026ca8087da3606b41b90ab0509c99

FROM ${DEBIAN_IMAGE} AS build

ARG PRIME_REPO=https://github.com/quoteunquoteapps/CourierPrime.git
ARG PRIME_COMMIT=7fd585a2dd4c1612c79b3308e300923d1c13df93

ARG CODE_REPO=https://github.com/quoteunquoteapps/CourierPrimeCode.git
ARG CODE_COMMIT=0fcb44c7bcb7e81079dfa9f0d5ac5a4b3e7bf853

# A new name is required: both upstream names are Reserved Font Names
# under the OFL
ARG FAMILY="Courier Custom"

# apt normally drops to the _apt user to download; that fails under rootless
# podman setups that can't switch IDs, and buys nothing in a build stage
RUN echo 'APT::Sandbox::User "root";' > /etc/apt/apt.conf.d/99no-sandbox \
 && apt-get update \
 && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        ca-certificates git python3 python3-venv \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tools/
RUN python3 -m venv /tools/venv \
 && /tools/venv/bin/pip install --no-cache-dir --require-hashes \
        -r /tools/requirements.txt

# Fetching by full commit hash means the checkout can't be anything else
RUN set -eu; \
    fetch() { \
        git init -q "$3"; \
        git -C "$3" fetch -q --depth 1 "$1" "$2"; \
        git -C "$3" checkout -q FETCH_HEAD; \
    }; \
    fetch "${PRIME_REPO}" "${PRIME_COMMIT}" /src/prime; \
    fetch "${CODE_REPO}" "${CODE_COMMIT}" /src/code

COPY merge.py verify.py /tools/

ENV PATH=/tools/venv/bin:${PATH}
WORKDIR /work

# - glyphs2ufo writes one UFO per master (CourierPrime-Regular.ufo, ...);
#   Prime's Bold masters are converted too but not used.
# - SOURCE_DATE_EPOCH (the newer upstream commit) fixes head.modified, so
#   rebuilding the same commits gives byte-identical fonts.
# - fontmake names its output after the UFO, so the merged UFOs carry the
#   font's file name (CourierCustom-Regular.ufo, ...).
# - WOFF2 is made from the TTF, as is usual for web fonts.
RUN set -eu; \
    base="$(printf %s "${FAMILY}" | tr -d ' ')"; \
    glyphs2ufo -m prime "/src/prime/sources/Courier Prime.glyphs"; \
    glyphs2ufo -m prime "/src/prime/sources/Courier Prime Italic.glyphs"; \
    glyphs2ufo -m code "/src/code/glyphs/Courier Prime Code.glyphs"; \
    glyphs2ufo -m code "/src/code/glyphs/Courier Prime Code Italic.glyphs"; \
    mkdir merged; \
    for style in Regular Italic; do \
        python3 -I /tools/merge.py "prime/CourierPrime-${style}.ufo" \
            "code/CourierPrimeCode-${style}.ufo" \
            "merged/${base}-${style}.ufo" "${FAMILY}"; \
    done; \
    export SOURCE_DATE_EPOCH="$( \
        { git -C /src/prime log -1 --format=%ct; \
          git -C /src/code log -1 --format=%ct; } | sort -n | tail -1)"; \
    for format in ttf otf; do \
        fontmake -u merged/*.ufo -o "${format}" --output-dir "/out/${format}"; \
    done; \
    mkdir /out/woff2; \
    for ttf in /out/ttf/*.ttf; do \
        name="$(basename "${ttf}" .ttf)"; \
        fonttools ttLib.woff2 compress -o "/out/woff2/${name}.woff2" "${ttf}"; \
    done

RUN set -eu; \
    prime_ttf=/src/prime/fonts/ttf/CourierPrime; \
    code_ttf="/src/code/ttf/Courier Prime Code"; \
    for style in Regular Italic; do \
        suffix=; [ "${style}" = Italic ] && suffix=" Italic"; \
        for font in /out/*/*-"${style}".*; do \
            python3 -I /tools/verify.py "${font}" "${FAMILY}" "${style}" \
                "${prime_ttf}-${style}.ttf" "${code_ttf}${suffix}.ttf"; \
        done; \
    done; \
    [ "$(ls /out/*/* | wc -l)" -eq 6 ]; \
    install -m644 /src/prime/OFL.txt /out/OFL.txt; \
    cd /out; \
    sha256sum */* > SHA256SUMS

# Export stage: only the build output, consumed by `podman build --output`
FROM scratch
COPY --from=build /out/ /
