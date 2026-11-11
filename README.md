# Online Examination Network — TCP + Mininet + Ryu SDN

An educational multi-client exam service using Python TCP sockets and length-prefixed JSON. The Mininet network contains three students (`h1`–`h3`), one background-traffic generator (`hbg`), one exam server (`hsrv`), and two OpenFlow 1.3 switches (`s1`, `s2`). A Ryu controller records exam/background flow statistics and can temporarily filter congestion-inducing background traffic.

## Network architecture

```text
h1 --\
h2 --- s1 ===== 2 Mbps / 5 ms ===== s2 --- hsrv (10.0.0.100)
h3 --/ |                                 TCP exam:9999
      hbg (10.0.0.50)                     iperf3:5001
     Ryu remote controller: 127.0.0.1:6633
```

## Files

- `server.py`: threaded TCP server, fixed-duration exams, grading, validation
- `client.py`: interactive TCP examination client
- `protocol.py`: 4-byte length framing + JSON
- `questions.json`: question bank (answers kept on server)
- `controller.py`: Ryu OpenFlow 1.3 learning + monitoring + congestion mitigation
- `topology.py`: Mininet two-switch topology, starts exam server
- `load_test.py`: concurrent synthetic students with measured **request/response RTT**
- `compare_results.py`: baseline vs adaptive metric table / CSV
- `tests/test_exam.py`: socket tests for grading, validation, duplicates, timeout

## Prerequisites

Use Ubuntu Linux or a Mininet-compatible Ubuntu VM. Need: Python 3, Mininet, Open vSwitch, `tc`, `iperf3`, Ryu. Do **not** use the zipped `ryu_env` virtual environment copied between machines; create a compatible one on the VM instead. Ryu is an older dependency: install it in a compatible virtual environment, such as the Python 3.10 setup in your original project, and verify `ryu-manager --version`/controller import. Do not install Mininet into a Windows-only Python shell.

Suggested Ubuntu system packages:

```bash
sudo apt update
sudo apt install -y mininet openvswitch-switch iperf3 python3-pip
```

Keep this project in an accessible location e.g. `~/cn_exam_completed`.

## Part A: verify pure TCP application (no Mininet needed)

Terminal 1:

```bash
cd ~/cn_exam_completed
python3 -m unittest discover -s tests -v
python3 server.py
```

Terminal 2:

```bash
cd ~/cn_exam_completed
python3 client.py  # change SERVER_IP to 127.0.0.1 for this local test
```

For local testing, modify `SERVER_IP` in `client.py` to `127.0.0.1`; for Mininet use `10.0.0.100`.

## Part B: Mininet demo, baseline

Terminal 1, using your working Ryu environment (its own Python):

```bash
cd ~/cn_exam_completed
SDN_MODE=baseline ryu-manager --ofp-tcp-listen-port 6633 controller.py 2>&1 | tee results/controller_baseline.log
```

Terminal 2:

```bash
cd ~/cn_exam_completed
sudo mn -c
sudo python3 topology.py
```

At the `mininet>` prompt:

```bash
h1 python3 client.py
h2 python3 client.py
h3 python3 client.py
```

These interactive clients run sequentially in the Mininet CLI. For genuine concurrent exams, use a terminal for each host with `xterm h1 h2 h3` (requires a graphical desktop / X11), or run several load-test threads on `h1`.

Start `iperf3` background load *inside the Mininet CLI*:

```bash
hsrv iperf3 -s -p 5001 -D
hbg iperf3 -c 10.0.0.100 -p 5001 -t 30 &
h1 python3 load_test.py --host 10.0.0.100 --clients 10 --loops 40 --label baseline
```

The background traffic should saturate the 2 Mbps inter-switch link. Results are written to `results/baseline.json`. Check switch flows from a regular Ubuntu shell:

```bash
sudo ovs-ofctl -O OpenFlow13 dump-flows s1
```

## Part C: adaptive congestion response

Stop the previous Mininet topology (`exit`) and Ryu controller (Ctrl+C). Relaunch Terminal 1 with:

```bash
cd ~/cn_exam_completed
SDN_MODE=adaptive BACKGROUND_THRESHOLD_BPS=150000 BACKGROUND_BLOCK_SECONDS=8 ryu-manager --ofp-tcp-listen-port 6633 controller.py 2>&1 | tee results/controller_adaptive.log
```

Relaunch Mininet (`sudo mn -c; sudo python3 topology.py`), then repeat **the same workload**:

```bash
hsrv iperf3 -s -p 5001 -D
hbg iperf3 -c 10.0.0.100 -p 5001 -t 30 &
h1 python3 load_test.py --host 10.0.0.100 --clients 10 --loops 40 --label adaptive
```

Watch the Ryu log for `MONITOR` stats and `CONGESTION: temporarily BLOCKED`. The temporary drop is a dynamic OpenFlow rule with `priority=200` and `hard_timeout=8`; the rule automatically expires. You can compare the switch flow table before/after. It blocks *background TCP port 5001*, not exam TCP port 9999.

Compare:

```bash
python3 compare_results.py results/baseline.json results/adaptive.json
```

**Important:** sample latency is round-trip time (RTT) for request/response, not one-way delay. Jain's fairness index here compares **completed answer submissions per student**, not equal packet scheduling. Results depend on machine/VM load and experiment timing; repeat at least 3 runs per condition and compare averages. For meaningful comparison, ensure the `iperf3` background flow is active throughout the measured exam load; if test finishes too soon, increase `--loops` to 100 and/or the `iperf3 -t` duration. The adaptive demo is *background-flow filtering*, not a proven queueing QoS guarantee.

## Demo checklist / evidence

1. Show `python3 -m unittest discover -s tests -v` pass.
2. Show three students can register and complete exams; timed completion and marks.
3. Show `mininet> pingall` succeeds with the Ryu controller.
4. Show flow entries priority 100 (exam), 20 (background), temporary 200 drop.
5. Show `MONITOR` and `CONGESTION` controller logs under background traffic.
6. Show baseline/adaptive JSON and comparison CSV with actual numbers.
7. Save terminal screenshots and measured results for the PDF/report and GitHub README.

## Limitations

This is a coursework prototype: no TLS/login credentials, persistent database, reconnectable sessions, or production-grade exam authorization. The congestion-control policy is intentionally simple: threshold-triggered filtering of a known background TCP port. Do not represent it as weighted-fair queueing or guaranteed QoS. The adaptive controller requires a real Mininet/Ryu run to verify flow statistics and packet behavior.
