const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file));
const json = file => JSON.parse(read(file));
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
const proof = json('evidence/observations/live-wire-proof.json');
for (const direction of ['request', 'response']) {
  const receipt = proof[direction];
  const parts = [];
  for (const item of receipt.frames) {
    const frame = Buffer.from(item.frame_base64, 'base64');
    assert.equal(frame.length, item.frame_byte_length);
    assert.equal(sha(frame), item.frame_sha256);
    assert.equal(frame.readUIntBE(0, 3), frame.length - 9);
    assert.equal(frame[3], 0, 'Only DATA frames may be published');
    assert.equal(frame.readUInt32BE(5) & 0x7fffffff, proof.binding.stream_id);
    assert.equal(frame[4], item.flags);
    let payload = frame.subarray(9);
    if (frame[4] & 8) payload = payload.subarray(1, payload.length - payload[0]);
    assert.equal(payload.length, item.payload_byte_length);
    assert.equal(sha(payload), item.payload_sha256);
    assert.equal(item.input_segments.reduce((sum, segment) => sum + segment.byte_length, 0), frame.length);
    parts.push(payload);
  }
  assert.ok(receipt.frames.at(-1).flags & 1, 'Missing END_STREAM');
  const bytes = Buffer.concat(parts);
  assert.deepEqual(bytes, read(receipt.body_path));
  assert.equal(bytes.length, receipt.byte_length);
  assert.equal(sha(bytes), receipt.sha256);
}
const request = json(proof.request.body_path);
const response = json(proof.response.body_path);
const ui = json('evidence/observations/native-save-ui-observation.json');
for (const field of ['api_uri', 'api_key', 'model_name']) assert.equal(request.model_info[field], ui.inputs_observed[field]);
assert.equal(response.msg, ui.ui_message_observed);
const metadata = json('evidence/observations/native-netlog-raw-mode-metadata.json');
assert.equal(metadata.input.sha256, proof.input.sha256);
assert.deepEqual(metadata.selection.url_request_source_ids, [proof.url_request_source_id]);
assert.deepEqual(metadata.selection.http2_streams, [{session_source_id: proof.binding.session_source_id, stream_id: proof.binding.stream_id}]);
for (const [eventType, expectedBytes] of [['HTTP2_SESSION_SEND_DATA', proof.request.byte_length], ['HTTP2_SESSION_RECV_DATA', proof.response.byte_length]]) {
  assert.equal(metadata.events.filter(event => event.type === eventType).reduce((sum, event) => sum + event.params.size, 0), expectedBytes);
}
const telemetry = json('evidence/observations/telemetry-log-excerpt.json');
const log = telemetry.selected_log.nested_json_excerpt;
assert.deepEqual(JSON.parse(log.param), request);
assert.deepEqual(JSON.parse(log.data), response);
assert.equal(sha(Buffer.from(log.param)), telemetry.selected_log.param_utf8_sha256);
assert.equal(telemetry.selected_log.param_utf8_sha256, proof.request.sha256);
assert.equal(telemetry.input_sha256, proof.input.sha256);
const telemetryMetadata = json('evidence/observations/telemetry-netlog-metadata.json');
assert.deepEqual(telemetryMetadata.selection.url_request_source_ids, [telemetry.url_request_source_id]);
assert.equal(telemetryMetadata.selection.exact_url, telemetry.endpoint);
assert.equal(telemetryMetadata.events.filter(event => event.type === 'HTTP2_SESSION_SEND_DATA').reduce((sum, event) => sum + event.params.size, 0), telemetry.body_byte_length);
console.log('Verified captured DATA frames, exact request/response bytes, UI inputs, and matching telemetry param.');
