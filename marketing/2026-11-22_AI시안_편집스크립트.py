"""Assemble the 30s preview reel: trim clips, concat, burn Korean captions."""
import os
import subprocess
import sys

clips_dir, out_path, work = sys.argv[1], sys.argv[2], sys.argv[3]
B = "/usr/share/fonts/truetype/nanum/NanumSquareB.ttf"
R = "/usr/share/fonts/truetype/nanum/NanumSquareR.ttf"

# (file, start offset in clip, length) -> timeline 3/7/9/4/4/3 = 30s
SEGS = [
    ("c1.mp4", float(os.environ.get("C1_SS", "1.5")), 3.0),
    ("c2.mp4", 0.0, 7.0),
    ("c3.mp4", 0.25, 4.5),
    ("c4.mp4", 0.25, 4.5),
    ("c5.mp4", 0.5, 4.0),
    ("c6.mp4", 0.5, 4.0),
    ("c7.mp4", 1.0, 3.0),
]

# (text, start, end, y as fraction of height, font size, font, kind)
TOP1, TOP2 = 0.175, 0.215
MID1, MID2 = 0.30, 0.355
CAPS = [
    ("[광고] 한국발보린 제작", 0.0, 3.0, TOP1, 44, B, "band"),
    ("표기는 차종마다 다를 수 있어요", 3.0, 19.0, TOP1, 44, B, "band"),
    ("엔진·배기 부위 뜨거움 주의", 3.0, 19.0, TOP2, 44, B, "warn"),
    ("[광고] 한국발보린 제작", 27.0, 30.0, TOP1, 44, B, "band"),
    ("첫 영하 오기 전에", 0.0, 3.0, MID1, 62, B, "main"),
    ("엔진오일 이 3가지부터", 0.0, 3.0, MID2, 62, B, "main"),
    ("1. 레벨", 3.0, 10.0, MID1, 62, B, "main"),
    ("설명서에 안내된 시간만큼 대기 후", 5.5, 10.0, MID2, 50, B, "main"),
    ("눈금(MIN~MAX 또는 L~F) 사이", 10.0, 19.0, MID1, 54, B, "main"),
    ("MAX·F를 넘지 않게", 12.5, 19.0, MID2, 54, B, "main"),
    ("2. 점도", 19.0, 23.0, MID1, 62, B, "main"),
    ("차량 취급설명서 권장 사양 우선", 19.0, 23.0, MID2, 50, B, "main"),
    ("3. 교환 시기", 23.0, 27.0, MID1, 62, B, "main"),
    ("설명서 가혹 조건도 확인", 23.0, 27.0, MID2, 50, B, "main"),
    ("점검 문의는 가까운 정비소로", 27.0, 30.0, MID1, 58, B, "main"),
    ("발보린 Turbo CX10 5W30", 27.0, 30.0, MID2 + 0.01, 50, B, "main"),
    ("AI 생성 영상 · 내부 검토용 시안", 0.0, 30.0, 0.585, 30, R, "note"),
]
STYLE = {
    "band": "fontcolor=white:box=1:boxcolor=black@0.62:boxborderw=16",
    "warn": "fontcolor=0xFFD84D:box=1:boxcolor=black@0.62:boxborderw=16",
    "main": "fontcolor=white:borderw=5:bordercolor=black@0.85:shadowx=2:shadowy=2:shadowcolor=black@0.6",
    "note": "fontcolor=white@0.75:borderw=2:bordercolor=black@0.6",
}

os.makedirs(work, exist_ok=True)
parts = []
for i, (name, ss, dur) in enumerate(SEGS):
    part = os.path.join(work, f"p{i}.mp4")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", str(ss), "-i", os.path.join(clips_dir, name),
         "-t", str(dur), "-an",
         "-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,fps=30,setsar=1",
         "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", part],
        check=True)
    parts.append(part)

lst = os.path.join(work, "list.txt")
with open(lst, "w") as f:
    for p in parts:
        f.write(f"file '{p}'\n")

filters = []
for n, (text, a, b, y, size, font, kind) in enumerate(CAPS):
    tf = os.path.join(work, f"t{n}.txt")
    with open(tf, "w", encoding="utf-8") as f:
        f.write(text)
    filters.append(
        f"drawtext=fontfile={font}:textfile={tf}:fontsize={size}:x=(w-text_w)/2:y=h*{y}:"
        f"{STYLE[kind]}:enable='between(t,{a},{b - 0.001})'")

subprocess.run(
    ["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", lst,
     "-vf", ",".join(filters), "-an", "-c:v", "libx264", "-preset", "medium", "-crf", "20",
     "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path],
    check=True)
print("wrote", out_path)
