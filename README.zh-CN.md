# slap_cc

英文版说明见 [README.md](README.md)。

`slap_cc` 可以把你拍一下 Apple Silicon MacBook 机身产生的物理冲击，转换成一条发送到当前聚焦聊天界面的 prompt。

这个项目会读取笔记本的 IMU 数据，检测短促的冲击峰值，从提示词池中选出一条 prompt，粘贴到最前台应用里并提交。它最初的用途，是在不碰键盘的情况下“提醒” Claude Code 继续干活。

## 工作原理

1. 通过 `macimu` 读取 Apple Silicon IMU 的加速度计采样
2. 跟踪一个缓慢变化的重力基线
3. 计算动态加速度的模长
4. 当冲击超过阈值且冷却时间已结束时触发
5. 从 `prompt_pool.json` 中选择一条 prompt
6. 将 prompt 粘贴到当前聚焦应用中，并按下 `Enter`

## 运行要求

- Apple Silicon MacBook
- macOS
- Python 3.10+
- 需要 `sudo` 才能读取 IMU
- 用于启动自动化流程的应用需要具备辅助功能权限

说明：

- IMU 访问路径是 macOS 专用的。
- 聊天提交路径依赖“最前台应用自动化”。探测器启用时，请保持 Claude Code 或目标聊天界面处于前台焦点。

## 项目结构

- `slap_detector.py`：冲击检测器和动作分发逻辑
- `prompt_pool.json`：实时发送时使用的 prompt 列表
- `requirements.txt`：Python 依赖列表

## 安装

```bash
cd slap_cc
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 快速开始

先做一次不发送任何内容的基础检查：

```bash
sudo .venv/bin/python3 slap_detector.py --dry-run --debug
```

在没有硬件输入的情况下运行模拟信号：

```bash
.venv/bin/python3 slap_detector.py --mock --dry-run
```

对当前聚焦应用启用真实硬件流程：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost
```

把它挂到后台，这样你可以把焦点切回 Claude Code：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost > slap.log 2>&1 &
```

## 辅助功能权限

如果 macOS 用下面这样的报错拦截了发送流程：

```text
osascript is not allowed to send keystrokes. (1002)
```

请在以下位置开启辅助功能权限：

`系统设置 > 隐私与安全性 > 辅助功能`

通常需要放行：

- `Terminal` 或 `iTerm`
- `System Events`
- 任何用于启动该脚本的辅助进程

如果 prompt 已经出现在聊天输入框里，但要等到下一次拍击才会真正提交，可以调大“粘贴到提交”的延迟：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --submit-delay-ms 300
```

## 用法

基础实时运行：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost
```

每次都使用同一条固定 prompt：

```bash
sudo .venv/bin/python3 slap_detector.py \
  --action frontmost \
  --prompt "find the root cause and fix it"
```

使用自定义 prompt 文件：

```bash
sudo .venv/bin/python3 slap_detector.py \
  --action frontmost \
  --prompts-file my_prompts.json
```

执行 dry-run，同时仍然显示检测到的 prompt：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --dry-run --debug
```

使用原始键入而不是剪贴板粘贴：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --send-mode type
```

插入 prompt 但不提交：

```bash
sudo .venv/bin/python3 slap_detector.py --action frontmost --no-enter
```

## 参数调优

默认值刻意设置得比较敏感：

- `--threshold-g 0.28`
- `--cooldown-ms 350`
- `--gravity-alpha 0.01`
- `--submit-delay-ms 180`

常用调整方向：

- 轻拍也要触发：降低 `--threshold-g`
- 减少误触发：提高 `--threshold-g` 或 `--cooldown-ms`
- 两次拍击之间更快恢复：降低 `--cooldown-ms`
- 粘贴后更稳定地提交聊天：提高 `--submit-delay-ms`

示例：

```bash
sudo .venv/bin/python3 slap_detector.py \
  --action frontmost \
  --threshold-g 0.20 \
  --submit-delay-ms 300 \
  --debug
```

## Prompt 池格式

`prompt_pool.json` 必须是一个字符串数组：

```json
[
  "continue working on the current task",
  "find the root cause and fix it",
  "verify the implementation instead of assuming it works"
]
```

## 故障排查

`No compatible AppleSPU IMU was found`

- 请确认这是带有对应传感器路径的 Apple Silicon MacBook。

`Run with sudo so Python can access the AppleSPU HID device`

- 请使用 `sudo` 启动硬件模式。

Prompt 已粘贴但没有发送

- 提高 `--submit-delay-ms`
- 确认目标应用当前处于焦点

聊天界面里完全没有反应

- 确认已开启辅助功能权限
- 确认你要控制的应用处于最前台
- 先试 `--dry-run --debug`，把“检测问题”和“界面自动化问题”分开排查

误触发太多

- 提高 `--threshold-g`
- 提高 `--cooldown-ms`

## 安全说明

- 这个工具会向最前台应用发送输入。如果当前焦点在别的应用上，不要启用它。
- 只有在你明确知道哪个应用会接收 prompt 时，才把探测器挂到后台运行。
- 如果你在做真实联调，请先从 `--dry-run` 开始。

## 发布前检查清单

在创建仓库之前：

1. 检查 `prompt_pool.json`，删除任何你不希望公开的内容。
2. 确认 `.venv`、日志和缓存文件都已被忽略。
3. 决定是否要添加许可证。
4. 在一个全新克隆环境里实际跑一遍 README 中的命令。

## 许可证

当前仓库还没有附带许可证文件。如果你希望其他人在明确授权条款下复用这份代码，请在发布前添加许可证。
