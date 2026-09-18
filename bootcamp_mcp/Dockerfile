# bootcamp-mcp: the scoped SAS Viya MCP server for the bootcamp.
# Build (from this directory):  docker build -t bootcamp-mcp:0.1.0 .
# Run:  docker run -d -p 8134:8134 --env-file .env --name bootcamp-mcp bootcamp-mcp:0.1.0
FROM python:3.12-slim-bookworm AS builder

# git: the sas-mcp-server dependency is installed from its GitHub tag.
RUN apt-get update && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python3 -m venv /app/.venv \
    && /app/.venv/bin/pip install --no-cache-dir --upgrade pip \
    && /app/.venv/bin/pip install --no-cache-dir .

FROM python:3.12-slim-bookworm AS runner
ARG HOST_PORT=8134

LABEL org.opencontainers.image.source=https://github.com/raedaldweik/Agentic-Bootcamp
LABEL org.opencontainers.image.description="bootcamp-mcp: scoped SAS Viya MCP server for the EHS x SAS Agentic AI Bootcamp"
LABEL org.opencontainers.image.licenses=Apache-2.0

RUN addgroup --system sas && adduser --system --ingroup sas --home /app sas
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /app
USER sas

EXPOSE ${HOST_PORT}
CMD ["bootcamp-mcp"]
