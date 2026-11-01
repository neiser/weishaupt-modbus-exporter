{ config, lib, ... }:

let
  cfg = config.services.weishaupt-modbus-exporter;
in
{
  options.services.weishaupt-modbus-exporter = {
    enable = lib.mkEnableOption "the Weishaupt Modbus TCP Prometheus exporter";

    package = lib.mkOption {
      type = lib.types.package;
      description = "Exporter package to use.";
    };

    host = lib.mkOption {
      type = lib.types.str;
      example = "wwp-cpu-com.grub.internal";
      description = "Host name or IP address of the heat pump's Modbus TCP interface.";
    };

    port = lib.mkOption {
      type = lib.types.port;
      default = 502;
      description = "Modbus TCP port of the heat pump.";
    };

    unit = lib.mkOption {
      type = lib.types.ints.between 0 255;
      default = 1;
      description = "Modbus unit id.";
    };

    listen = lib.mkOption {
      type = lib.types.str;
      default = "127.0.0.1:9808";
      description = "Address and port the HTTP metrics endpoint listens on.";
    };

    extraArgs = lib.mkOption {
      type = lib.types.listOf lib.types.str;
      default = [ ];
      description = "Extra command line arguments for the exporter.";
    };
  };

  config = lib.mkIf cfg.enable {
    systemd.services.weishaupt-modbus-exporter = {
      description = "Prometheus exporter for the Weishaupt heat pump (Modbus TCP)";
      wantedBy = [ "multi-user.target" ];
      wants = [ "network-online.target" ];
      after = [ "network-online.target" ];
      serviceConfig = {
        ExecStart = lib.escapeShellArgs ([
          (lib.getExe cfg.package)
          "--host" cfg.host
          "--port" (toString cfg.port)
          "--unit" (toString cfg.unit)
          "--listen" cfg.listen
        ] ++ cfg.extraArgs);
        DynamicUser = true;
        Restart = "always";
        RestartSec = 10;
        NoNewPrivileges = true;
        ProtectSystem = "strict";
        ProtectHome = true;
        PrivateTmp = true;
        PrivateDevices = true;
        RestrictAddressFamilies = [ "AF_INET" "AF_INET6" ];
      };
    };
  };
}
