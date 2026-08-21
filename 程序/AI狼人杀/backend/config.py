"""配置加载：解析 config/models.json 与 .env，校验 API Key。"""
import json
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent
FRONTEND_DIR = PROJECT_DIR / "frontend"
CONFIG_DIR = BACKEND_DIR / "config"
MODELS_FILE = CONFIG_DIR / "models.json"


class ModelConfig:
    """一个 AI 模型配置（由用户在 models.json 中自行填写）。"""

    def __init__(self, name: str, base_url: str, api_key_env: str, model: str, tts_voice: str = ""):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.api_key = os.environ.get(api_key_env, "")
        self.model = model
        self.tts_voice = tts_voice
        self.enabled = bool(self.api_key and self.base_url and self.model)

    @property
    def disabled_reason(self) -> str:
        reasons = []
        if not self.api_key:
            reasons.append(f"未设置环境变量 {self.api_key_env}")
        if not self.base_url:
            reasons.append("base_url 为空")
        if not self.model:
            reasons.append("model 为空")
        return "；".join(reasons) if reasons else ""


def load_env_file():
    """加载 backend/.env（若存在），不覆盖已有的环境变量。"""
    env_path = BACKEND_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()


def load_models() -> list[ModelConfig]:
    """读取 models.json，返回所有模型配置（含被禁用的）。"""
    if not MODELS_FILE.exists():
        return []
    try:
        data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"⚠️ 配置文件 {MODELS_FILE} 解析失败：{e}，将使用空模型列表")
        return []
    models = []
    for item in data.get("models", []):
        models.append(ModelConfig(
            name=item.get("name", ""),
            base_url=item.get("base_url", ""),
            api_key_env=item.get("api_key_env", ""),
            model=item.get("model", ""),
            tts_voice=item.get("tts_voice", ""),
        ))
    return models


def check_models_and_print(models: list[ModelConfig]):
    """启动时校验 API Key，打印醒目的中文警告。"""
    if not models:
        print("⚠️ 未配置任何模型（config/models.json 为空模板），AI 玩家将不可用。")
        print("   请自行编辑 backend/config/models.json 添加模型后重启。")
        return
    enabled = [m for m in models if m.enabled]
    for m in models:
        if m.enabled:
            print(f"✅ 模型「{m.name}」已启用（{m.model}）")
        else:
            print(f"⚠️ 模型「{m.name}」已禁用：{m.disabled_reason}")
    if not enabled:
        print("⚠️ 没有可用的模型，AI 玩家将不可用。")


# 启动时加载的模型配置（供 main / ws_handler 引用）
# 注意：必须先加载 .env 再读 models.json，否则 api_key 为空导致所有模型被禁用
def _init_models() -> list[ModelConfig]:
    load_env_file()
    return load_models()


# 语音播报总开关（edge-tts 不稳定，默认关闭；设 TTS_ENABLED=1 开启）
# 必须在 load_env_file() 之后求值；此处直接调用确保模块导入时即生效
load_env_file()
TTS_ENABLED = os.environ.get("TTS_ENABLED", "").strip().lower() in ("1", "true", "yes")


MODELS: list[ModelConfig] = _init_models()
