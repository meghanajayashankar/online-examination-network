# ExamFlow browser UI

## Quick local demonstration (no Mininet)

Keep `server.py` and `web_ui.py` in the **same folder** with `protocol.py`.

Terminal 1:
```bash
cd ~/Downloads/cn_exam_completed
python3 server.py
```

Terminal 2:
```bash
cd ~/Downloads/cn_exam_completed
python3 -m pip install flask --break-system-packages
python3 web_ui.py
```

Open **http://127.0.0.1:8080** in Ubuntu Firefox. Register and complete an examination. The web server sends the existing length-prefixed JSON messages to TCP server `127.0.0.1:9999`.

## During a Mininet demonstration

The default browser walkthrough above is a **local socket demo**, not evidence that traffic passed through Mininet switches. For a Mininet-path demonstration, run the web gateway inside a student host namespace:
```text
mininet> h1 env EXAM_SERVER_IP=10.0.0.100 python3 web_ui.py &
```
Then launch a browser **inside that same Mininet host namespace** (with graphical X11 configured), navigating to `http://10.0.0.1:8080`. Browser access to `10.0.0.1` from the Ubuntu VM's ordinary browser is not guaranteed because Mininet hosts use separate network namespaces. The existing CLI client and load tests remain the recommended reliable SDN demo.

## Notes
- Don't start a second `server.py` while `topology.py` is running (it starts a server in `hsrv`).
- This lightweight student UI is for local coursework demonstrations, not public deployment. It doesn't implement authentication, TLS, persistent storage, or robust cleanup for abandoned browser sessions.
- UI timer is a visual countdown. The TCP server remains authoritative for the actual time limit.
