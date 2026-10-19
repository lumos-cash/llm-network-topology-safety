# LLM 网络拓扑生成与安全部署

课程项目：使用 DeepSeek 将自然语言网络需求转成 YAML 拓扑描述，经结构、编址和协议检查后生成 Cisco 配置；配置发布须经人工确认，再在 Packet Tracer 工作副本中部署和验收。

当前实现了需求生成、静态检查、配置预览、安全确认和测试输出解析。Packet Tracer 设备配置及结果采集仍由人工完成，尚未实现可靠的自动下发、自动采集或自动故障修复。适配后通过测试不等于模型原始配置一次通过。

## 复现

在 Windows PowerShell 中安装 `requirements.txt` 的依赖，然后运行：

```powershell
python netlab.py doctor
python netlab.py validate examples/lab4_11_ospf.yaml
python netlab.py render examples/lab4_11_ospf.yaml --out outputs/my-ospf
```

调用 DeepSeek 需在本机按 `.env.example` 配置 `.env.local`，不要提交密钥。发布配置前应审阅预览并在交互终端输入确认口令。生成的命令不能自动连接 Packet Tracer；具体操作和验收方式见代码及报告。

## 已记录的结果

本地实验对 11 项需求实际调用过 DeepSeek。程序测试 70 项通过，8 组故意构造的错误输入被拦截。OSPF 工作副本通过 5 项独立验收；经人工适配的 RIPv2 与 ACL 工作副本分别通过 3 项独立验收。一次人为关闭端口的故障由人工修复。

仓库保留代表性的模型拓扑、生成配置、评估摘要、三份实测 `.pkt` 工作工程及[最新六页报告](output/pdf/LLM网络作业报告_署名留空_20261019.pdf)。原始模型调用审计、完整设备控制台记录、本地密钥、课程课件和未修改的课程参考工程不在公开仓库内。报告姓名、学号栏按作者要求留空。

公开可见不代表系统已实现全自动部署。详细能力边界和失败案例见报告。
