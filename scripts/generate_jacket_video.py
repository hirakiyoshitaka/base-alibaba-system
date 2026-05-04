"""Generate a cinematic fashion film via fal.ai using a reference jacket image.

Usage:
    export FAL_KEY="your_fal_key_here"
    python -m pip install fal-client requests
    python scripts/generate_jacket_video.py
"""

from __future__ import annotations

import os
import sys
import time
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REFERENCE_IMAGE = PROJECT_ROOT / "images" / "ワークジャケット（デトロイト風）" / "04.jpg"
OUTPUT_VIDEO = PROJECT_ROOT / "videos" / "jacket_omotesando.mp4"

PROMPT = (
    "A cinematic fashion film of a handsome, stylish young Japanese man "
    "with a fresh haircut, walking confidently down a sunny, trendy street "
    "in Omotesando, Tokyo. He is wearing a minimalist color-block windbreaker "
    "jacket in white and brown (matching the reference image), styled with "
    "clean white sneakers. The camera follows him in a smooth tracking shot. "
    "High-end commercial aesthetic, 4k resolution, 24fps, natural morning "
    "sunlight with soft shadows."
)


def fail(message: str, code: int = 1) -> None:
    print(f"❌ {message}")
    sys.exit(code)


def main() -> None:
    if not os.environ.get("FAL_KEY"):
        fail("FAL_KEY 環境変数が未設定です。`export FAL_KEY=...` を実行してください。")

    if not REFERENCE_IMAGE.exists():
        fail(f"参照画像が見つかりません: {REFERENCE_IMAGE}")

    try:
        import fal_client
    except ImportError:
        fail("fal-client が未導入です。`python -m pip install fal-client` を実行してください。")

    OUTPUT_VIDEO.parent.mkdir(parents=True, exist_ok=True)

    print("📤 参照画像を fal.ai にアップロードしています...")
    image_url = fal_client.upload_file(str(REFERENCE_IMAGE))
    print(f"   {image_url}")

    print("🎬 Kling v3 Pro (image-to-video) で動画を生成しています...")
    started_at = time.time()
    handler = fal_client.submit(
        "fal-ai/kling-video/v2.1/master/image-to-video",
        arguments={
            "prompt": PROMPT,
            "image_url": image_url,
            "duration": "5",
            "aspect_ratio": "16:9",
            "negative_prompt": "blurry, low quality, distorted, deformed",
        },
    )
    for event in handler.iter_events(with_logs=True):
        if hasattr(event, "logs") and event.logs:
            for log in event.logs:
                print(f"   {log.get('message', log)}")

    result = handler.get()
    elapsed = time.time() - started_at
    video_url = result.get("video", {}).get("url") if isinstance(result, dict) else None
    if not video_url:
        fail(f"生成結果から動画URLを取得できませんでした: {result}")

    print(f"✅ 生成完了 ({elapsed:.1f}s): {video_url}")
    print(f"⬇️  ダウンロード中: {OUTPUT_VIDEO}")
    urllib.request.urlretrieve(video_url, OUTPUT_VIDEO)
    print(f"🎉 保存完了: {OUTPUT_VIDEO}")
    print("   open でプレビュー: open '" + str(OUTPUT_VIDEO) + "'")


if __name__ == "__main__":
    main()
