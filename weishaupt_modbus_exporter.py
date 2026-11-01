#!/usr/bin/env python3
"""Prometheus exporter for Weishaupt WWP heat pumps via Modbus TCP.

Metric names follow the former WEM portal scraper (wemportal_*) where the meaning is the same.
Register list: Weishaupt Datenpunktliste Modbus TCP (WWP), 83807301.
"""
import argparse
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

NO_VALUE = {-32768, -32767, -32766, -32758, -32757}

STATES = (
    'UNDEFINIERT RELAISTEST NOTAUS DIAGNOSE HANDBETRIEB HANDBETRIEB_HEIZEN HANDBETRIEB_KUEHLEN '
    'MANUELLER_ABTAUBETRIEB ABTAUEN WEZ2 EVU_SPERRE SG_TARIF SG_MAXIMAL TARIFLADUNG ERHOEHTER_BETRIEB '
    'STANDZEIT STANDBYBETRIEB SPUELBETRIEB FROSTSCHUTZ HEIZBETRIEB WARMWASSERBETRIEB LEGIONELLENSCHUTZ '
    'UMSCHALTUNG_HZ_KU KUEHLBETRIEB PASSIVE_KUEHLUNG SOMMERBETRIEB SCHWIMMBAD URLAUB ESTRICHT GESPERRT '
    'SPERRE_AT SPERRE_SOMMER SPERRE_WINTER EINSATZGRENZE HK_SPERRE BEREITSCHAFT REGENERATIV SGR3_HEIZEN '
    'SGR3_KUEHLEN SGR3_WARMWASSER SGR4_HEIZEN SGR4_KUEHLEN SGR4_WARMWASSER OELRUECKFUEHRUNG'
).split()
SYSTEM_MODES = {1: 'HEIZEN', 2: 'KUEHLEN', 3: 'SOMMER', 4: 'STANDBY', 5: '2.WEZ'}

INPUT, HOLDING = 4, 3

# (metric, type, function code, register, scale, help)
REGISTERS = [
    ('current_outside_temperature_celsius', 'gauge', INPUT, 30001, 0.1, 'Außentemperatur'),
    ('error_code', 'gauge', INPUT, 30003, 1, 'Aktiver Fehlercode, 65535 = keiner'),
    ('warning_code', 'gauge', INPUT, 30004, 1, 'Aktiver Warncode, 65535 = keiner'),
    ('room_set_temperature_celsius', 'gauge', INPUT, 31101, 0.1, 'Raumsolltemperatur Heizkreis 1'),
    ('water_inlet_set_temperature_celsius', 'gauge', INPUT, 31104, 0.1, 'Vorlaufsolltemperatur Heizkreis 1'),
    ('hot_water_set_temperature_celsius', 'gauge', INPUT, 32101, 0.1, 'Warmwassersolltemperatur'),
    ('hot_water_temperature_celsius', 'gauge', INPUT, 32102, 0.1, 'Warmwassertemperatur'),
    ('fault_free', 'gauge', INPUT, 33102, 1, '1 = störungsfreier Betrieb, 0 = Fehler aktiv'),
    ('performance_request_ratio', 'gauge', INPUT, 33103, 1, 'Leistungsanforderung in %'),
    ('water_inlet_temperature_celsius', 'gauge', INPUT, 33104, 0.1, 'Vorlauftemperatur'),
    ('water_outlet_temperature_celsius', 'gauge', INPUT, 33105, 0.1, 'Rücklauftemperatur'),
    # 33107 is not in 83807301; it matches the portal value "LWT" (B4).
    ('lwt_temperature_celsius', 'gauge', INPUT, 33107, 0.1, 'Vorlauftemperatur LWT (B4)'),
    ('sum_flow_temperature_celsius', 'gauge', INPUT, 33111, 0.1, 'Summenvorlauf (B7)'),
    ('wez2_state', 'gauge', INPUT, 34101, 1, 'Status 2. WEZ'),
    # 83807301 calls 34102 "Betriebsstunden 2ter WEZ"; its value matches the portal value "Schaltspiele E1".
    ('heating1_cycles_total', 'counter', INPUT, 34102, 1, 'Schaltspiele E-Heizung 1'),
    ('heating1_state', 'gauge', INPUT, 34104, 1, 'Status E-Heizung 1'),
    ('heating2_state', 'gauge', INPUT, 34105, 1, 'Status E-Heizung 2'),
    ('sg_ready1_state', 'gauge', INPUT, 35101, 1, 'Eingang SG Ready 1'),
    ('sg_ready2_state', 'gauge', INPUT, 35102, 1, 'Eingang SG Ready 2'),
    ('total_energy_per_day', 'gauge', INPUT, 36101, 1, 'Thermische Energie gesamt heute in kWh'),
    ('total_energy_yesterday', 'gauge', INPUT, 36102, 1, 'Thermische Energie gesamt gestern in kWh'),
    ('total_energy_per_month', 'gauge', INPUT, 36103, 1, 'Thermische Energie gesamt Monat in kWh'),
    ('total_energy_per_year', 'gauge', INPUT, 36104, 1, 'Thermische Energie gesamt Jahr in kWh'),
    ('heating_energy_per_day', 'gauge', INPUT, 36201, 1, 'Thermische Energie Heizen heute in kWh'),
    ('heating_energy_per_month', 'gauge', INPUT, 36203, 1, 'Thermische Energie Heizen Monat in kWh'),
    ('heating_energy_per_year', 'gauge', INPUT, 36204, 1, 'Thermische Energie Heizen Jahr in kWh'),
    ('water_energy_per_day', 'gauge', INPUT, 36301, 1, 'Thermische Energie Warmwasser heute in kWh'),
    ('water_energy_per_month', 'gauge', INPUT, 36303, 1, 'Thermische Energie Warmwasser Monat in kWh'),
    ('water_energy_per_year', 'gauge', INPUT, 36304, 1, 'Thermische Energie Warmwasser Jahr in kWh'),
    ('cooling_energy_per_day', 'gauge', INPUT, 36401, 1, 'Thermische Energie Kühlen heute in kWh'),
    ('cooling_energy_per_month', 'gauge', INPUT, 36403, 1, 'Thermische Energie Kühlen Monat in kWh'),
    ('cooling_energy_per_year', 'gauge', INPUT, 36404, 1, 'Thermische Energie Kühlen Jahr in kWh'),
    # 367xx is not in 83807301; known from the Home Assistant community.
    ('electrical_energy_per_day', 'gauge', INPUT, 36701, 1, 'Elektrische Energie heute in kWh'),
    ('electrical_energy_per_month', 'gauge', INPUT, 36703, 1, 'Elektrische Energie Monat in kWh'),
    ('electrical_energy_per_year', 'gauge', INPUT, 36704, 1, 'Elektrische Energie Jahr in kWh'),
    ('pv_power_setpoint_watts', 'gauge', HOLDING, 40002, 1, 'SollwertPV (Leistungsvorgabe, z. B. von evcc)'),
]
STATE_REGISTERS = [
    ('system_state', INPUT, 30006, STATES, 'Betriebsstatusanzeige System'),
    ('operating_state', INPUT, 33101, STATES, 'Betrieb Wärmepumpe'),
    ('system_operating_mode', HOLDING, 40001, SYSTEM_MODES, 'Systembetriebsart'),
]


class ModbusClient:
    def __init__(self, host, port, unit):
        self.address = (host, port)
        self.unit = unit
        self.sock = None
        self.tid = 0

    def read(self, fc, register):
        try:
            return self._read(fc, register)
        except OSError:
            self.close()
            return self._read(fc, register)

    def _read(self, fc, register):
        if self.sock is None:
            self.sock = socket.create_connection(self.address, timeout=5)
        self.tid = (self.tid + 1) & 0xFFFF
        self.sock.sendall(struct.pack('>HHHBBHH', self.tid, 0, 6, self.unit, fc, register, 1))
        response = self._recv(9)
        if response[7] & 0x80:
            return None
        payload = self._recv(response[8])
        return struct.unpack('>h', payload[:2])[0]

    def _recv(self, n):
        data = b''
        while len(data) < n:
            chunk = self.sock.recv(n - len(data))
            if not chunk:
                raise ConnectionError('connection closed')
            data += chunk
        return data

    def close(self):
        if self.sock is not None:
            self.sock.close()
        self.sock = None


def unsigned(value):
    return value & 0xFFFF


def collect(client):
    lines = []
    for metric, kind, fc, register, scale, help_text in REGISTERS:
        value = client.read(fc, register)
        if value is None or value in NO_VALUE:
            continue
        if scale == 1:
            value = unsigned(value)
        name = 'wemportal_' + metric
        lines += [f'# HELP {name} {help_text}', f'# TYPE {name} {kind}', f'{name} {round(value * scale, 1)}']
    for metric, fc, register, names, help_text in STATE_REGISTERS:
        value = client.read(fc, register)
        if value is None:
            continue
        label = names[value] if isinstance(names, list) and value < len(names) else (
            names.get(value, str(value)) if isinstance(names, dict) else str(value))
        name = 'wemportal_' + metric
        lines += [f'# HELP {name} {help_text}', f'# TYPE {name} gauge', f'{name} {value}',
                  f'# HELP {name}_info {help_text}', f'# TYPE {name}_info gauge', f'{name}_info{{value="{label}"}} 1']
    return lines


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=502)
    parser.add_argument('--unit', type=int, default=1)
    parser.add_argument('--listen', default='0.0.0.0:9808')
    args = parser.parse_args()

    client = ModbusClient(args.host, args.port, args.unit)
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            with lock:
                try:
                    lines = collect(client) + ['wemportal_up 1']
                except OSError as e:
                    client.close()
                    self.log_message('modbus error: %s', e)
                    lines = ['wemportal_up 0']
            body = ('\n'.join(lines) + '\n').encode()
            self.send_response(200)
            self.send_header('Content-Type', 'text/plain; version=0.0.4; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt, *a):
            if 'modbus' in fmt:
                super().log_message(fmt, *a)

    host, port = args.listen.rsplit(':', 1)
    ThreadingHTTPServer((host, int(port)), Handler).serve_forever()


if __name__ == '__main__':
    main()
