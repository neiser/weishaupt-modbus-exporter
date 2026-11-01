# weishaupt-modbus-exporter

Prometheus exporter for Weishaupt WWP heat pumps (WWP-CPU-COM controller) via Modbus TCP.
It is a single Python 3 script that uses only the standard library.

The metric names keep the `wemportal_` prefix of the former WEM portal scraper, so existing
dashboards and alerts keep working.

## Usage

```
weishaupt-modbus-exporter --host <heat pump> [--port 502] [--unit 1] [--listen 0.0.0.0:9808]
```

Every scrape of `http://<listen>/metrics` reads all registers once. If the heat pump cannot
be reached, the response only contains `wemportal_up 0`; otherwise `wemportal_up 1`.
Registers that report one of the "no value" markers (-32768, -32767, ...) are left out.

## Metrics

Unless noted otherwise, the registers come from the Weishaupt "Datenpunktliste Modbus TCP (WWP)",
document number 83807301. Input registers are read with function code 4, holding registers with
function code 3.

| Metric (`wemportal_` prefix) | Type | Register | Meaning |
|---|---|---|---|
| `current_outside_temperature_celsius` | gauge | 30001 | Outside temperature |
| `error_code` | gauge | 30003 | Active error code, 65535 = none |
| `warning_code` | gauge | 30004 | Active warning code, 65535 = none |
| `system_state`, `system_state_info{value}` | gauge | 30006 | System operating state |
| `room_set_temperature_celsius` | gauge | 31101 | Room set temperature, heating circuit 1 |
| `water_inlet_set_temperature_celsius` | gauge | 31104 | Flow set temperature, heating circuit 1 |
| `hot_water_set_temperature_celsius` | gauge | 32101 | Hot water set temperature |
| `hot_water_temperature_celsius` | gauge | 32102 | Hot water temperature |
| `operating_state`, `operating_state_info{value}` | gauge | 33101 | Heat pump operating state |
| `fault_free` | gauge | 33102 | 1 = no fault, 0 = fault active |
| `performance_request_ratio` | gauge | 33103 | Requested power in percent |
| `water_inlet_temperature_celsius` | gauge | 33104 | Flow temperature |
| `water_outlet_temperature_celsius` | gauge | 33105 | Return temperature |
| `lwt_temperature_celsius` | gauge | 33107 | Flow temperature LWT (B4), undocumented |
| `sum_flow_temperature_celsius` | gauge | 33111 | Common flow temperature (B7) |
| `wez2_state` | gauge | 34101 | State of the second heat generator |
| `heating1_cycles_total` | counter | 34102 | Switching cycles of electric heater 1 |
| `heating1_state` | gauge | 34104 | State of electric heater 1 |
| `heating2_state` | gauge | 34105 | State of electric heater 2 |
| `sg_ready1_state`, `sg_ready2_state` | gauge | 35101, 35102 | SG Ready inputs |
| `total_energy_per_day`, `_yesterday`, `_per_month`, `_per_year` | gauge | 36101-36104 | Thermal energy, total, in kWh |
| `heating_energy_per_day`, `_per_month`, `_per_year` | gauge | 36201, 36203, 36204 | Thermal energy for heating in kWh |
| `water_energy_per_day`, `_per_month`, `_per_year` | gauge | 36301, 36303, 36304 | Thermal energy for hot water in kWh |
| `cooling_energy_per_day`, `_per_month`, `_per_year` | gauge | 36401, 36403, 36404 | Thermal energy for cooling in kWh |
| `electrical_energy_per_day`, `_per_month`, `_per_year` | gauge | 36701, 36703, 36704 | Electrical energy in kWh, undocumented |
| `system_operating_mode`, `system_operating_mode_info{value}` | gauge | 40001 (holding) | System operating mode |
| `pv_power_setpoint_watts` | gauge | 40002 (holding) | PV power setpoint, for example written by evcc |
| `room_comfort_set_temperature_celsius`, `room_normal_…`, `room_setback_…` | gauge | 41105-41107 (holding) | Room set temperatures comfort, normal and setback, heating circuit 1 |
| `heating_curve_ratio` | gauge | 41108 (holding) | Heating curve of heating circuit 1, undocumented |
| `hot_water_normal_set_temperature_celsius`, `hot_water_setback_…` | gauge | 42103, 42104 (holding) | Hot water set temperatures normal and setback |
| `up` | gauge | | 1 if the last scrape reached the heat pump |

Notes on the register sources:

- 33107 is not part of 83807301. Its value matches the portal value "LWT" (sensor B4).
- 34102 is listed in 83807301 as "Betriebsstunden 2ter WEZ" (operating hours of the second
  heat generator). Its value matches the portal value "Schaltspiele E1" (switching cycles of
  electric heater 1), so it is exported as a counter with that meaning.
- 36701-36704 (electrical energy) are not part of 83807301. They are known from the
  Home Assistant community.
- 41108 is not part of 83807301. Its value (60) matches the heating curve 0.60 set on
  the device.

## What the heat pump offers over Modbus

A read-only scan of all addresses (function codes 3 and 4) on firmware WWP-CPU T5.3 found:

- Only 30001-39998 (input) and 40001-49998 (holding) answer. Every read that starts
  elsewhere gets exception 2.
- 141 data points carry values; every other address reads 0xFFFF. A block read that
  includes such an address answers with the exception bit set but still sends the
  data, so a standard Modbus client drops the whole block. The exporter reads one
  register per request for this reason.
- A read of 125 registers hangs the connection until the timeout; 120 work.
- The data points are those of 83807301 plus a few undocumented ones (33107, 34102,
  34103, 36701-36704, 36801, 41108-41112). The WEM portal shows more values than
  Modbus offers: refrigerant, heat exchanger, hot gas and air inlet temperatures,
  compressor frequency, operating hours and cycles, defrost cycles, switch-over
  valve, live volume flow and electrical power are not available in any register,
  neither as 16 nor as 32 bit.
- All energy statistics registers (36101-36801) read 0 on this firmware, while the
  portal shows the same statistics with values.
- The Modbus setting "Zugriff" has the values Aus, Ein and Service. Service allows
  access for 60 minutes only (manual 83315301); it does not add registers.

The `*_info` metrics carry the decoded state name in the `value` label, for example
`wemportal_operating_state_info{value="HEIZBETRIEB"} 1`.

## NixOS

Add the flake as an input and import the module:

```nix
{
  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    weishaupt-modbus-exporter.url = "github:neiser/weishaupt-modbus-exporter";
    weishaupt-modbus-exporter.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { nixpkgs, weishaupt-modbus-exporter, ... }: {
    nixosConfigurations.home-server = nixpkgs.lib.nixosSystem {
      system = "x86_64-linux";
      modules = [
        weishaupt-modbus-exporter.nixosModules.default
        {
          services.weishaupt-modbus-exporter = {
            enable = true;
            host = "wwp-cpu-com.grub.internal";
            # port = 502; unit = 1; listen = "127.0.0.1:9808"; extraArgs = [ ];
          };
        }
      ];
    };
  };
}
```

The service runs with `DynamicUser` and restarts automatically. The flake also provides
`packages.x86_64-linux.default` and `overlays.default`, which adds `pkgs.weishaupt-modbus-exporter`.

## License

MIT, see [LICENSE](LICENSE).
