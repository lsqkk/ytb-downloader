# ytb-downloader

> 基于 yt-dlp 的可配置 YouTube 批量视频下载器。配置类别、搜索关键词和数量限制，即可自动搜索并下载。

## 功能

- **批量下载** — 按类别并行下载，支持断点续传
- **可配置** — YAML 配置文件，自定义类别、搜索词、数量、画质
- **Web 监控面板** — 实时查看下载进度、速度、日志，自动停滞检测
- **智能搜索** — 多关键词多轮搜索，自动去重，跳过已下载
- **代理支持** — 配合 Clash / V2Ray 使用

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

需要 `yt-dlp` 已安装且在 PATH 中：[yt-dlp 安装指南](https://github.com/yt-dlp/yt-dlp#installation)

### 2. 配置

编辑 `config.yaml`：

```yaml
proxy: "http://127.0.0.1:7890"   # 代理地址（必填，否则 YouTube 会屏蔽）
cookies: "cookies.txt"            # YouTube 登录 cookie
workers: 3                        # 并行下载数
output_dir: "downloads"           # 下载目录

categories:
  - name: my_category             # 文件夹名（会存到 output_dir/ 下）
    target: 40                    # 目标视频数
    queries:                      # 搜索关键词（轮询，去重）
      - "my category tutorial"
      - "my category workout"
```

### 3. 获取 Cookie

1. 浏览器登录 [YouTube](https://www.youtube.com)
2. 安装 [Get cookies.txt](https://chrome.google.com/webstore/detail/get-cookiestxt/bgaddhkoddajcdgocldbbfleckgcbcid) 扩展
3. 在 YouTube 页面上点击扩展 → **Export**（Netscape 格式）
4. 保存为 `cookies.txt` 到项目根目录

> **没有 cookie 文件，YouTube 会返回 "Sign in to confirm you're not a bot" 并拒绝下载。**

### 4. 开始下载

```bash
# 启动下载 + 命令行显示进度
python -m ytb_downloader start

# 单独开一个终端启动 Web 监控面板
python -m ytb_downloader monitor --port 8080

# 或者先检查配置是否正确
python -m ytb_downloader check
```

然后浏览器打开 [http://localhost:8080](http://localhost:8080) 查看实时进度。

## 命令参考

| 命令 | 说明 | 示例 |
|------|------|------|
| `start` | 启动批量下载 | `python -m ytb_downloader start -w 4` |
| `monitor` | 启动 Web 监控面板 | `python -m ytb_downloader monitor --port 8080` |
| `status` | 查看当前状态 | `python -m ytb_downloader status` |
| `list` | 列出所有类别及进度 | `python -m ytb_downloader list` |
| `check` | 验证配置文件 | `python -m ytb_downloader check -c my_config.yaml` |

### start 选项

| 参数 | 说明 |
|------|------|
| `-c, --config` | 指定配置文件路径 |
| `-w, --workers` | 并行下载数（覆盖配置） |
| `-p, --proxy` | 代理地址（覆盖配置） |
| `-l, --limit` | 所有类别统一重设目标数 |

## 配置文件

完整配置项见 `config.yaml`，所有字段都有默认值：

```yaml
# 网络
proxy: "http://127.0.0.1:7890"
cookies: "cookies.txt"

# 下载
workers: 3
output_dir: "downloads"
max_duration: 600           # 最长时长（秒），0=不限
max_filesize: "300M"         # 单文件上限
video_format: "bestvideo[height<=720]+bestaudio/best[height<=720]"

# 重试
search_retries: 3
download_retries: 5

# 类别列表（可任意扩展）
categories:
  - name: example_category
    target: 40
    queries:
      - "search query 1"
      - "search query 2"
```

### 多配置文件

可以为不同数据集创建不同配置：

```bash
python -m ytb_downloader start -c config_rac.yaml
python -m ytb_downloader start -c config_sports.yaml
```

每个配置独立存储下载状态和日志，互不干扰。

## 监控面板

Web 监控面板提供：

- 总体进度（完成类别数、总下载数、失败数）
- 每类别进度条（已有/目标）
- 当前正在下载的视频
- **停滞检测** — 3 分钟无新增视频自动告警，提示检查 Cookie 或代理
- 实时运行日志
- 配置摘要（worker 数、代理、时长上限）

## 测试

```bash
# 安装测试依赖
pip install pytest pytest-cov

# 运行测试
python run_tests.py
```

## 项目结构

```
ytb-downloader/
├── README.md
├── config.yaml              # 主配置文件
├── requirements.txt         # Python 依赖
├── cookies.txt.example      # Cookie 文件格式示例
├── run_tests.py             # 测试入口
├── conftest.py              # pytest 配置
├── ytb_downloader/
│   ├── __init__.py
│   ├── __main__.py          # python -m ytb_downloader 入口
│   ├── cli.py               # 命令行解析
│   ├── config.py            # 配置加载与验证
│   ├── engine.py            # 下载引擎
│   ├── state.py             # 状态管理
│   └── monitor.py           # Web 监控面板
├── tests/
│   ├── test_config.py
│   ├── test_state.py
│   └── test_utils.py
├── downloads/               # 下载输出（自动创建）
└── cookies.txt              # YouTube Cookie（需自行准备）
```
