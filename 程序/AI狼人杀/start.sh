#!/bin/bash
# AI 狼人杀一键启动
cd "$(dirname "$0")"
exec .venv/bin/python -m backend.main
