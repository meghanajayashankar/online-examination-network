import os
import socket
import subprocess
import sys
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from protocol import send_msg, recv_msg

class TestExam(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.port = 19999
        cls.proc = subprocess.Popen([sys.executable, str(ROOT/'server.py')], cwd=ROOT,
                                    env={**os.environ, 'EXAM_PORT': str(cls.port), 'EXAM_DURATION':'3'},
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for i in range(30):
            try:
                cls.sock = socket.create_connection(('127.0.0.1', cls.port), timeout=1)
                cls.sock.close()
                break
            except ConnectionRefusedError:
                time.sleep(.1)
        else:
            raise RuntimeError('Server failed to start')

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)

    def connect(self):
        s = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        s.settimeout(5)
        return s

    def test_full_exam(self):
        with self.connect() as s:
            send_msg(s, {'action':'REGISTER','student_id':'T1'})
            self.assertEqual(recv_msg(s)['status'], 'OK')
            send_msg(s, {'action':'GET_QUESTION','q_idx':0})
            q = recv_msg(s)
            self.assertEqual(q['id'],1)
            send_msg(s, {'action':'SUBMIT_ANSWER','q_id':1,'answer':'B'})
            self.assertEqual(recv_msg(s)['status'], 'ACCEPTED')
            send_msg(s, {'action':'FINISH'})
            result = recv_msg(s)
            self.assertEqual(result['score'],1)

    def test_invalid_answer(self):
        with self.connect() as s:
            send_msg(s, {'action':'REGISTER','student_id':'T2'})
            recv_msg(s)
            send_msg(s, {'action':'SUBMIT_ANSWER','q_id':1,'answer':'Z'})
            self.assertEqual(recv_msg(s)['status'], 'ERROR')

    def test_duplicate_active(self):
        with self.connect() as a, self.connect() as b:
            send_msg(a, {'action':'REGISTER','student_id':'DUP'})
            self.assertEqual(recv_msg(a)['status'], 'OK')
            send_msg(b, {'action':'REGISTER','student_id':'DUP'})
            self.assertEqual(recv_msg(b)['status'], 'ERROR')

    def test_timer(self):
        with self.connect() as s:
            send_msg(s, {'action':'REGISTER','student_id':'TIMER'})
            recv_msg(s)
            s.settimeout(6)
            self.assertEqual(recv_msg(s)['status'], 'RESULT')

if __name__=='__main__':
    unittest.main()
