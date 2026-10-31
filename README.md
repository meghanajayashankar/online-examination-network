Online Examination Network (TCP + SDN)
A multi-client examination system using TCP sockets and a Ryu/OpenFlow 1.3 controller. It delivers questions, accepts answers, enforces a server-side timer, calculates scores, records application telemetry, and includes concurrent-load tests. The Mininet topology places the server and student/background hosts behind two switches with a constrained inter-switch link for congestion experiments.
Features
- Concurrent TCP clients (one thread per connection) and length-prefixed JSON messages.
- Registration, question delivery, answer validation/submission, timer enforcement and scoring.
- Per-request/application events in results/server_metrics.jsonl; final results in results/exam_results.jsonl.
- Ryu controller learns MAC addresses, gives TCP flows on port 9999 a higher-priority flow rule, logs exam traffic, and polls OpenFlow port/flow statistics every five seconds.
- Mininet topology with a 5-Mbit/s inter-switch link and 10-ms delay, plus a concurrent load generator reporting latency percentiles and Jain's fairness index.
- Unit and local end-to-end integration tests.
Important: OpenFlow priority controls matching/rule selection, not guaranteed bandwidth by itself. For actual queue-based QoS, configure OVS queues/HTB and map flows to queues; this project logs/observes port counters and prioritizes exam-flow rules, and the constrained link enables congestion experiments. Report only results you actually measure.

Requirements
- Python 3.9+ for the socket application (no third-party Python packages required).
- For SDN experiments: Linux VM/Ubuntu with Mininet, Open vSwitch and a Ryu-compatible Python environment. Ryu and Mininet are not reliably supported as native Windows tools; use a Linux VM/department lab machine.
Quick start: local socket test (Windows, macOS or Linux)
Terminal 1:
python server.py --host 127.0.0.1 --port 9999 --duration 120
Terminal 2 (repeat in other terminals for concurrent students):
python client.py --host 127.0.0.1 --port 9999 --student-id S001
Run a concurrent test in another terminal:
python load_test.py --host 127.0.0.1 --port 9999 --clients 20 --duration 10
It writes a detailed JSON report to results/load_test.json. Server telemetry and scores are appended to the JSONL files in results/.
Web UI (student portal + admin dashboard)
A modern browser interface is included in web/ and connects to the existing TCP exam server through web_bridge.py. The bridge uses only Python's standard library; no Flask, Node.js, database, or frontend build step is required. Student registration, question requests, answer submissions, and final scoring all pass through the original length-prefixed TCP protocol. The admin dashboard reads the server's JSONL telemetry/results and the controller's optional SDN telemetry.
Run locally on Windows
Open Terminal 1 in this folder and start the original TCP server:
python server.py --host 127.0.0.1 --port 9999 --duration 120
Open Terminal 2 and start the web bridge:
python web_bridge.py --host 127.0.0.1 --port 8080 --tcp-host 127.0.0.1 --tcp-port 9999
Open http://127.0.0.1:8080 in a browser. Choose Student portal to take the exam or Admin console to view server telemetry and results. For a LAN demo, bind the bridge to 0.0.0.0 and use the host machine's LAN IP in the browser; keep the TCP server reachable from the bridge host.
Run with Mininet + Ryu
When the TCP server is running inside Mininet on 10.0.0.100:9999, start the web bridge on the machine that can reach that host:
python3 web_bridge.py --host 0.0.0.0 --port 8080 --tcp-host 10.0.0.100 --tcp-port 9999
The browser uses HTTP to reach the bridge; the bridge opens the original TCP socket connection to the Mininet-hosted examination server. Ryu controller events are appended to results/controller_metrics.jsonl and appear in the admin console when the controller is running.
UI/API notes
- GET /api/admin returns derived dashboard data; GET /api/health reports bridge configuration.
- POST /api/register, /api/question, /api/answer, and /api/finish are the browser-to-TCP adapter endpoints.
- Active sessions are reconstructed from registration and session-end telemetry, so they are best-effort after a process restart.
- This is a classroom/demo interface, not a production exam platform: add TLS, real authentication, CSRF protection, persistent session storage, and stronger access controls before deployment beyond a trusted lab.
Tests
python -m unittest discover -s tests -v
The integration test launches a short-lived local server on a test port and verifies registration, question delivery, submission and result calculation. It does not require Mininet/Ryu.
Mininet + Ryu demonstration (Linux)
1. Install/start Open vSwitch and Mininet in a Linux VM. Ensure ryu-manager, mn, ovs-vsctl and iperf are available.
2. In terminal A, from this folder, start the controller:
   ryu-manager controller.py
   Controller listens on the standard OpenFlow port 6633.
3. In terminal B, launch the topology as root:
   sudo python3 topology.py
   Mininet opens its CLI. First verify pingall works.
4. In the Mininet CLI, start the server on the server host:
   hsrv python3 server.py --host 10.0.0.100 --port 9999 --duration 120 > /tmp/exam-server.log 2>&1 &
5. Start student clients from Mininet hosts (one command per host/session):
   h1 python3 client.py --host 10.0.0.100 --student-id S001
   h2 python3 client.py --host 10.0.0.100 --student-id S002
   If interactive input is awkward inside the Mininet CLI, run a scripted client/load test from the host namespace or open separate xterms (xterm h1 h2 hsrv). Ensure the project folder is accessible in host namespaces; Mininet hosts normally share the filesystem.
6. Check Ryu logs for EXAM TCP observed, PORT_STATS, and FLOW_STATS. Check /tmp/exam-server.log for concurrent client sessions.
Congestion and comparison plan
The topology constrains the s1-s2 link to 5 Mbit/s and adds 10 ms delay. To create background load, use a second terminal/xterm or Mininet CLI:
hbg iperf -s -p 5001 > /tmp/iperf-server.log 2>&1 &
h1 iperf -c 10.0.0.3 -p 5001 -t 60
For repeatable experiments, run a fixed number of clients and the same background load for each condition. Suggested conditions:
Condition	Setup	Record
Baseline	No background iperf traffic	avg/p50/p95 request latency, successful clients, submissions
Congested	Run iperf across shared link	Same metrics + port drop counters
SDN-aware	Controller active, verify exam flow rules/counters	Same metrics + Ryu flow/port logs


Run load_test.py for each condition and save each output with a distinct --output results/<condition>.json. Compare the numbers; don't fill in fabricated measurements. Jain fairness is calculated from the number of accepted submissions per client: (sum(x)^2)/(n*sum(x^2)), where 1.0 indicates equal counts. With equal client workloads this is a useful indicator, but discuss its limitations.
Protocol
Each TCP message is a 4-byte network-order unsigned length followed by a UTF-8 JSON object. Client actions: REGISTER, GET_QUESTION, SUBMIT_ANSWER, FINISH; PING is also supported. This framing avoids relying on TCP packet/message boundaries.
Project structure
online_examination_network/
├── client.py
├── web_bridge.py
├── web/
│   └── index.html
├── server.py
├── protocol.py
├── questions.json
├── controller.py
├── topology.py
├── load_test.py
├── tests/
├── results/
├── run_local.sh
└── README.md
Known limitations / next steps
- Demo-grade project: no TLS, persistent database, authentication provider or proctoring. Do not use for real high-stakes exams without security and privacy work.
- Results are append-only JSONL files; clear/rotate them before a fresh experiment if needed.
- Controller packet-in learning and flow rules demonstrate SDN integration. Actual QoS bandwidth reservation requires explicit OVS queues and controller queue actions, which depend on the OVS/Mininet environment.
- Client timestamps are informational and are not trusted for grading; the timer is enforced using the server's monotonic clock.
