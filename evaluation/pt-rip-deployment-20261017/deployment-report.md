# 4-10 RIPv2 模型配置 PT 部署与验收

本记录对应 `pt-work/ripv2_deployment_working.pkt`，不是课程参考工程。三台路由器旧启动配置只在此工作副本中清空；空白工程另存 `pt-work/ripv2_blank_baseline.pkt`。部署包为用户已 CONFIRM 的 `outputs/ripv2_pt_dce_router1_preview/released/*.cfg`，原始 DeepSeek 输出未改写。

三台设备经 Packet Tracer Config 的 Running Config Merge 导入，界面均提示 `Configuration merged successfully.`。导出的实际配置位于 `after-merge/Router0.txt`、`Router1.txt`、`Router2.txt`。其中 Router1 的 `Serial0/0/0` 为 `30.0.0.2/30` 且有 `clock rate 2000000`；三台设备均配置 RIPv2 和 `no auto-summary`。NVRAM Save 的 CLI 三次均显示 `[OK]`。部署工作工程已保存，SHA256 为 `66952B7E0E2FF13BC66A8617EAFA2AA5ABC2479577AEB34945B513ED86171297`。

PT 原始输出保存在 `live-tests/`，整理后的逐命令输入为 `observations.json`，来源标记 `packet_tracer_manual`。PC0→PC1 首次 ping 为 3/4，保留于 `PC0-ping-first.txt`；第二次为 4/4。PC1→PC0 为 4/4。PC0 tracert 路径为 `192.168.16.126 → 30.0.0.2 → 192.168.16.129`。Router0 学到 `R 192.168.16.128/26 via 30.0.0.2`，Router1 学到 `R 192.168.16.0/25 via 30.0.0.1`。

独立课内 oracle `examples/lab4_10_ripv2.yaml` 验收 **3/3**，审计 `runs/20261017T034133Z-verify-b9af16f9/`。适配包自己的六项断言验收 **6/6**，审计 `runs/20261017T034147Z-verify-73670ac1/`。两次均为 PT GUI 人工部署和采集，再由程序分析导入证据；不能称为 PT 自动下发或自动采集。

Router1、Router2 导入后的首次 Config Export 分别产生 0 字节文件，保留为 `after-merge/Router1_first_export_empty.txt`、`Router2_first_export_empty.txt`；再次导出后获得完整配置并用于核对。空文件不计为有效运行配置证据。
