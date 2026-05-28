# ytb-downloader - 油管视频批量下载器

> 配置驱动的 YouTube 批量主题视频收集器 — 告诉它你要什么主题，自动找到并下载足够多的视频。

[EN](README.md) - 中文

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
