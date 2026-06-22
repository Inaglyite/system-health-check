# System Health Check

跨平台（Windows / Linux）系统硬件健康检查工具。

## 快速开始（Windows）

下载 [healthcheck-gui.exe](../../releases/latest)，双击运行即可。无需安装 Python！

> ⚠️ **注意**：Release 中的 exe 是 v0.1.0 旧版本，**不包含** `--threshold-override` 修复和 SMART 模块的 bug 修复。如需最新代码，请用下面的[命令行方式](#命令行使用)或从源码运行。新版本 exe 将在下次 Windows 环境打包后更新。

## 命令行使用

```bash
# 安装依赖（仅首次）
pip install -r requirements.txt

# 运行全部检查
python -m healthcheck.main

# JSON 输出
python -m healthcheck.main -o json

# HTML 报告
python -m healthcheck.main -o html -f report.html

# 只检查特定模块
python -m healthcheck.main -m cpu,memory,disk

# 覆盖阈值
python -m healthcheck.main --threshold-override cpu_percent=90
```

## 打包 exe

```bash
pip install pyinstaller
pyinstaller healthcheck-gui.spec --clean --noconfirm
```

输出：`dist/healthcheck-gui.exe`

## 开发

```bash
# 安装开发依赖
pip install -r requirements.txt pytest

# 运行测试
python -m pytest tests/ -v
```

## 项目结构

```
healthcheck/
├── gui.py            # GUI 界面 (tkinter)
├── main.py           # CLI 入口
├── report.py         # Console / JSON / HTML 报告
├── config.py         # 配置加载
├── config.yaml       # 默认阈值
├── cpu.py            # CPU 检查
├── memory.py         # 内存检查
├── disk.py           # 磁盘检查
├── smart.py          # S.M.A.R.T. 磁盘健康
├── network.py        # 网络检查
├── temperature.py    # 温度检查
├── i18n.py           # 中英文翻译
└── dataclasses.py    # 共享数据结构
```

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 全部正常 |
| 1 | 有警告 |
| 2 | 有严重问题 |
| 3 | 检查出错 |

## 平台支持

| 模块 | Windows | Linux |
|------|---------|-------|
| cpu | psutil + PowerShell/WMI | psutil + /proc/cpuinfo |
| memory | psutil | psutil + /proc/meminfo |
| disk | psutil | psutil + statvfs |
| smart | PowerShell Get-PhysicalDisk | smartctl |
| network | psutil + ping | psutil + ping |
| temperature | WMI | psutil + lm-sensors |
