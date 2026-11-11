"""Concurrent TCP examination server (JSON length-prefixed messages)."""
import json
import logging
import os
import socket
import threading
import time
from pathlib import Path
from protocol import send_msg, recv_msg

ROOT = Path(__file__).resolve().parent
QUESTIONS = json.loads((ROOT / 'questions.json').read_text())
HOST = os.environ.get('EXAM_BIND', '0.0.0.0')
PORT = int(os.environ.get('EXAM_PORT', 9999))
DURATION = int(os.environ.get('EXAM_DURATION', 120))
records = {}
lock = threading.Lock()
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')


def serve_client(conn, addr):
    sid = None
    responses = {}
    deadline = None
    completed = False
    try:
        with conn:
            conn.settimeout(10)
            reg = recv_msg(conn)
            if not isinstance(reg, dict) or reg.get('action') != 'REGISTER':
                send_msg(conn, {'status': 'ERROR', 'message': 'REGISTER required'})
                return
            sid = reg.get('student_id')
            if not isinstance(sid, str) or not 1 <= len(sid.strip()) <= 48:
                send_msg(conn, {'status': 'ERROR', 'message': 'Invalid student ID'})
                return
            sid = sid.strip()
            with lock:
                if sid in records and records[sid]['state'] == 'ACTIVE':
                    send_msg(conn, {'status': 'ERROR', 'message': 'Student already active'})
                    return
                records[sid] = {'state': 'ACTIVE', 'score': None}
            start = time.monotonic()
            deadline = start + DURATION
            send_msg(conn, {'status': 'OK', 'duration': DURATION, 'total_questions': len(QUESTIONS)})
            logging.info('Exam started student=%s peer=%s', sid, addr)
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    break
                conn.settimeout(min(2.0, left))
                try:
                    msg = recv_msg(conn)
                except socket.timeout:
                    continue
                if msg is None:
                    break
                if not isinstance(msg, dict):
                    send_msg(conn, {'status': 'ERROR', 'message': 'Invalid message'})
                    continue
                if time.monotonic() >= deadline:
                    break
                action = msg.get('action')
                remaining = round(max(0, deadline - time.monotonic()), 2)
                if action == 'GET_QUESTION':
                    idx = msg.get('q_idx')
                    if type(idx) is not int or not 0 <= idx < len(QUESTIONS):
                        send_msg(conn, {'status': 'END_OF_QUESTIONS'})
                        continue
                    q = QUESTIONS[idx]
                    send_msg(conn, {'status': 'OK', 'q_idx': idx, 'id': q['id'],
                                    'question': q['question'], 'options': q['options'],
                                    'remaining_time': remaining})
                elif action == 'SUBMIT_ANSWER':
                    qid = msg.get('q_id')
                    answer = msg.get('answer')
                    if type(qid) is not int or not any(q['id'] == qid for q in QUESTIONS) or answer not in ('A','B','C','D'):
                        send_msg(conn, {'status': 'ERROR', 'message': 'Invalid question or answer'})
                        continue
                    responses[qid] = answer
                    send_msg(conn, {'status': 'ACCEPTED', 'remaining_time': remaining})
                elif action == 'FINISH':
                    completed = True
                    break
                else:
                    send_msg(conn, {'status': 'ERROR', 'message': 'Unknown action'})
            score = sum(responses.get(q['id']) == q['answer'] for q in QUESTIONS)
            took = round(min(DURATION, time.monotonic() - start), 2)
            with lock:
                records[sid] = {'state': 'FINISHED' if completed else 'CLOSED', 'score': score, 'time_taken': took}
            try:
                conn.settimeout(2)
                send_msg(conn, {'status': 'RESULT', 'student_id': sid, 'score': score,
                                'total': len(QUESTIONS), 'time_taken_sec': took})
            except (OSError, TimeoutError):
                pass
            logging.info('Exam ended student=%s score=%s/%s elapsed=%.2fs', sid, score, len(QUESTIONS), took)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logging.warning('Client %s error: %s', addr, exc)
    finally:
        if sid:
            with lock:
                if records.get(sid, {}).get('state') == 'ACTIVE':
                    records[sid] = {'state': 'DISCONNECTED', 'score': None}
        conn.close()


def main():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((HOST, PORT))
        server.listen(128)
        logging.info('Exam TCP server listening on %s:%s', HOST, PORT)
        while True:
            conn, addr = server.accept()
            threading.Thread(target=serve_client, args=(conn, addr), daemon=True).start()

if __name__ == '__main__':
    main()
