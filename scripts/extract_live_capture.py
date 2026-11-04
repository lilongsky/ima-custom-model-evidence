#!/usr/bin/env python3
"""Extract the two identified test requests from private NetLog; no network access."""
import argparse
import base64
import hashlib
import json
from pathlib import Path
from extract_netlog import extract, TARGET, TELEMETRY

PREFACE = b'PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n'


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read_data_frames(data, socket_id, direction, stream_id):
    names = {v: k for k, v in data['constants']['logEventTypes'].items()}
    chunks, position = [], 0
    for index, event in enumerate(data['events']):
        params = event.get('params', {})
        if (event['source']['id'] == socket_id
                and names[event['type']] == 'SSL_SOCKET_BYTES_' + direction
                and 'bytes' in params):
            decoded = base64.b64decode(params['bytes'], validate=True)
            chunks.append((position, position + len(decoded), index, decoded))
            position += len(decoded)
    joined = b''.join(part[3] for part in chunks)
    position = len(PREFACE) if joined.startswith(PREFACE) else 0
    result = []
    while position + 9 <= len(joined):
        length = int.from_bytes(joined[position:position + 3], 'big')
        end = position + 9 + length
        if end > len(joined):
            break  # A logging boundary may truncate the final, unrelated frame.
        frame = joined[position:end]
        frame_type, flags = frame[3], frame[4]
        frame_stream = int.from_bytes(frame[5:9], 'big') & 0x7fffffff
        if frame_type == 0 and frame_stream == stream_id:
            payload = frame[9:]
            if flags & 8:
                padding = payload[0]
                if padding >= len(payload):
                    raise ValueError('Invalid HTTP/2 DATA padding')
                payload = payload[1:len(payload) - padding]
            segments = [
                {'event_index': index, 'decoded_event_byte_offset': max(position, start) - start,
                 'byte_length': min(end, stop) - max(position, start)}
                for start, stop, index, value in chunks if start < end and stop > position
            ]
            result.append({'frame': frame, 'payload': payload, 'flags': flags,
                           'stream_id': frame_stream, 'input_segments': segments})
        position = end
    if not result or not result[-1]['flags'] & 1:
        raise ValueError('Selected DATA stream has no captured END_STREAM')
    return result


def socket_binding(data, metadata):
    streams = metadata['selection']['http2_streams']
    if len(streams) != 1:
        raise ValueError('Expected exactly one HTTP/2 stream for the selected request')
    stream = streams[0]
    names = {v: k for k, v in data['constants']['logEventTypes'].items()}
    matches = [(i, e) for i, e in enumerate(data['events'])
               if e['source']['id'] == stream['session_source_id']
               and names[e['type']] == 'HTTP2_SESSION_INITIALIZED']
    if len(matches) != 1:
        raise ValueError('Missing unique session-to-socket binding')
    index, event = matches[0]
    return {**stream, 'socket_source_id': event['params']['source_dependency']['id'],
            'session_initialized_event_index': index}


def published_frame(frame):
    return {'stream_id': frame['stream_id'], 'flags': frame['flags'],
            'frame_byte_length': len(frame['frame']), 'frame_sha256': sha(frame['frame']),
            'frame_base64': base64.b64encode(frame['frame']).decode('ascii'),
            'payload_byte_length': len(frame['payload']), 'payload_sha256': sha(frame['payload']),
            'input_segments': frame['input_segments']}


def build(raw, expected, request_source_id, telemetry_request_source_id):
    data = json.loads(raw)
    if data['constants']['logCaptureMode'] != 'Everything':
        raise ValueError('This extraction requires the explicitly authorized raw-byte capture')
    main_meta = extract(raw, TARGET, request_source_id)
    telemetry_meta = extract(raw, TELEMETRY, telemetry_request_source_id)
    main_binding = socket_binding(data, main_meta)
    telemetry_binding = socket_binding(data, telemetry_meta)
    sent = read_data_frames(data, main_binding['socket_source_id'], 'SENT', main_binding['stream_id'])
    received = read_data_frames(data, main_binding['socket_source_id'], 'RECEIVED', main_binding['stream_id'])
    request_bytes = b''.join(f['payload'] for f in sent)
    response_bytes = b''.join(f['payload'] for f in received)
    request, response = json.loads(request_bytes), json.loads(response_bytes)
    inputs = expected['inputs_observed']
    info = request.get('model_info', {})
    if set(request) != {'model_info'} or set(info) != {
            'api_uri', 'api_key', 'model_name', 'max_input_tokens', 'max_output_tokens'}:
        raise ValueError('Unexpected request fields: review privately before publication')
    for field in ('api_uri', 'api_key', 'model_name'):
        if info[field] != inputs[field]:
            raise ValueError('Captured body differs from the declared synthetic UI input')
    if inputs['api_key_kind'] != 'synthetic marker; no permissions':
        raise ValueError('Only this declared synthetic-key experiment is supported')
    if not all(isinstance(info[k], int) for k in ('max_input_tokens', 'max_output_tokens')):
        raise ValueError('Unexpected token values')
    if (set(response) != {'code', 'msg'} or not isinstance(response['code'], int)
            or response['msg'] != expected['ui_message_observed']):
        raise ValueError('Unexpected response: review privately before publication')

    telemetry_frames = read_data_frames(data, telemetry_binding['socket_source_id'],
                                       'SENT', telemetry_binding['stream_id'])
    telemetry_bytes = b''.join(f['payload'] for f in telemetry_frames)
    telemetry = json.loads(telemetry_bytes)
    matches = []
    for item_index, item in enumerate(telemetry.get('d2', [])):
        for message_index, message in enumerate(item.get('message', [])):
            if not isinstance(message, str) or inputs['api_key'] not in message:
                continue
            nested = json.loads(message)
            param = nested.get('param')
            if not isinstance(param, str) or json.loads(param) != request:
                raise ValueError('Telemetry marker is not in the expected request parameter')
            if nested.get('url') != TARGET or nested.get('method') != 'POST':
                raise ValueError('Telemetry entry does not describe this request')
            nested_response = nested.get('data')
            if not isinstance(nested_response, str) or json.loads(nested_response) != response:
                raise ValueError('Telemetry response does not match captured response')
            keep = {key: nested[key] for key in ('url', 'status', 'method', 'ret', 'isErr', 'param', 'data')}
            if keep['status'] != 200 or str(keep['ret']) != str(response['code']) or keep['isErr'] is not True:
                raise ValueError('Unexpected telemetry result metadata')
            matches.append({'json_pointer_to_nested_string': f'/d2/{item_index}/message/{message_index}',
                            'nested_string_utf8_byte_length': len(message.encode()),
                            'nested_string_sha256': sha(message.encode()),
                            'nested_json_excerpt': keep,
                            'omitted_nested_field_names': sorted(set(nested) - set(keep)),
                            'param_json_equals_captured_add_model_request': True,
                            'param_utf8_sha256': sha(param.encode()),
                            'param_bytes_equal_captured_request': param.encode() == request_bytes})
    if len(matches) != 1:
        raise ValueError('Expected one telemetry log containing the synthetic test parameter')

    proof = {
        'schema_version': 1, 'evidence_type': 'real_native_netlog_decoded_http2_data_frames',
        'input': main_meta['input'], 'endpoint': TARGET,
        'url_request_source_id': request_source_id, 'binding': main_binding,
        'request': {'body_path': 'evidence/network/live-add-model-request.json',
                    'byte_length': len(request_bytes), 'sha256': sha(request_bytes),
                    'frames': [published_frame(f) for f in sent]},
        'response': {'body_path': 'evidence/network/live-add-model-response.json',
                     'byte_length': len(response_bytes), 'sha256': sha(response_bytes),
                     'frames': [published_frame(f) for f in received]},
        'decoding': ['Decode base64 in selected SSL_SOCKET_BYTES events.',
                     'Concatenate by direction on the explicitly bound socket.',
                     'Skip the HTTP/2 client preface when present; parse 9-byte frame headers.',
                     'Select DATA (type 0) for the bound stream; remove padding if present.',
                     'Concatenate payloads through END_STREAM; decode UTF-8 JSON.'],
        'publication': 'Only validated synthetic request and code/msg response DATA frames are published. No HPACK header blocks, credentials or other streams.',
        'limits': ['These are TLS application bytes observed inside the client, not plaintext on the physical network.',
                   'The private original log is required to verify event provenance; published frames independently reproduce the published bodies.',
                   'No conclusion about server storage or server-to-provider traffic.'],
    }
    telemetry_excerpt = {
        'schema_version': 1, 'evidence_type': 'real_outgoing_telemetry_body_json_excerpt',
        'input_sha256': sha(raw), 'endpoint': TELEMETRY,
        'url_request_source_id': telemetry_request_source_id, 'binding': telemetry_binding,
        'body_byte_length': len(telemetry_bytes), 'body_sha256': sha(telemetry_bytes),
        'data_frames': [{'input_segments': f['input_segments'], 'frame_byte_length': len(f['frame']),
                         'frame_sha256': sha(f['frame']), 'payload_byte_length': len(f['payload'])}
                        for f in telemetry_frames],
        'selected_log': matches[0],
        'redaction': ['Full telemetry body and DATA frame bytes are not published.',
                      'Other log entries, account/device identifiers, headers, timestamps and trace/span values are omitted.',
                      'Published param and data strings are unchanged and verified against the benign test request/response.'],
        'limits': ['This records one observed failed-save flow with a synthetic key.',
                   'No claim that every key or every version is logged, or that a real-key breach occurred.'],
    }
    encode = lambda obj: (json.dumps(obj, ensure_ascii=False, indent=2) + '\n').encode()
    return {
        'evidence/network/live-add-model-request.json': request_bytes,
        'evidence/network/live-add-model-response.json': response_bytes,
        'evidence/observations/live-wire-proof.json': encode(proof),
        'evidence/observations/telemetry-log-excerpt.json': encode(telemetry_excerpt),
        'evidence/observations/native-netlog-raw-mode-metadata.json': encode(main_meta),
        'evidence/observations/telemetry-netlog-metadata.json': encode(telemetry_meta),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_netlog', type=Path)
    parser.add_argument('--request-source-id', required=True, type=int)
    parser.add_argument('--telemetry-request-source-id', required=True, type=int)
    parser.add_argument('--expected-inputs', type=Path,
                        default=Path(__file__).resolve().parents[1] / 'evidence/observations/native-save-ui-observation.json')
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--output-dir', type=Path)
    group.add_argument('--check-dir', type=Path)
    args = parser.parse_args()
    files = build(args.raw_netlog.read_bytes(), json.loads(args.expected_inputs.read_text()),
                  args.request_source_id, args.telemetry_request_source_id)
    for relative, value in files.items():
        root = args.check_dir or args.output_dir
        target = root / relative
        if args.check_dir:
            if not target.exists() or target.read_bytes() != value:
                raise SystemExit(f'Live extraction differs: {relative}')
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
    print(f"{'Verified' if args.check_dir else 'Exported'} {len(files)} filtered live-capture artifacts; no network.")


if __name__ == '__main__':
    main()
