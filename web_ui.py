"""Browser frontend proxy for the existing length-prefixed TCP examination server."""
import os
import secrets
import socket
import threading
import time
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory
from protocol import send_msg, recv_msg

app = Flask(__name__)
ROOT = Path(__file__).resolve().parent
TCP_HOST = os.getenv('EXAM_SERVER_IP', '127.0.0.1')
TCP_PORT = int(os.getenv('EXAM_SERVER_PORT', '9999'))
WEB_PORT = int(os.getenv('EXAM_WEB_PORT', '8080'))
sessions = {}
sessions_lock = threading.Lock()


def response(payload, code=200):
    return jsonify(payload), code


def exchange(session, payload):
    with session['lock']:
        send_msg(session['sock'], payload)
        result = recv_msg(session['sock'])
        if not result:
            raise ConnectionError('TCP exam server disconnected')
        return result


def get_session():
    token = (request.get_json(silent=True) or {}).get('token', '')
    with sessions_lock:
        session = sessions.get(token)
    return session


@app.get('/')
def home():
    return send_from_directory(ROOT, 'exam_ui.html')


@app.post('/api/start')
def start():
    data = request.get_json(silent=True) or {}
    student_id = str(data.get('student_id', '')).strip()
    if not 1 <= len(student_id) <= 48:
        return response({'error': 'Enter a valid student ID'}, 400)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(8)
    try:
        sock.connect((TCP_HOST, TCP_PORT))
        send_msg(sock, {'action': 'REGISTER', 'student_id': student_id})
        registration = recv_msg(sock)
        if not registration or registration.get('status') != 'OK':
            sock.close()
            return response({'error': (registration or {}).get('message', 'Registration failed')}, 400)
        sock.settimeout(5)
        token = secrets.token_urlsafe(32)
        session = {'sock': sock, 'lock': threading.Lock(), 'index': 0,
                   'total': int(registration['total_questions']),
                   'deadline': time.monotonic() + float(registration['duration'])}
        with sessions_lock:
            sessions[token] = session
        return response({'token': token, 'student_id': student_id,
                         'duration': registration['duration'],
                         'total_questions': registration['total_questions']})
    except (OSError, ValueError, KeyError) as exc:
        sock.close()
        return response({'error': f'TCP server unavailable: {exc}'}, 502)


@app.post('/api/question')
def question():
    session = get_session()
    if not session:
        return response({'error': 'Session expired. Please register again.'}, 401)
    data = request.get_json(silent=True) or {}
    idx = data.get('index')
    if type(idx) is not int or idx < 0 or idx >= session['total']:
        return response({'error': 'Invalid question index'}, 400)
    try:
        result = exchange(session, {'action': 'GET_QUESTION', 'q_idx': idx})
        if result.get('status') != 'OK':
            return response({'error': 'Question unavailable or time expired', 'status': result.get('status')}, 409)
        return response(result)
    except (OSError, ValueError) as exc:
        return response({'error': str(exc)}, 502)


@app.post('/api/answer')
def answer():
    session = get_session()
    if not session:
        return response({'error': 'Session expired'}, 401)
    data = request.get_json(silent=True) or {}
    if type(data.get('q_id')) is not int or data.get('answer') not in ('A', 'B', 'C', 'D'):
        return response({'error': 'Invalid answer'}, 400)
    try:
        result = exchange(session, {'action': 'SUBMIT_ANSWER', 'q_id': data['q_id'], 'answer': data['answer']})
        return response(result, 200 if result.get('status') == 'ACCEPTED' else 409)
    except (OSError, ValueError) as exc:
        return response({'error': str(exc)}, 502)


@app.post('/api/finish')
def finish():
    data = request.get_json(silent=True) or {}
    token = data.get('token', '')
    with sessions_lock:
        session = sessions.pop(token, None)
    if not session:
        return response({'error': 'Session already ended'}, 401)
    try:
        result = exchange(session, {'action': 'FINISH'})
        return response(result, 200 if result.get('status') == 'RESULT' else 409)
    except (OSError, ValueError) as exc:
        return response({'error': str(exc)}, 502)
    finally:
        session['sock'].close()


if __name__ == '__main__':
    print(f'Exam UI: http://127.0.0.1:{WEB_PORT} | TCP backend: {TCP_HOST}:{TCP_PORT}')
    app.run(host='0.0.0.0', port=WEB_PORT, threaded=True, debug=False)
