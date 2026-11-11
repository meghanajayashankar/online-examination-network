"""Run on Linux with Mininet installed: sudo python3 topology.py"""
import os
import time
from pathlib import Path
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

ROOT = Path(__file__).resolve().parent

class ExamTopology(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')
        hsrv = self.addHost('hsrv', ip='10.0.0.100/24')
        for number in range(1, 4):
            host = self.addHost(f'h{number}', ip=f'10.0.0.{number}/24')
            self.addLink(host, s1)
        bg = self.addHost('hbg', ip='10.0.0.50/24')
        self.addLink(bg, s1)
        self.addLink(s2, hsrv)
        self.addLink(s1, s2, cls=TCLink, bw=2, delay='5ms', max_queue_size=100)


def run():
    net = Mininet(topo=ExamTopology(),
                  controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6633),
                  switch=OVSSwitch, link=TCLink, autoSetMacs=True)
    try:
        net.start()
        time.sleep(3)
        info('*** Connectivity test ***\n')
        net.pingAll()
        host = net.get('hsrv')
        logfile = str(ROOT / 'results' / 'server.log')
        host.cmd(f'cd {ROOT} && python3 -u server.py > {logfile} 2>&1 &')
        info('*** Exam server hsrv 10.0.0.100:9999\n')
        info('*** Commands: h1 python3 client.py; h2 python3 load_test.py --host 10.0.0.100 --clients 10 --label experiment\n')
        CLI(net)
    finally:
        net.stop()

if __name__ == '__main__':
    setLogLevel('info')
    run()
