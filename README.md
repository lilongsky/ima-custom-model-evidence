# Tencent ima 自定义模型 API Key 提交流程：可复核证据

本仓库记录 2026-11-03 对 macOS 版 ima 本地客户端的检查。**所见客户端的保存流程会把用户填写的 `apiKey`、`apiUri` 和 `modelName` 一起提交给 ima 的自定义模型服务。** 原始函数在隔离运行中构造的生产默认目标是：

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

上面的 Key 是公开测试标记。**这份结果来自原始客户端函数的断网复现，在 `fetch` 处截获；不是一次真实、已认证的线上请求抓包。** 当前没有证明密钥泄露、被滥用、长期明文存储或服务端权限隔离失效的证据。

## 结论与证据等级

| 编号 | 结论 | 证据与边界 |
| --- | --- | --- |
| C1 | 客户端将 Key 放入 ima 自定义模型服务的保存请求；生产默认目标为上述 URL | 当前安装脚本原文 + 原函数断网执行；尚无真实保存请求抓包 |
| C2 | 所见前端没有过滤模型名中的 `/`，原样进入保存逻辑 | 输入函数和表单逻辑原文；带 `/`、不带 `/`、多级 `/` 的本地复现 |
| C3 | 本机 Magpie 接受 `group/deepseek-v4-1-flash` | 一次真实本机调用返回 HTTP 200 和 `OK`；不能单独证明 ima 云端接受该名称 |
| C4 | 云端校验无法使用用户电脑的 localhost 是当前失败的一种合理解释 | 客户端架构 + 用户报错截图；未观测服务端具体失败分支，不能认定唯一根因 |
| C5 | 所见聊天代码把问题和模型 ID 发往 ima assistant 服务；官方也说明 AI 内容上云 | 客户端片段 + 官方隐私指引；未观测 ima 服务器向模型供应商发出的流量 |
| C6 | 真实客户端网络捕获 | [状态与方法](docs/network-capture.md)：尚未取得；已尝试打开内置网络日志，后续受 Mac 锁屏阻止 |

完整映射见 [claims.json](evidence/claims.json)。

## 一条命令复核

需要 Node.js 20 或更高版本，无 npm 依赖，无须执行 `npm install`：

```sh
npm test
```

它会检查公开文件及片段的 SHA-256，并用仓库中的原始片段重新构造 Request，与已提交的[复现回执](evidence/observations/offline-reproduction.json)逐项比较。复现不联网、不读取账号、不使用真实 Key、不保存应用配置。

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

该实现意味着用户把所填 Key 交给 ima 服务端处理，增加了需要信任的主体。服务器如何加密保存、保留多久、如何限制访问和删除，目前未核实。请求对象中的字符串不能证明线上未使用 TLS，也不能证明服务器明文落盘。

如果填写的是本机网关占位 token，交出的就是该 token；本仓库没有读取或公开 Magpie 保存的模型供应商密钥。即使前端显示保存失败，也不能据此推定配置从未进入请求。

官方 [ima.copilot（PC端）隐私保护指引](https://privacy.qq.com/document/preview/aca5ed13893d47cfa31697704c2dd366) 第 1.2（1）项说明 AI 服务相关内容会上传云端。该条不能单独证明 API Key 的存储方式。
