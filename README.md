# Epson L1119 Waste Ink Counter Reset

**English** | [中文](#中文说明)

USB-only tool that permanently clears the waste ink counter on Epson L1119 / ET-1110 family printers by talking directly to the EEPROM. No driver replacement, no Zadig, no proprietary adjustment program.

> Use it only on a printer you own or are authorized to service. Clearing the counter only lifts the software lock — it does **not** change the state of the physical waste ink pad.

## What it does

When the panel reports "the waste ink pad has reached the end of its service life", printing is refused because the main waste counter in EEPROM has hit 100%. This tool opens an IEEE 1284.4 (D4) session and reads and writes those EEPROM cells through EPSON-CTRL frames, bypassing the proprietary service program.

**Supported models:** `L1119`, `ET-1110`, plus `L1110 / L1118 / L3100–L3168 / L5190 / ET-111x / ET-271x / ET-4700`, which share the same keys and addresses.

## How it works

The D4 handshake is EJL ENTER sequence → D4 Init → OpenChannel. The L1119 runs firmware revision 0x0100, which speaks D4 revision 0x10. Every handshake step must be followed by a thorough drain, otherwise the firmware ignores the next request — `d4client.py` handles draining and retries.

EEPROM access uses the `||` command, framed as `name (2 bytes) + little-endian length (2 bytes) + payload`:

```
read : 7C 7C 07 00 <r1> <r2> 41 BE A0 <lo> <hi>
write: 7C 7C 10 00 <r1> <r2> 42 BD 21 <lo> <hi> <value> <wkey x8>
```

A read answers `EE:0032AC;`, an accepted write answers `||:OK;`, a refused write answers `||:NA;`.

**One trap worth knowing:** every byte of the write key is incremented by 1 before it goes on the wire. Plaintext `Maribaya` becomes `Nbsjcbzb`. If you send the unshifted key, the firmware still answers `:OK;` but silently discards the write — so this tool verifies every write by reading it back and trusts only the read-back, never the status code.

## Requirements

- Python 3.10 or newer
- One dependency: [`epson-usb`](https://pypi.org/project/epson-usb/) (Windows USBPRINT backend and EPSON-CTRL framing), verified on Windows

```
pip install -r requirements.txt
```

Make sure no Epson Status Monitor process holds the printer's USB interface, otherwise D4 Init fails.

## Usage

Read-only check — prints current and target values, writes nothing:

```
python epread.py
```

Dry run — reads `0x00–0x3F`, backs them up to JSON, prints the change plan, then stops:

```
python epwrite.py --dry-run
```

Full reset — backup → plan → probe the write key and confirm by read-back → batch write → verify the whole range:

```
python epwrite.py
```

Success prints `RESET COMPLETE and verified.` If you see `RESET INCOMPLETE`, roll back with the backup JSON written next to the script.

Diagnose a failing handshake byte by byte and list USB device paths:

```
python d4diag.py
```

## L1119 parameters

| Item | Value |
|---|---|
| read_key | `[0x97, 0x07]` |
| write_key (plain) | `Maribaya` |
| write_key (on the wire) | `Nbsjcbzb` (+1 shifted) |
| main waste counter | `0x30` (lo) `0x31` (hi), little-endian, value ÷ 63.46 = percent |
| borderless counter | `0x32` (lo) `0x33` (hi), little-endian, value ÷ 34.16 = percent |
| reset set | `0x1C/0x2F/0x30/0x31/0x32/0x33/0x34/0x35` → 0, `0x36/0x37` → `0x5E` |

These values are functional data taken from the public reinkpy model dictionary (see Credits); no upstream files are redistributed here.

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `D4 Init failed` | The USB port is held by the status monitor; stop the Epson processes and retry |
| `D4 OpenChannel failed` | Firmware revision isn't 0x10, or the pre-handshake drain was too short; the client retries three times |
| All writes answer `:OK;` but nothing changes | The write key wasn't shifted by +1; use `Nbsjcbzb` |
| `no candidate key committed` | No candidate key works; check whether the model belongs to this family |
| Device not found | Run `d4diag.py` to print the USBPRINT path and confirm `VID_04B8 / PID_00A8` is present |

## After the reset

Power the printer off for about 30 seconds and back on — the panel error disappears only after that. Then **replace or clean the waste ink pad**: a saturated pad leaks ink and degrades print quality. Clearing the counter is not a substitute for physical maintenance.

## Credits

The model data and protocol understanding here build on public projects:

- [reinkpy](https://codeberg.org/atufi/reinkpy) — source of the model dictionary (read/write keys and reset addresses)
- [epson_print_conf](https://github.com/Ircama/epson_print_conf) — reference for the D4/EEPROM protocol and the write-key shift convention, EUPL-1.2
- [epson-usb](https://pypi.org/project/epson-usb/) — the USB transport and framing library this tool depends on

## License

MIT, see [LICENSE](LICENSE).

---

## 中文说明

[English](#epson-l1119-waste-ink-counter-reset) | **中文**

通过 USB 直连读写打印机 EEPROM，把 L1119 / ET-1110 家族的废墨计数器永久清零。不改驱动、不装 Zadig、不依赖任何第三方调整程序。

> 仅用于你本人拥有或获授权维护的打印机。复位只解除软件锁定，**不会**改变物理废墨垫的吸墨状态。

### 这是什么

打印机面板提示"废墨收集垫已到使用寿命"时，打印会被拒绝，原因是 EEPROM 里的主废墨计数达到 100%。本工具用 IEEE 1284.4（D4）会话 + EPSON-CTRL 帧直接读写那几格 EEPROM，绕过需要专有调整程序的路径。

覆盖机型：`L1119`、`ET-1110`，以及共享同一组密钥与地址的 `L1110 / L1118 / L3100–L3168 / L5190 / ET-111x / ET-271x / ET-4700` 等。

### 原理

D4 握手顺序为 EJL ENTER 序列 → D4 Init → OpenChannel。L1119 固件版本 0x0100，对应 D4 revision 0x10。握手每一步之间必须充分排空（drain），否则固件会忽略紧随上一条回复发来的请求——`d4client.py` 已封装排空与重试。

EEPROM 访问走 `||` 命令，帧格式为 `名称(2 字节) + 小端长度(2 字节) + 载荷`：

```
读: 7C 7C 07 00 <r1> <r2> 41 BE A0 <lo> <hi>
写: 7C 7C 10 00 <r1> <r2> 42 BD 21 <lo> <hi> <value> <wkey x8>
```

读成功回 `EE:0032AC;`，写成功回 `||:OK;`，写被拒回 `||:NA;`。

**一个容易踩的坑**：写密钥上线前要逐字节 +1。明文 `Maribaya` 位移后是 `Nbsjcbzb`。发未位移的密钥时，固件照样回 `:OK;`，但会静默丢弃写入——所以本工具的每一次写入都会读回比对，只认读回结果，不认状态码。

### 环境要求

- Python 3.10 及以上
- 唯一的依赖是 [`epson-usb`](https://pypi.org/project/epson-usb/)（提供 Windows USBPRINT 后端与 EPSON-CTRL 帧构造），已在 Windows 上实测

```
pip install -r requirements.txt
```

执行前请确认没有 Epson 状态监视器进程占用打印机 USB 接口，否则 D4 Init 会失败。

### 用法

只读检测，打印各地址的现值与目标值，不写任何东西：

```
python epread.py
```

干跑，读全 `0x00–0x3F` 并备份为 JSON、打印变更计划后停下：

```
python epwrite.py --dry-run
```

正式复位，流程为备份 → 计划 → 密钥探测并读回确认 → 批量写入 → 全量读回校验：

```
python epwrite.py
```

输出末尾出现 `RESET COMPLETE and verified.` 即成功。若报 `RESET INCOMPLETE`，可用同目录生成的备份 JSON 回滚。

握手失败时用诊断脚本逐字节跟踪并列出 USB 设备路径：

```
python d4diag.py
```

### L1119 参数

| 项目 | 值 |
|---|---|
| read_key | `[0x97, 0x07]` |
| write_key 明文 | `Maribaya` |
| write_key 上线值 | `Nbsjcbzb`（+1 位移后） |
| 主废墨计数 | `0x30`(低) `0x31`(高)，小端，值 ÷ 63.46 = 百分比 |
| 无边距计数 | `0x32`(低) `0x33`(高)，小端，值 ÷ 34.16 = 百分比 |
| 复位地址集 | `0x1C/0x2F/0x30/0x31/0x32/0x33/0x34/0x35` 清 0，`0x36/0x37` 置 `0x5E` |

这些数值属于功能性事实数据，来源于公开的 reinkpy 机型字典（见下方致谢），本仓库不转发上游文件。

### 排错

| 现象 | 原因与处理 |
|---|---|
| `D4 Init failed` | USB 端口被状态监视器占用，停掉 Epson 进程后重试 |
| `D4 OpenChannel failed` | 固件 revision 不是 0x10，或握手前未充分排空；客户端会自动重试三次 |
| 所有写入返回 `:OK;` 但读回不变 | 写密钥未做 +1 位移，改用 `Nbsjcbzb` |
| `no candidate key committed` | 候选密钥都无效，确认机型是否属于本家族 |
| 找不到设备 | 用 `d4diag.py` 打印 USBPRINT 路径，确认 `VID_04B8 / PID_00A8` 在线 |

### 收尾

复位后给打印机断电约 30 秒再开机，面板报错才会消失。随后**更换或清理废墨收集垫**——垫子吸满后继续打印会漏墨并影响打印质量。复位不是物理维护的替代品。

### 来源与致谢

本工具的机型数据与协议理解建立在几个公开项目之上：

- [reinkpy](https://codeberg.org/atufi/reinkpy)：机型字典（读/写密钥与复位地址）的来源
- [epson_print_conf](https://github.com/Ircama/epson_print_conf)：D4/EEPROM 协议实现与写密钥位移约定的参考，EUPL-1.2
- [epson-usb](https://pypi.org/project/epson-usb/)：本工具依赖的 USB 传输与帧构造库

### 许可证

MIT，见 [LICENSE](LICENSE)。
