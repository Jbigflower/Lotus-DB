# 顶部：导入与路径工具函数迁移
import os
import math
import subprocess
from typing import List, Dict, Any
from PIL import Image
from pymediainfo import MediaInfo


def ensure_dir_rw(path: str) -> None:
    try:
        if not os.path.isdir(path):
            os.makedirs(path, exist_ok=True)
        if not (os.access(path, os.R_OK) and os.access(path, os.W_OK)):
            raise PermissionError("路径需可读写")
    except Exception as e:
        raise e

# ------------------------------
# 媒体元数据与处理（逻辑层）
# ------------------------------


def extract_media_metadata(path: str) -> Dict[str, Any]:
    """
    使用 pymediainfo 提取元数据；对非视频/音频用 mimetypes 补充
    """
    import mimetypes

    meta: Dict[str, Any] = {
        "size": os.path.getsize(path) if os.path.exists(path) else 0,
        "codec": "",
        "quality": "",
        "duration": None,
        "width": None,
        "height": None,
        "has_thumbnail": False,
        "has_sprite": False,
    }
    # 尝试使用 ffprobe 获取更准确的时长和分辨率
    try:
        # 格式: duration,width,height
        probe_cmd = [
            "ffprobe", "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,duration",
            "-of", "csv=p=0",
            path
        ]
        res = subprocess.run(probe_cmd, capture_output=True, text=True)
        if res.returncode == 0:
            parts = res.stdout.strip().split(',')
            # ffprobe 输出顺序通常对应 -show_entries 的顺序，但也可能变动，csv=p=0 简单模式下
            # -show_entries stream=width,height,duration -> width,height,duration
            if len(parts) >= 2:
                try:
                    # 尝试解析
                    w_probe = int(parts[0])
                    h_probe = int(parts[1])
                    if w_probe > 0 and h_probe > 0:
                        meta["width"] = w_probe
                        meta["height"] = h_probe
                        # 根据分辨率重新判断画质
                        if w_probe >= 3840: meta["quality"] = "2160p"
                        elif w_probe >= 2560: meta["quality"] = "1440p"
                        elif w_probe >= 1920: meta["quality"] = "1080p"
                        elif w_probe >= 1280: meta["quality"] = "720p"
                        else: meta["quality"] = "SD"
                except ValueError: pass
            
            if len(parts) >= 3:
                try:
                    d_probe = float(parts[2])
                    if d_probe > 0:
                        meta["duration"] = int(d_probe)
                except ValueError: pass
    except Exception: pass

    try:
        mi = MediaInfo.parse(path)
        for track in mi.tracks:
            if track.track_type == "Video":
                meta["duration"] = (
                    int(track.duration / 1000) if track.duration else meta["duration"]
                )
                meta["codec"] = track.codec or meta["codec"]
                if track.width:
                    w = int(track.width)
                    meta["width"] = w
                    if track.height:
                        meta["height"] = int(track.height)
                    if w >= 3840:
                        meta["quality"] = "2160p"
                    elif w >= 2560:
                        meta["quality"] = "1440p"
                    elif w >= 1920:
                        meta["quality"] = "1080p"
                    elif w >= 1280:
                        meta["quality"] = "720p"
                    else:
                        meta["quality"] = "SD"
            elif track.track_type == "Image":
                if track.width:
                    meta["width"] = int(track.width)
                if track.height:
                    meta["height"] = int(track.height)
            elif track.track_type == "General":
                if meta["duration"] is None and track.duration:
                    meta["duration"] = int(track.duration / 1000)
                if not meta["codec"] and track.codec:
                    meta["codec"] = track.codec
    except Exception:
        ext = os.path.splitext(path)[1].lower()
        meta["codec"] = ext.replace(".", "") if ext else ""
        meta["quality"] = ""

    return meta


def _run_ffmpeg(cmd: List[str]):
    """
    运行 ffmpeg 命令
    """
    subprocess.run(
        cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )


def generate_video_thumbnails_and_sprite(
    src_path: str,
    out_dir: str,
    video_type: str,
    thumb_width: int = 320,
    frame_count: int = 12,
    sprite_cols: int = 4,
) -> Dict[str, Any]:
    """
    从视频生成若干缩略图并合成雪碧图，返回结果包含缩略图目录和雪碧图路径
    video_type: "clip" | "movie"
    """

    ensure_dir_rw(out_dir)

    # 获取视频时长
    duration_cmd = [
        "ffprobe",
        "-v",
        "quiet",
        "-show_entries",
        "format=duration",
        "-of",
        "csv=p=0",
        src_path,
    ]

    try:
        duration_result = subprocess.run(
            duration_cmd, capture_output=True, text=True, check=True
        )
        duration = float(duration_result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError):
        duration = None

    # 生成帧缩略图：均匀分布在整个视频中
    thumb_pattern = os.path.join(out_dir, "thumb_%03d.jpg")

    if duration and duration > 0:
        interval = duration / (frame_count + 1)
        select_expr = "+".join(
            [f"eq(n,{int(i * interval * 25)})" for i in range(1, frame_count + 1)]
        )
        cmd = [
            "ffmpeg",
            "-y",
            "-i",
            src_path,
            "-vf",
            f"select='{select_expr}',scale={thumb_width}:-1",
            "-vsync",
            "vfr",
            "-frames:v",
            str(frame_count),
            thumb_pattern,
        ]
    else:
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            "10",
            "-i",
            src_path,
            "-vf",
            f"scale={thumb_width}:-1,fps=1/{max(1, int(60 / frame_count))}",
            "-vframes",
            str(frame_count),
            thumb_pattern,
        ]

    _run_ffmpeg(cmd)

    # 收集生成的缩略图
    thumbs = sorted(
        [
            os.path.join(out_dir, f)
            for f in os.listdir(out_dir)
            if f.startswith("thumb_") and f.endswith(".jpg")
        ]
    )
    if not thumbs:
        return {"thumbnail_dir": out_dir, "sprite_path": ""}

    # 合成雪碧图
    actual_count = len(thumbs)
    rows = math.ceil(actual_count / sprite_cols)

    first = Image.open(thumbs[0])
    w, h = first.size
    first.close()

    sprite = Image.new("RGB", (w * sprite_cols, h * rows), color=(0, 0, 0))
    for idx, img_path in enumerate(thumbs):
        img = Image.open(img_path)
        r = idx // sprite_cols
        c = idx % sprite_cols
        sprite.paste(img, (c * w, r * h))
        img.close()

    sprite_path = os.path.join(out_dir, "sprite.jpg")
    sprite.save(sprite_path, "JPEG", quality=90)
    sprite.close()

    return {
        "thumbnail_dir": out_dir,
        "sprite_path": sprite_path,
        "frame_count": actual_count,
        "sprite_cols": sprite_cols,
        "sprite_rows": rows,
        "frame_width": w,
        "frame_height": h,
    }

# 新增：图片缩略图（从 src/utils/media_processing.py 迁移）
def generate_image_thumbnail(
    src_path: str, out_dir: str, img_type: str, width: int = 320
) -> str:

    ensure_dir_rw(out_dir)
    img = Image.open(src_path)
    w, h = img.size
    new_h = int(h * (width / w))
    img = img.resize((width, new_h))
    out_path = os.path.join(out_dir, "thumb_001.jpg")
    img.save(out_path, "JPEG", quality=90)
    return out_path
