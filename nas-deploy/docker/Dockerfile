FROM python:3.12-slim-bookworm

WORKDIR /app

# ============================================================
# 离线构建：所有依赖已预下载到 offline-deps/ 目录
# 构建前请确保已拉取基础镜像：
#   docker pull python:3.12-slim-bookworm
# ============================================================

# 1. 安装预下载的 supercronic（cron 调度器）
COPY offline-deps/supercronic-linux-amd64 /usr/local/bin/supercronic
RUN chmod +x /usr/local/bin/supercronic && supercronic -version

# 2. 安装预下载的 uv（Python 包管理器）
COPY offline-deps/uv-x86_64-unknown-linux-gnu.tar.gz /tmp/
RUN tar xzf /tmp/uv-x86_64-unknown-linux-gnu.tar.gz -C /usr/local/bin/ --strip-components=1 \
    && chmod +x /usr/local/bin/uv /usr/local/bin/uvx \
    && rm /tmp/uv-x86_64-unknown-linux-gnu.tar.gz

# 3. 从本地 wheels 安装所有 Python 依赖（无需网络，无依赖解析）
#    策略：所有传递依赖的 wheel 已预下载，直接安装全部 wheel 即可
#    hf-xet 被故意跳过 —— 它只有 cp313 wheel，不兼容 Python 3.12，
#    但它是 huggingface-hub 的可选下载加速器，缺失不影响功能
COPY offline-deps/wheels/ /tmp/wheels/
RUN uv venv /app/.venv && \
    uv pip install --no-index --find-links /tmp/wheels/ setuptools wheel && \
    uv pip install --no-index --no-deps /tmp/wheels/*.whl && \
    uv pip install --no-index --no-build-isolation /tmp/wheels/sgmllib3k-1.0.0.tar.gz && \
    rm -rf /tmp/wheels

ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app:$PYTHONPATH"

# 4. 复制项目源码
COPY docker/manage.py .
COPY trendradar/ ./trendradar/
COPY mcp_server/ ./mcp_server/

# 5. 复制入口脚本
COPY docker/entrypoint.sh /entrypoint.sh.tmp
RUN sed -i 's/\r$//' /entrypoint.sh.tmp && \
    mv /entrypoint.sh.tmp /entrypoint.sh && \
    chmod +x /entrypoint.sh && \
    chmod +x manage.py && \
    mkdir -p /app/config /app/output

ENV PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/app/config/config.yaml \
    FREQUENCY_WORDS_PATH=/app/config/frequency_words.txt

ENTRYPOINT ["/entrypoint.sh"]
