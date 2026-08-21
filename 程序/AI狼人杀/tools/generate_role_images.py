"""一次性预生成 5 张角色立绘（调用本地 agnes-cli）。

依赖：/Users/hyh/程序/agnes-cli/agnes.js（已通过 npm link 全局生效，可以直接 `agnes ...`）

使用方法：
    python tools/generate_role_images.py

生成的图片保存在 frontend/static/roles/<role>.png，已存在则跳过。
"""
import subprocess
import sys
from pathlib import Path

# agnes CLI 的两种调用方式：优先全局 `agnes`，fallback 用 node + 绝对路径
AGNES_GLOBAL = "agnes"
AGNES_NODE_FALLBACK = ["node", "/Users/hyh/程序/agnes-cli/agnes.js"]

ROLES = {
    "werewolf": "A mysterious lone werewolf with glowing red eyes, dark hooded cloak, "
                "full moon behind, fantasy portrait, dramatic lighting, 8k",
    "seer":     "An ancient seer holding a glowing crystal orb, hooded robes, mystical aura, "
                "fantasy portrait, 8k",
    "witch":    "A potion-making witch with two glowing vials (red and blue), "
                "dark forest background, fantasy portrait, 8k",
    "hunter":   "A rugged hunter with crossbow and a loyal hound, twilight forest, "
                "fantasy portrait, 8k",
    "villager": "A kind commoner villager in simple linen clothes holding a lantern, "
                "warm sunset village background, fantasy portrait, 8k",
}


def run_agnes(prompt: str, out_path: Path) -> bool:
    """调用 agnes image generate；CLI 会自行处理鉴权与下载。"""
    base = [AGNES_GLOBAL, "image", "generate",
            "--prompt", prompt,
            "--model", "agnes-image-2.1-flash",
            "--size", "768x1024",
            "--out", str(out_path)]
    # 如果全局 `agnes` 找不到，fallback 到 node + 绝对路径
    try:
        result = subprocess.run(base, capture_output=True, text=True, timeout=300)
    except FileNotFoundError:
        result = subprocess.run(AGNES_NODE_FALLBACK + base[1:],
                                capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"   ❌ agnes 调用失败: {result.stderr.strip()}", file=sys.stderr)
        return False
    print(f"   {result.stdout.strip()}")
    return out_path.exists() and out_path.stat().st_size > 1024


def main():
    out_dir = Path(__file__).resolve().parents[1] / "frontend" / "static" / "roles"
    out_dir.mkdir(parents=True, exist_ok=True)

    for role, prompt in ROLES.items():
        out_path = out_dir / f"{role}.png"
        if out_path.exists() and out_path.stat().st_size > 1024:
            print(f"⏭️  {role}.png 已存在，跳过")
            continue
        print(f"🎨 生成 {role}.png …")
        if not run_agnes(prompt, out_path):
            sys.exit(2)

    print("\n全部完成。图片路径：")
    for p in sorted(out_dir.glob("*.png")):
        print(f"  - frontend/static/roles/{p.name}")


if __name__ == "__main__":
    main()