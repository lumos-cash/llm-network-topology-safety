# OSPF 单故障注入与修复记录（Packet Tracer 9.0.1）

本记录仅针对课程工程副本。正常基线是 `pt-work/ospf_deployment_working.pkt`；故障快照是 `pt-work/ospf_fault_shutdown_injected.pkt`；修复后的工作副本是 `pt-work/ospf_fault_shutdown_working.pkt`。课程原件与 `lab4_11_reference.pkt` 未改动。

| 阶段 | 操作和实测 | 原始证据 |
|---|---|---|
| 故障注入 | 在 Router0 的 `GigabitEthernet0/0` 下执行 `shutdown`，保存 NVRAM 和 PKT | `running-configs/Router0.txt`、故障快照 PKT |
| 故障验收 | PC0→PC1 `ping 192.168.16.129`，0/4；独立 oracle：fail 1、not_run 4 | `PC0-failed-ping.txt`、`observations-fault.json`、`runs/20261016T021921Z-verify-a4b7fa5e/` |
| 修复（第 1 轮） | Router0 G0/0 执行 `no shutdown`，保存 NVRAM 和 PKT；运行配置与故障配置逐行比较，唯一消失的命令是该接口下的 `shutdown` | `Router0-repaired-running-config.txt`、修复工作副本 PKT |
| 修复后首次测试 | PC0→PC1 ping 3/4；首包超时，后 3 包有回复 | `PC0-repaired-ping-first.txt` |
| 修复后复测 | 同一方向 ping 4/4，丢包率 0%；独立 oracle：pass 1、not_run 4 | `PC0-repaired-ping-complete.txt`、`observations-repaired.json`、`runs/20261016T105540Z-verify-7fae1e91/` |

故障现象与接口关闭一致，`no shutdown` 后恢复了本故障影响的端到端连通性。第二次 ping 的 4/4 是实际 PT 输出，不把首次 3/4 改写为成功。修复轮数为 1；本记录只有 1 个实际故障样本，不据此推断一般排障成功率。

故障注入、配置修复、PT 命令采集和 PKT 保存均经 GUI 人工操作；程序负责导入证据、解析与独立 oracle 判定。修复后只重新采集了 PC0→PC1 ping，原正常基线 5/5 不能代替修复后的其余四项；因此不称修复后“全项验收通过”。DeepSeek 故障诊断调用尚未执行，不能把这次修复归因为模型建议。

PKT SHA256：故障快照 `8A3364CAB1A8A35596FE5414813730BF4B26D74F9835464DBA2D04D9A3CB2EC1`；修复工作副本 `59F241FDFF5D4293E3918F39361A5DBAFCB86F26E79EDC9A572A7C40DB263D9E`。

待审批 DeepSeek 输入的**本地预览**是 `deepseek-diagnosis-input-preview.json`，SHA256 `31CC8747C8CF7A3450FB611250B5E5A693A5A7FC1D13681AAA17383E05B820FE`。它包含实验 IP、三台模拟路由器的运行配置和设备序列号；未包含 API 密钥。只有用户明确允许发送这份内容到 DeepSeek 后，才能执行外部诊断。
