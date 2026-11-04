# Tencent ima 自定义模型 API Key 提交流程：可复核证据

本仓库记录 2026-11-03 至 2026-11-04 对 macOS 版 ima 本地客户端的检查。**所见客户端的保存流程会把用户填写的 `apiKey`、`apiUri` 和 `modelName` 一起提交给 ima 的自定义模型服务。** 原始函数的断网复现构造了以下目标；随后真实客户端的网络事件也确认向该地址发送 POST：

```http
POST https://ima.qq.com/cgi-bin/customize_models/add_model
```

```json
{
  "model_info": {
    "api_uri": "http://127.0.0.1:3425/v1/chat/completions",
    "api_key": "IMA_EVIDENCE_DUMMY_KEY_DO_NOT_USE",
    "model_name": "group/deepseek-v4-1-flash",
    "max_input_tokens": 32,
    "max_output_tokens": 8
  }
}
```

上面的 Key 是公开测试标记。**上面的 JSON 是最初的断网复现，不能当作抓包原文。** 随后的真实客户端采集取得了独立的[线上请求体](evidence/network/live-add-model-request.json)和[响应体](evidence/network/live-add-model-response.json)：请求中的假 Key 与 UI 输入相同，模型名原样保留 `/`，默认 token 参数实际提交为 `172 / 32`。本次没有使用真实供应商 Key，也没有审计服务端存储及访问控制。

2026-11-04 的[原始字节解码证据](evidence/observations/live-wire-proof.json)确认：该 POST 的 HTTP/2 DATA 为 **207 字节**，HTTP 状态 **200**，响应 DATA 为 **61 字节**，内容为：

```json
{"code":100001,"msg":"校验失败，请检查模型配置"}
```

**另一个实际观察：同一次失败请求的完整 `param` 还出现在发往 `https://galileotelemetry.tencent.com/collect` 的日志中，假 Key 没有被遮蔽。** 该 `param` 与上面的真实请求体逐字节一致。[遥测日志脱敏摘录](evidence/observations/telemetry-log-excerpt.json) · [采集、解码及省略说明](docs/network-capture.md)

## 结论与证据等级

| 编号 | 结论 | 证据与边界 |
| --- | --- | --- |
| C1 | 客户端将 Key 放入 ima 自定义模型服务的保存请求 | 安装脚本原文 + 原函数断网执行 + 真实 TLS 应用字节中的 JSON |
| C2 | 所见前端没有过滤模型名中的 `/`，原样发出 | 输入函数和表单逻辑原文 + 本地输入复现 + 真实请求体中的完整模型名 |
| C3 | 本机 Magpie 接受 `group/deepseek-v4-1-flash` | 一次真实本机调用返回 HTTP 200 和 `OK`；不能单独证明 ima 云端接受该名称 |
| C4 | 云端校验无法使用用户电脑的 localhost 是当前失败的一种合理解释 | 客户端架构 + 用户报错截图；未观测服务端具体失败分支，不能认定唯一根因 |
| C5 | 所见聊天代码把问题和模型 ID 发往 ima assistant 服务；官方也说明 AI 内容上云 | 客户端片段 + 官方隐私指引；未观测 ima 服务器向模型供应商发出的流量 |
| C6 | 真实客户端保存请求和响应已取得 | NetLog 元数据 + SSL 应用字节 + HTTP/2 DATA 帧 + JSON；不是网卡 PCAP |
| C7 | 本次失败请求的原始参数进入额外的日志/遥测接口 | 相同假 Key 及完整 `param` 出现在 `galileotelemetry.tencent.com/collect` 的实际请求体中；其他日志和身份字段已省略 |

完整映射见 [claims.json](evidence/claims.json)。

## 一条命令复核

需要 Node.js 20 或更高版本，无 npm 依赖，无须执行 `npm install`：

```sh
npm test
```

它会检查公开文件及片段的 SHA-256，从公开 DATA 帧重建线上请求/响应并核对遥测 `param`，再用原始片段重新构造离线 Request，与[离线回执](evidence/observations/offline-reproduction.json)比较。验证不联网、不读取账号、不使用真实 Key、不保存应用配置。

要看完整构造结果：

```sh
node scripts/reproduce.cjs
```

## 从自己的同版 ima 重建证据

安装相同版本的扩展后运行：

```sh
python3 scripts/extract_sources.py \
  --profile "$HOME/Library/Application Support/com.tencent.imamac"
```

脚本先核对完整原文件的哈希，然后按精确选择器提取片段，检查 Unicode 码点、UTF-16、UTF-8 字节偏移及片段哈希。输出写入 `_local/rebuilt/`。版本或字节不匹配会失败，不会替换公开基线。也可用 `--source-dir` 指向按 manifest 相对路径排列的离线文件目录。

无原始安装文件时，可以验证公开片段的一致性和执行结果；不能仅靠这些公开片段独立证明它们的安装来源。

## 源码入口

| 环节 | 原始片段 |
| --- | --- |
| 从表单读取 `apiKey`，构造 `modelInfo` 并保存 | [model_presenter](evidence/snippets/model_presenter.jsfrag) |
| `addModel()` 发起 POST 并传入 JSON | [model_http_service](evidence/snippets/model_http_service.jsfrag) |
| `apiKey` → `api_key`，字符串值不变 | [json_key_conversion](evidence/snippets/json_key_conversion.jsfrag) |
| `customize_models` 路径绑定 | [service_path_injection](evidence/snippets/service_path_injection.jsfrag) |
| 生产 host 与 HTTP 前缀 | [host_resolver](evidence/snippets/host_resolver.jsfrag)、[host_injection](evidence/snippets/host_injection.jsfrag) |
| 原始 HTTP 客户端和账户头处理 | [ky_service](evidence/snippets/ky_service.jsfrag)、[fetch_service](evidence/snippets/fetch_service.jsfrag)、[ky_client](evidence/snippets/ky_client.jsfrag) |
| 模型名称输入函数 | [input_hook](evidence/snippets/input_hook.jsfrag) |

所有片段的完整父文件 SHA-256、长度、原始偏移与选择器见 [source-manifest.json](evidence/source-manifest.json)。片段没有改名、重排或格式化；执行脚本的包装和依赖替身单独公开。

## 来源与完整性

所见扩展版本：设置 `5.11.1`、问问 ima `5.19.0`、copilot `4.8.5`。主程序的 macOS 签名在沙箱外只读核验通过，显示 Tencent Technology (Shenzhen) Company Limited，Team ID `88L2Q4487U`。[签名回执](evidence/observations/host-app-signature.json)

主程序签名检查**不覆盖用户 profile 内独立下载的扩展脚本**。这些脚本来自本机版本目录，并以完整文件哈希固定；未独立验证其发布者分离签名。哈希证明字节身份与后续完整性，不等同于发布者公证或所有版本的行为证明。

进一步阅读：[完整证据链](docs/evidence-chain.md) · [方法、替身与局限](docs/methodology.md) · [公开与省略范围](docs/publication-scope.md) · [原始 Magpie 调用回执](evidence/observations/magpie-direct-probe.json)

## 对安全含义的准确表述

本次观察确认所填字段交给 ima 服务处理，而且失败请求参数进入另一条日志处理链路。这使日志脱敏、日志访问权限和保留策略也成为 Key 安全边界的一部分。是否保存、如何加密、谁能访问及何时删除，目前未核实。采集的是 HTTPS/TLS 内部应用字节，**不能称为公网明文传输，也不能据此断言服务器明文落盘或发生真实密钥泄露**。

如果填写的是本机网关占位 token，交出的就是该 token；本仓库没有读取或公开 Magpie 保存的模型供应商密钥。即使前端显示保存失败，也不能据此推定配置从未进入请求。

官方 [ima.copilot（PC端）隐私保护指引](https://privacy.qq.com/document/preview/aca5ed13893d47cfa31697704c2dd366) 第 1.2（1）项说明 AI 服务相关内容会上传云端。该条不能单独证明 API Key 的存储方式。
