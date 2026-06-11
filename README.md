# System Health Check

跨平台（Windows / Linux）系统硬件健康检查工具。

## 快速使用（Windows exe）

直接下载 `healthcheck-gui.exe`，双击运行即可看到图形界面。无需安装 Python！

## 项目结构

```
healthcheck/
├── __init__.py       # 包元数据
├── dataclasses.py    # 共享数据结构 (HealthStatus, MetricValue, ModuleResult, Threshold)
├── config.py         # YAML 配置加载器
├── config.yaml       # 默认阈值配置
├── cpu.py            # CPU 信息、使用率、频率、负载
├── memory.py         # RAM + Swap 使用率
├── disk.py           # 磁盘分区、使用率、I/O
├── smart.py          # S.M.A.R.T. 磁盘健康状态
├── network.py        # 网络接口、流量、ping 测试
├── temperature.py    # CPU/GPU 温度
├── report.py         # 报告生成 (Console/JSON/HTML)
└── main.py           # CLI 入口，编排器
```

## 依赖

- Python >= 3.8
- psutil >= 5.9.0
- rich >= 13.0.0
- PyYAML >= 6.0

## 安装

```bash
pip install -r requirements.txt
```

## 使用方法

```bash
# 运行全部检查（终端彩色输出）
python -m healthcheck.main

# JSON 输出
python -m healthcheck.main -o json

# HTML 报告
python -m healthcheck.main -o html -f report.html

# 只检查特定模块
python -m healthcheck.main -m cpu,memory,disk

# 详细模式（per-core CPU）
python -m healthcheck.main -v

# 静默模式（只显示警告和错误）
python -m healthcheck.main -q

# 覆盖阈值
python -m healthcheck.main --threshold-override cpu_percent=90,memory_percent=85

# 列出可用模块
python -m healthcheck.main --list-modules
```

## 打包为 exe（Windows）

```bash
# 在 Windows 上安装 PyInstaller
pip install pyinstaller

# 构建 exe
pyinstaller healthcheck-gui.spec --clean --noconfirm

# 或者直接运行
build_exe.bat
```

输出文件：`dist/healthcheck-gui.exe` (~14 MB)，双击即可运行 GUI。

## 部署到 Windows VM 测试

```bash
# 1. 复制文件到 Windows VM
scp -r healthcheck/ requirements.txt Inaglyite@192.168.129.54:/Users/Inaglyite/

# 2. SSH 到 VM 并安装依赖
ssh Inaglyite@192.168.129.54
pip install -r requirements.txt

# 3. 运行检查
python -m healthcheck.main -o json
python -m healthcheck.main -o html -f health_report.html
```

## 退出码

| 退出码 | 含义 |
|--------|------|
| 0 | 所有检查 OK |
| 1 | 有 WARNING 级别问题 |
| 2 | 有 CRITICAL 级别问题 |
| 3 | 检查过程中出错 |

## 平台支持

| 模块 | Windows | Linux |
|------|---------|-------|
| cpu | psutil + PowerShell/WMI | psutil + /proc/cpuinfo |
| memory | psutil | psutil + /proc/meminfo |
| disk | psutil | psutil + statvfs (inodes) |
| smart | PowerShell Get-PhysicalDisk | smartctl |
| network | psutil + ping -n | psutil + ping -c |
| temperature | WMI (可能 N/A on VMs) | psutil sensors_temperatures |
