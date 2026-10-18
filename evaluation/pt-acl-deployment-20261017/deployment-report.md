# 7-1 ACL 适配配置：Packet Tracer 部署与验收

本次使用 `pt-work/acl_deployment_working.pkt`，课程原件 `Lab2/7.1.pkt` 未修改。配置来自用户已在交互终端确认的 `outputs/acl_pt_1941_rendered/released/`。该包把模型方案适配为课程工程实际使用的 Cisco 1941；适配后的成功不能计为 DeepSeek 原始配置一次通过。

课程参考工程本来已有部分相同的接口、静态路由和 ACL，因此不能把打开工程后的原有连通性当成模型部署证据。在工作副本里，Router1 先执行 `no access-list 100`，再逐行重新下发获批的六条 ACL 规则及 G0/1 入站绑定，并保存 NVRAM；Router0 核对接口和静态路由后按获批名称设为 `Router0` 并保存。Switch0、Switch1 的 Fa0/1–Fa0/3 均重新配置为 VLAN 1 access 端口、`no shutdown`，`show interfaces status` 显示这六个端口 connected，两个交换机均 `write memory` 显示 `[OK]`。

PC0、PC1、PC2、Server0 分别设置为 `192.168.0.1/24`、`192.168.0.2/24`、`192.168.1.1/24`、`192.168.1.2/24`；网关分别为所在 LAN 的 `.254`。Server0 的 HTTP 与 FTP 服务均为 On。工作工程经 PT 保存后 SHA256 为 `A0254DE88A5391AACF319C3F452B4A089C8996BF9CF05ADCC8766E798C1E9BF9`。

实际测试：

| 测试 | PT 结果 |
|---|---|
| PC1 → PC2 ping | 0/4，Router1 返回 Destination host unreachable |
| PC0 → Router1 `10.0.0.2` ping | 0/4，返回 Destination host unreachable |
| PC0 → PC2 ping | 首次 2/4，预热后 4/4；首次失败未删除 |
| PC0 → PC2 tracert | `192.168.0.254 → 10.0.0.2 → 192.168.1.1` |
| PC0 / PC1 → Server0 HTTP | PT 浏览器均显示 Request Timeout |
| PC0 → Server0 FTP | 连接超时 |
| PC2 → Server0 | ping 4/4；HTTP 首页正常；FTP 可连接并登录 |
| Router0 / Router1 | 分别有到对方 LAN 的预期静态路由 |

Router1 `show access-lists 100` 在测试后显示：HTTP deny 24 次、PC0 FTP 控制端口 deny 12 次、PC1→PC2 deny 4 次、到 `10.0.0.2` 的 ICMP deny 4 次，以及兜底 permit 17 次。FTP 数据端口 20 规则未见命中，故不能宣称已单独实测该端口。`show ip interface GigabitEthernet0/1` 明确显示 `Inbound access list is 100`。HTTP/FTP 浏览器或服务页面的结论来自现场界面观察；CLI 原始文本保存在 `live-tests/`，首次 ping 的丢包也保留在 PC0 原始记录中。

导入的六条观测见 `outputs/acl_pt_1941_rendered/observations.json`，由 `build_observations.py` 从保留的 PT 控制台文本逐命令提取，来源为 `packet_tracer_manual`。独立课程基准 `examples/lab7_1_acl_pt1941.yaml` 验收 **3/3**，审计 `runs/20261017T110807Z-verify-d7199cba/`；适配包自身断言 **6/6**，审计 `runs/20261017T110830Z-verify-b5973b33/`。这是 PT 人工部署与采集，加程序解析证据，不是 PT 自动下发或自动采集。

参考副本 `pt-work/lab7_1_reference.pkt` 曾被写入而与课程原件哈希不一致。已将该变化版本保留为 `pt-work/lab7_1_reference_modified_20261017.pkt`，然后从未修改的 `Lab2/7.1.pkt` 恢复参考副本；恢复后两者 SHA256 均为 `D07D7EA7F1497F81166AAA1E8C39C311D86B6D3321455858EBA53795971634E8`。此前另存的 `pt-work/lab7_1_reference_unsaved_20261017.pkt` 也独立保留，未用于验收。
