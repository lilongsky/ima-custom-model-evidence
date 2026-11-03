// Executes selected original ima functions with a synthetic credential and a non-network fetch.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'evidence/source-manifest.json')));
const loaded = [];
function fragment(id) {
  const part = manifest.fragments.find(item => item.id === id);
  if (!part) throw new Error(`Unknown fragment: ${id}`);
  const data = fs.readFileSync(path.join(root, part.path));
  if (crypto.createHash('sha256').update(data).digest('hex') !== part.sha256) throw new Error(`Digest mismatch: ${id}`);
  loaded.push(id);
  return data.toString('utf8');
}
const marker = 'IMA_EVIDENCE_DUMMY_KEY_DO_NOT_USE';
const requests = [];
const notices = [];
const silent = { info() {}, error() {}, reportEvent() {} };
class SyntheticError extends Error { constructor(message, code) { super(message); this.code = code; } }
const sandbox = vm.createContext({
  Request, Response, Headers, FormData, Blob, URL, URLSearchParams,
  AbortController, AbortSignal, ReadableStream, TransformStream, TextEncoder, TextDecoder,
  setTimeout, clearTimeout,
  location: { href: 'chrome-extension://khmgfdkajnigikondkcjbaflpjflfiee/index.html', origin: 'chrome-extension://khmgfdkajnigikondkcjbaflpjflfiee', hostname: 'khmgfdkajnigikondkcjbaflpjflfiee' },
  navigator: { userAgent: 'ima' }, chrome: { extension: {} },
  fetch: async request => {
    if (!(request instanceof Request)) throw new Error('Expected original Ky to construct a Request');
    requests.push({ url: request.url, method: request.method, body: JSON.parse(await request.clone().text()) });
    return new Response(JSON.stringify({ code: 1000, msg: 'SYNTHETIC_REPLY_NO_NETWORK' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
  },
  J: null, N: SyntheticError, z: SyntheticError, S: value => value,
  j: { Success: 0, LoginExpired: 1100, TokenRefreshErrorV2: 1101, TokenExpired: 1102, TokenRefreshError: 1103 },
  a: { Request: 16000, ThirtySecond: 30000 },
  P: { RefreshedAccount: 'refreshedAccount', ImaFetchManner: 'imaFetchManner', TokenRefreshRetried: 'tokenRefreshRetried' },
  F: { GiveUpIfTokenExpired: 'giveUp', Silent: 'silent', SilentRetry: 'silentRetry' },
  I: {}, C: { SettingModelAddFail: 'failure', SettingModelAddSuc: 'success' },
  kY: { Add: 'add', Edit: 'edit' }, QF: () => ({ error: value => notices.push(value) }), M: callback => callback,
});
const run = code => vm.runInContext(code, sandbox, { timeout: 2000 });
(async () => {
  const helpers = run(`(()=>{${fragment('runtime_body')};return {interop:l,commonjs:o};})()`);
  sandbox.e = helpers.interop;
  sandbox.t = helpers.commonjs;
  sandbox.p = run(`(()=>{const p=(url,key)=>new URL(url).searchParams.has(key);var ${fragment('host_resolver')};return v;})()`);
  const host = sandbox.p();
  run(`var ${fragment('snake_case_helper')};`);
  run(fragment('json_key_conversion'));
  run(fragment('ky_client') + ';');
  run('var rn=`${p()}/cgi-bin/`,an=`synthetic token expiry notice`;');
  run(`var ${fragment('ky_service')};`);
  run(`var ${fragment('fetch_service')};`);
  run(`var ${fragment('model_http_service')};`);
  run(`var ${fragment('model_presenter')};`);
  const inputHook = run(`(${fragment('input_hook')})`);
  const inputChecks = ['group/deepseek-v4-1-flash', 'deepseek-v4-1-flash', 'a/b/c'].map(input => {
    let output;
    inputHook({ maxLength: 50, onChange: value => { output = value; } })({ target: { value: input } });
    return { input, output, unchanged: input === output };
  });
  const KyService = run('on'), FetchService = run('U'), ModelHttpService = run('$'), Presenter = run('PY');
  const ky = new KyService({}, silent, { getHeader: async () => ({}) }, undefined, [], undefined);
  const transport = new FetchService(ky, silent);
  const http = new ModelHttpService(transport, 'customize_models', silent);
  const state = { mode: 'add', supplierId: 0, apiUri: 'http://127.0.0.1:3425/v1/chat/completions', apiKey: marker, modelName: 'group/deepseek-v4-1-flash', maxInputTokens: 0, maxOutputTokens: 0 };
  const presenter = new Presenter(
    { getState: () => state, setState: patch => Object.assign(state, patch) },
    { useStore: { getState: () => ({ customizeModelConfig: { defaultInputTokens: 32, defaultOutputTokens: 8 } }) } },
    http, silent, { report() {} },
  );
  const result = await presenter.saveModel();
  const checks = {
    requestCountIsOne: requests.length === 1,
    targetIsImaCloud: requests[0]?.url === 'https://ima.qq.com/cgi-bin/customize_models/add_model',
    methodIsPost: requests[0]?.method === 'POST',
    markerPreserved: requests[0]?.body?.model_info?.api_key === marker,
    configuredLocalModelUriIsAJsonField: requests[0]?.body?.model_info?.api_uri === state.apiUri,
    syntheticReplyPropagated: result.errorMessage === 'SYNTHETIC_REPLY_NO_NETWORK',
    slashInputsPreserved: inputChecks.every(check => check.unchanged),
    noInputNotices: notices.length === 0,
  };
  const receipt = {
    evidence_kind: 'controlled local execution; fetch intercepted before network',
    network_used: false, real_credentials_used: false,
    scope: 'Selected original ima client functions. Does not observe Tencent server behavior or a live authenticated request.',
    substitutions: ['Synthetic browser environment with production-default host.', 'Query-presence helper substituted only inside host resolver.', 'Empty account headers; optional application crypto service absent.', 'Error type, reporting, enum, and store dependency stubs.', 'globalThis.fetch captures the original Request and supplies a synthetic error response.'],
    host, requests, result, input_checks: inputChecks, checks,
    source_manifest_sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, 'evidence/source-manifest.json'))).digest('hex'),
    loaded_fragments: loaded, all_passed: Object.values(checks).every(Boolean),
  };
  if (process.argv.includes('--check')) {
    const expected = JSON.parse(fs.readFileSync(path.join(root, 'evidence/observations/offline-reproduction.json')));
    if (JSON.stringify(receipt) !== JSON.stringify(expected)) throw new Error('Reproduction differs from committed receipt');
    console.log(`Reproduced ${Object.keys(checks).length} checks from original source fragments; no network or real credentials.`);
  } else console.log(JSON.stringify(receipt, null, 2));
  if (!receipt.all_passed) process.exitCode = 1;
})().catch(error => { console.error(error); process.exitCode = 1; });
