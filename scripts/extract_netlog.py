#!/usr/bin/env python3
"""Export only allowlisted add_model metadata; never export bodies or account headers."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

TARGET = 'https://ima.qq.com/cgi-bin/customize_models/add_model'
TELEMETRY = 'https://galileotelemetry.tencent.com/collect'
INITIATOR = 'chrome-extension://khmgfdkajnigikondkcjbaflpjflfiee'


def extract(raw, target=TARGET, request_source_id=None):
    if target not in (TARGET, TELEMETRY):
        raise ValueError('Only the two investigated endpoints are supported')
    target_path = ':path: ' + urlsplit(target).path
    data = json.loads(raw)
    constants, events = data['constants'], data['events']
    names = {v: k for k, v in constants['logEventTypes'].items()}
    sources = {v: k for k, v in constants['logSourceType'].items()}
    phases = {v: k for k, v in constants['logEventPhase'].items()}
    offset = int(constants['timeTickOffset'])

    def kind(event):
        return names[event['type']]

    def utc(ticks):
        return datetime.fromtimestamp((offset + int(ticks)) / 1000, timezone.utc).isoformat(timespec='milliseconds')

    requests = {e['source']['id'] for e in events
                if kind(e) == 'URL_REQUEST_START_JOB'
                and e.get('params', {}).get('url') == target
                and e['params'].get('method') == 'POST'}
    if request_source_id is not None:
        requests &= {request_source_id}
    if not requests:
        raise ValueError('No real POST event for the selected endpoint in this log')
    jobs = {e['params']['source_dependency']['id'] for e in events
            if e['source']['id'] in requests
            and kind(e) == 'HTTP_STREAM_REQUEST_BOUND_TO_JOB'}
    streams = {(e['source']['id'], e['params']['stream_id']) for e in events
               if kind(e) == 'HTTP2_SESSION_SEND_HEADERS'
               and target_path in e.get('params', {}).get('headers', [])
               and e['params'].get('source_dependency', {}).get('id') in jobs}

    header_patterns = [
        r':method: POST', re.escape(':authority: ' + urlsplit(target).netloc), r':scheme: https',
        re.escape(target_path), r'HTTP/\d(?:\.\d)? \d{3}(?: [A-Za-z ]+)?',
        r':status: \d{3}', r'content-length: \d+',
        r'content-type: application/json(?:;\s*charset=utf-8)?',
        r'date: [A-Za-z]{3}, \d{2} [A-Za-z]{3} \d{4} \d{2}:\d{2}:\d{2} GMT',
    ]
    safe_headers = re.compile('(?:' + '|'.join(header_patterns) + ')', re.IGNORECASE)
    primary_kinds = {
        'CORS_REQUEST', 'REQUEST_ALIVE', 'URL_REQUEST_START_JOB',
        'HTTP_STREAM_REQUEST_BOUND_TO_JOB', 'UPLOAD_DATA_STREAM_INIT',
        'HTTP_TRANSACTION_SEND_REQUEST', 'HTTP_TRANSACTION_HTTP2_SEND_REQUEST_HEADERS',
        'HTTP_TRANSACTION_SEND_REQUEST_HEADERS', 'HTTP_TRANSACTION_READ_RESPONSE_HEADERS',
        'URL_REQUEST_JOB_FILTERED_BYTES_READ',
    }
    h2_kinds = {'HTTP2_SESSION_SEND_HEADERS', 'HTTP2_SESSION_RECV_HEADERS',
                'HTTP2_SESSION_SEND_DATA', 'HTTP2_SESSION_RECV_DATA'}
    numeric_fields = {'byte_count', 'total_size', 'net_error', 'stream_id', 'size',
                      'is_chunked', 'fin', 'end_stream'}
    result = []
    for index, event in enumerate(events):
        source_id = event['source']['id']
        event_kind = kind(event)
        params = event.get('params', {})
        selected = (source_id in requests and event_kind in primary_kinds
                    or source_id in jobs and event_kind == 'HTTP2_SESSION_POOL_IMPORTED_SESSION_FROM_SOCKET'
                    or (source_id, params.get('stream_id')) in streams and event_kind in h2_kinds)
        if not selected:
            continue
        public = {}
        for key, value in params.items():
            if key in numeric_fields and isinstance(value, (int, bool)):
                public[key] = value
            elif key == 'url' and value == target:
                public[key] = value
            elif key == 'method' and value == 'POST':
                public[key] = value
            elif key == 'initiator' and value == INITIATOR:
                public[key] = value
            elif key == 'source_dependency':
                public[key] = {'id': value['id'], 'type': sources[value['type']]}
            elif key == 'headers':
                public[key] = [line for line in value if safe_headers.fullmatch(line)]
        item = {
            'event_index': index, 'type': event_kind,
            'phase': phases[event['phase']], 'time_ticks_ms': event['time'],
            'derived_time_utc': utc(event['time']),
            'source': {'id': source_id, 'type': sources[event['source']['type']],
                       'start_time_ticks_ms': event['source']['start_time']},
            'params': public,
            'omitted_param_names': sorted(set(params) - set(public)),
        }
        if 'headers' in params:
            item['omitted_header_count'] = len(params['headers']) - len(public['headers'])
        result.append(item)

    return {
        'schema_version': 1,
        'evidence_type': 'real_native_client_netlog_allowlisted_metadata',
        'input': {'sha256': hashlib.sha256(raw).hexdigest(), 'byte_length': len(raw),
                  'event_count': len(events), 'log_format_version': constants['logFormatVersion'],
                  'capture_mode': constants['logCaptureMode'], 'time_tick_offset_ms': offset,
                  'first_event_time_utc': utc(events[0]['time']),
                  'last_event_time_utc': utc(events[-1]['time']),
                  'client_name': constants['clientInfo']['name'],
                  'client_version': constants['clientInfo']['version']},
        'selection': {'exact_url': target, 'method': 'POST',
                      'url_request_source_ids': sorted(requests),
                      'bound_job_source_ids': sorted(jobs),
                      'http2_streams': [{'session_source_id': a, 'stream_id': b}
                                        for a, b in sorted(streams)]},
        'redaction': {'method': 'allowlist; event_index is zero-based in original events array',
                      'headers_kept': 'method, authority, scheme, target path, HTTP status, JSON content type, byte length, date',
                      'request_body_published': False, 'response_body_published': False,
                      'raw_log_published': False,
                      'other_omissions': ['all non-target requests', 'account and authorization headers',
                                          'cookies and tickets', 'proxy and local network details',
                                          'client command line', 'all socket bytes and payload bodies']},
        'limits': ['This is a filtered event log, not an Ethernet/IP packet capture.',
                   'The original private log is required to independently verify this extraction.',
                   'Hashes commit to bytes; they do not authenticate collection time or publisher.',
                   'HTTP 200 alone does not mean application validation succeeded.',
                   'No API key value or response JSON is recovered by this metadata extractor.'],
        'events': result,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw_netlog', type=Path)
    parser.add_argument('--target', choices=(TARGET, TELEMETRY), default=TARGET)
    parser.add_argument('--request-source-id', type=int, help='Limit to one verified URL_REQUEST source')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--output', type=Path)
    group.add_argument('--check', type=Path, help='Compare against a previously exported receipt')
    args = parser.parse_args()
    receipt = extract(args.raw_netlog.read_bytes(), args.target, args.request_source_id)
    if args.check:
        if receipt != json.loads(args.check.read_text()):
            raise SystemExit('NetLog extraction differs from the committed receipt')
        print(f"Verified {len(receipt['events'])} allowlisted events against the private original log.")
    elif args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + '\n')
    else:
        print(json.dumps(receipt, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
