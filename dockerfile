FROM alpine AS base

ARG USER=magg
ARG HOME=/home/${USER}
ARG PACKAGE=${USER}
ARG UID=1000

ENV PATH="${HOME}/.local/bin:${PATH}"

RUN apk add --no-cache tini bash curl nano nodejs npm python3 py3-pip && \
    addgroup -g ${UID} -S ${USER} && \
    adduser -u ${UID} -S -G ${USER} -h ${HOME} -s /bin/bash ${USER} && \
    chmod 755 ${HOME}

USER ${USER}
WORKDIR ${HOME}

FROM base AS venv

ARG PYTHON_VERSION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=0 \
    UV_LINK_MODE=copy \
    PATH="${HOME}/.venv/bin:${PATH}" \
    VIRTUAL_ENV="${HOME}/.venv" \
    PS1="(${PACKAGE}) \h:\w\$ "

# Activating the venv through bash the "normal" way:
# ENV BASH_ENV="${HOME}/.bashrc"  # enables .bashrc to be sourced in non-interactive shells e.g. `bash -c`
# RUN echo "source ~/.venv/bin/activate" >> ${HOME}/.bashrc

RUN curl -LsSf https://astral.sh/uv/install.sh | sh

ADD --chown=${USER}:${USER} .python-version ./

RUN if [ -n "${PYTHON_VERSION}" ]; then \
        echo "${PYTHON_VERSION}" > .python-version; \
    fi

FROM venv AS proj

LABEL org.opencontainers.image.source=https://github.com/sitbon/magg \
      org.opencontainers.image.description="Magg - The Model Context Protocol (MCP) Aggregator (Project)" \
      org.opencontainers.image.licenses=AGPLv3 \
      org.opencontainers.image.authors="Phillip Sitbon <phillip.sitbon@gmail.com>"

ARG MAGG_CONFIG_PATH="${HOME}/.magg/config.json"
ARG MAGG_READ_ONLY=false

ENV MAGG_CONFIG_PATH="${MAGG_CONFIG_PATH}" \
    MAGG_READ_ONLY="${MAGG_READ_ONLY}"

RUN --mount=type=cache,uid=${UID},gid=${UID},target=${HOME}/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# Fix for Python 3.12 extension suffix mismatch on Alpine
# Python 3.12 expects linux-gnu but we have linux-musl wheels
RUN if [ "${PYTHON_VERSION}" = "3.12" ]; then \
        find .venv/lib -name "*.cpython-*-x86_64-linux-musl.so" -exec sh -c \
            'ln -sf "$(basename "$1")" "$(dirname "$1")/$(echo "$(basename "$1")" | sed "s/-musl\.so$/-gnu.so/")"' _ {} \; ; \
    fi

ADD --chown=${USER}:${USER} pyproject.toml uv.lock readme.md license.md ./
ADD --chown=${USER}:${USER} ${PACKAGE}/ ./${PACKAGE}/

RUN --mount=type=cache,uid=${UID},gid=${UID},target=${HOME}/.cache/uv \
    uv sync --locked --no-dev

RUN mkdir -p .magg && \
    chmod 755 .magg

EXPOSE 8000

ENTRYPOINT ["/sbin/tini", "--"]
CMD ["magg", "serve", "--http", "--host", "0.0.0.0", "--port", "8000"]


FROM proj AS pre

LABEL org.opencontainers.image.source=https://github.com/sitbon/magg \
      org.opencontainers.image.description="Magg - The Model Context Protocol (MCP) Aggregator (Staging)" \
      org.opencontainers.image.licenses=AGPLv3 \
      org.opencontainers.image.authors="Phillip Sitbon <phillip.sitbon@gmail.com>"

ENV MAGG_LOG_LEVEL=INFO

USER root

RUN chown -R root:${USER} ${HOME}/.venv ${HOME}/${PACKAGE} && \
    chmod -R a-w,a+rX ${HOME}/.venv ${HOME}/${PACKAGE} && \
    chown -R ${USER}:${USER} ${HOME}/.magg && \
    chmod -R u+rwX ${HOME}/.magg && \
    if [ "${MAGG_READ_ONLY}" = "true" ] || [ "${MAGG_READ_ONLY}" = "1" ] || [ "${MAGG_READ_ONLY}" = "yes" ]; then \
        chmod -R a-w ${HOME}/.magg; \
    fi
    # Note: The above check does not work with volume mounts (e.g. compose), so the real enforcement
    #       is done in the application code.

USER ${USER}

FROM pre AS pro

LABEL org.opencontainers.image.source=https://github.com/sitbon/magg \
      org.opencontainers.image.description="Magg - The Model Context Protocol (MCP) Aggregator" \
      org.opencontainers.image.licenses=AGPLv3 \
      org.opencontainers.image.authors="Phillip Sitbon <phillip.sitbon@gmail.com>"

ENV MAGG_LOG_LEVEL=WARNING

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD ["magg", "status"]

FROM proj AS dev

LABEL org.opencontainers.image.source=https://github.com/sitbon/magg \
      org.opencontainers.image.description="Magg - The Model Context Protocol (MCP) Aggregator (Development)" \
      org.opencontainers.image.licenses=AGPLv3 \
      org.opencontainers.image.authors="Phillip Sitbon <phillip.sitbon@gmail.com>"

ENV MAGG_LOG_LEVEL=DEBUG

ADD --chown=${USER}:${USER} test/ ./test/

RUN --mount=type=cache,uid=1000,gid=1000,target=${HOME}/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --dev

FROM dev AS pkg

LABEL org.opencontainers.image.source=https://github.com/sitbon/magg \
      org.opencontainers.image.description="Magg - The Model Context Protocol (MCP) Aggregator (Packaging)" \
      org.opencontainers.image.licenses=AGPLv3 \
      org.opencontainers.image.authors="Phillip Sitbon <phillip.sitbon@gmail.com>"

RUN --mount=type=cache,uid=${UID},gid=${UID},target=${HOME}/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv build

FROM venv AS user

LABEL org.opencontainers.image.source=https://github.com/sitbon/magg \
      org.opencontainers.image.description="Magg - The Model Context Protocol (MCP) Aggregator (User Environment)" \
      org.opencontainers.image.licenses=AGPLv3 \
      org.opencontainers.image.authors="Phillip Sitbon <phillip.sitbon@gmail.com>"

ENV PS1="(user) \h:\w\$ "

COPY --from=pkg ${HOME}/dist/ ${HOME}/dist/

RUN uv init --no-workspace --no-package --no-readme --no-description --name user && \
    uv sync && \
    uv add "magg[dev] @ $(ls -t1 dist/*.whl | head -n 1)"

CMD ["bash"]
