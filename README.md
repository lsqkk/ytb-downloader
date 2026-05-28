# ytb-downloader

> Config-driven YouTube batch topic collector — tell it what topics you want,
> it finds and downloads enough videos automatically.

[中文版本](#中文版)

---

## Overview

**ytb-downloader** is a configuration-driven batch downloader for YouTube. Unlike
typical downloaders that require you to paste individual URLs, ytb-downloader
works from a YAML config: define categories with search keywords and quantity
targets, and it handles search, deduplication, parallel downloading, and resume
automatically.

### Why not just use yt-dlp directly?

| You want... | yt-dlp | ytb-downloader |
|-------------|--------|----------------|
| Download one video by URL | ✅ `yt-dlp <url>` | ✅ `ytb-downloader dl <url>` |
| Download a playlist | ✅ | ❌ (planned) |
| **Search + bulk download by topic** | ❌ manual loop | ✅ config-driven |
| **Multiple keyword groups** | ❌ one at a time | ✅ categories with auto-dedup |
| **Parallel category downloads** | ❌ | ✅ thread pool per category |
| **Resume partial downloads** | ❌ | ✅ disk + JSON tracking |
| **Web monitoring dashboard** | ❌ | ✅ real-time dashboard |

### When to use ytb-downloader

- You want to build a video dataset on specific topics (e.g., "tutorials", "workouts")
- You need to periodically refresh a video collection by re-running a config
- You prefer defining download jobs in a config file over CLI arguments

---

## Features

- **Batch topic search** — define categories with keywords, auto-deduplicate
- **Single URL download** — `ytb-downloader dl <url>` for quick grabs
- **Config-driven** — YAML file defines everything: categories, targets, quality
- **Parallel category processing** — concurrent downloads across categories
- **Resume support** — skips already-downloaded videos on re-run
- **Web dashboard** — real-time progress, stall detection, logs
- **Proxy support** — works with Clash / V2Ray
- **Retry logic** — automatic retries for search and download failures

---

## Quick Start

### Install

```bash
pip install -r requirements.txt
```

Requires `yt-dlp` binary on your PATH: [yt-dlp installation guide](https://github.com/yt-dlp/yt-dlp#installation)

### 1. Configuration

Edit `config.yaml`:

```yaml
proxy: "http://127.0.0.1:7890"
cookies: "cookies.txt"
workers: 3
output_dir: "downloads"

categories:
  - name: my_category
    target: 40
    queries:
      - "my category tutorial"
      - "my category workout"
```

### 2. Get Cookies

1. Log into [YouTube](https://www.youtube.com)
2. Install [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid)
3. On YouTube, click the extension → **Export** (Netscape format)
4. Save as `cookies.txt` in the project root

### 3. Start Downloading

```bash
# Batch download by categories
ytb-downloader start

# Or if not installed:
python -m ytb_downloader start

# Single video download
ytb-downloader dl "https://youtube.com/watch?v=..."

# Web monitoring dashboard
ytb-downloader monitor --port 8080
```

Then open http://localhost:8080 for live progress.

---

## Command Reference

| Command | Description | Example |
|---------|-------------|---------|
| `start` | Start batch download | `ytb-downloader start -w 4` |
| `dl <url>` | Download single video | `ytb-downloader dl "https://..."` |
| `monitor` | Start web dashboard | `ytb-downloader monitor --port 8080` |
| `status` | Show download progress | `ytb-downloader status` |
| `list` | List all categories | `ytb-downloader list` |
| `check` | Validate config file | `ytb-downloader check -c my_config.yaml` |

### start options

| Flag | Description |
|------|-------------|
| `-c, --config` | Path to config file |
| `-w, --workers` | Parallel workers (overrides config) |
| `-p, --proxy` | Proxy URL (overrides config) |
| `-l, --limit` | Override target for all categories |

### dl options

| Flag | Description |
|------|-------------|
| `-c, --config` | Path to config file (for proxy/cookies settings) |
| `-p, --proxy` | Proxy URL |
| `-o, --output` | Output directory |

---

## Full Config Reference

```yaml
# Network
proxy: "http://127.0.0.1:7890"
cookies: "cookies.txt"

# Download
workers: 3
output_dir: "downloads"
max_duration: 600           # max video length (seconds), 0 = no limit
max_filesize: "300M"         # max file size per video
video_format: "bestvideo[height<=720]+bestaudio/best[height<=720]"

# Retry
search_retries: 3
download_retries: 5

# Categories
categories:
  - name: example_category
    target: 40
    queries:
      - "search query 1"
      - "search query 2"
```

### Multiple config files

Create different configs for different datasets:

```bash
ytb-downloader start -c config_workout.yaml
ytb-downloader start -c config_cooking.yaml
```

Each config maintains its own download state and logs.

---

## Web Dashboard

The real-time dashboard provides:

- Overall progress (completed categories, total downloads, failures)
- Per-category progress bars
- Currently downloading video
- **Stall detection** — alerts if no new videos for 3 minutes
- Live log stream
- Config summary (workers, proxy, limits)

---

## Project Structure

```
ytb-downloader/
├── README.md                 # This file
├── LICENSE                   # MIT License
├── pyproject.toml            # Package config + CLI entry
├── config.yaml               # Main config file
├── requirements.txt          # Python dependencies
├── cookies.txt.example       # Cookie file format example
├── run_tests.py              # Test runner
├── conftest.py               # Pytest config
├── .github/workflows/ci.yml  # CI pipeline
├── ytb_downloader/
│   ├── __init__.py
│   ├── __main__.py           # python -m entry
│   ├── cli.py                # CLI argument parsing
│   ├── config.py             # Config loader + validator
│   ├── engine.py             # Download engine (class-based)
│   ├── state.py              # State management with write throttling
│   ├── monitor.py            # Web monitoring dashboard
│   └── templates/
│       └── monitor.html      # Dashboard HTML template
└── tests/
    ├── test_config.py
    ├── test_state.py
    ├── test_engine.py         # Mock-based engine tests
    └── test_utils.py
```

---

## Testing

```bash
# Install test dependencies
pip install pytest pytest-cov

# Run tests
python run_tests.py
```

---

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

MIT

---

## 中文版

> 配置驱动的 YouTube 批量主题视频收集器 — 告诉它你要什么主题，自动找到并下载足够多的视频。

### 项目定位

**ytb-downloader** 是一个配置驱动的 YouTube 批量下载工具。与需要逐个粘贴 URL 的下载器不同，它在 YAML 配置文件中定义类别、搜索关键词和目标数量，自动完成搜索、去重、并行下载和断点续传。

**核心价值主张：** 告诉它你要什么主题，它自动找到并下载足够多的视频。

**适用场景：**
- 按主题构建视频数据集（如教程、健身、烹饪）
- 定期刷新视频收藏（重新运行同一配置即可）
- 偏好配置文件驱动而非命令行参数

### 安装

```bash
pip install -r requirements.txt
```

需要 `yt-dlp` 已安装且在 PATH 中。

### 快速使用

```bash
# 批量下载（按配置文件中的类别）
ytb-downloader start

# 单视频下载
ytb-downloader dl "https://youtube.com/watch?v=..."

# Web 监控面板
ytb-downloader monitor --port 8080

# 查看状态
ytb-downloader status

# 验证配置
ytb-downloader check
```

### 配置

编辑 `config.yaml`，定义类别和搜索关键词：

```yaml
proxy: "http://127.0.0.1:7890"
cookies: "cookies.txt"
workers: 3
output_dir: "downloads"

categories:
  - name: 健身教程
    target: 40
    queries:
      - "home workout beginner"
      - "bodyweight exercise"
```

### 与 yt-dlp 的区别

| 功能 | yt-dlp | ytb-downloader |
|------|--------|----------------|
| 按 URL 下载单个视频 | ✅ | ✅ `dl <url>` |
| 下载播放列表 | ✅ | ❌（规划中） |
| **按关键词搜索批量下载** | ❌ 需手动循环 | ✅ 配置驱动 |
| **多关键词分组去重** | ❌ 一次一个 | ✅ 自动去重 |
| **并行类别下载** | ❌ | ✅ 线程池 |
| **断点续传** | ❌ | ✅ 磁盘+JSON 追踪 |
| **Web 监控面板** | ❌ | ✅ 实时仪表盘 |
