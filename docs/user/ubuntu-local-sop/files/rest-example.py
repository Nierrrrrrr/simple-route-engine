#!/usr/bin/env python3
"""Loopback-only, nonsecret demo of Route Engine's operation protocol.

One JSON file per operation preserves a completed result across process restart.
This ledger belongs to the example external API, not to the engine state store.
"""
import argparse
import json
import os
import pathlib
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOCK = threading.Lock()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9081)
    parser.add_argument('--state-dir', required=True)
    args = parser.parse_args()
    root = pathlib.Path(args.state_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, status, body):
            data = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == '/health':
                return self.reply(200, {'status': 'UP'})
            match = re.fullmatch(r'/operations/([a-f0-9-]{36})', self.path)
            if not match:
                return self.reply(404, {'error': 'not_found'})
            with LOCK:
                path = root / (match[1] + '.json')
                if not path.exists():
                    return self.reply(404, {'error': 'unknown_operation'})
                saved = json.loads(path.read_text())
            self.reply(200, saved['result'])

        def do_POST(self):
            if self.path != '/operations':
                return self.reply(404, {'error': 'not_found'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 65536:
                    raise ValueError('length')
                request = json.loads(self.rfile.read(length))
                op = request['operationId']
                if not isinstance(op, str) or not re.fullmatch(r'[a-f0-9-]{36}', op):
                    raise ValueError('identity')
                if self.headers.get('Idempotency-Key') != op:
                    raise ValueError('key')
                data = request['input']
                if not isinstance(data, dict):
                    raise ValueError('input')
                allowed = data.get('allowed', True)
                if type(allowed) is not bool:
                    raise ValueError('allowed')
                message = data.get('message', 'REST example complete')
                if not isinstance(message, str) or len(message) > 200:
                    raise ValueError('message')
                with LOCK:
                    path = root / (op + '.json')
                    if path.exists():
                        saved = json.loads(path.read_text())
                        if saved['request'] != request:
                            return self.reply(409, {'operationId': op, 'error': 'identity_conflict'})
                        return self.reply(200, saved['result'])
                    result = {'operationId': op, 'status': 'SUCCEEDED',
                              'output': {'allowed': allowed, 'message': message}}
                    temporary = path.with_suffix('.tmp')
                    with temporary.open('w', encoding='utf-8') as stream:
                        json.dump({'request': request, 'result': result}, stream, ensure_ascii=False)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                self.reply(200, result)
            except (KeyError, ValueError, TypeError, json.JSONDecodeError):
                self.reply(400, {'error': 'invalid_request'})

        def log_message(self, *args):
            pass  # Do not print request bodies, headers or credentials.

    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'REST example listening on 127.0.0.1:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
