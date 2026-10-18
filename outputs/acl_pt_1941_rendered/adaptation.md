# 7-1 ACL 的 PT 1941 适配预览

源文件为 `outputs/deepseek_acl/topology.yaml`（真实 DeepSeek 重试生成）。本目录的 `topology.yaml` 是人工适配副本，不能作为模型首次原样输出统计。对照 Packet Tracer 课程 `Lab2/7.1.pkt` 的实际画面，改动仅涉及：Router0/Router1 型号从 2911 改成 1941，Switch0 与 Switch1 的 Fa0/1–3 接线映射改成实际端口。IP、静态路由、ACL 规则顺序、协议、验收断言未改。

2026-10-17 的 `validate` 为 `valid=true, deployable=true` 且无警告；审计目录 `runs/20261017T093352Z-validate-825a6413/`。本目录由 `render` 生成，审计 `runs/20261017T093417Z-render-14daf1db/`。与独立 `examples/lab7_1_acl_pt1941.yaml` 的严格意图比较为 `matched=true`。四份生成的 Router0、Router1、Switch0、Switch1 配置与未适配版 `outputs/deepseek_acl/preview/` 分别逐字节相同；型号与接线改动只影响部署匹配和指导文档。

独立工作副本 `pt-work/acl_deployment_working.pkt` 已由课内参考副本复制，复制时 SHA256 均为 `D07D7EA7F1497F81166AAA1E8C39C311D86B6D3321455858EBA53795971634E8`。课程工程当前 PC0 `ipconfig` 显示 `0.0.0.0`，因此原样参考工程的 ping 失败不能当作 ACL 命中证据。部署时需在工作副本中先配置 PC/Server 静态 IPv4 和两台路由器、两台交换机，再同时核对放行与拒绝；HTTP/FTP 需要业务层实测。此预览尚未批准或下发，原课程工程与三份参考副本均保持原样。
