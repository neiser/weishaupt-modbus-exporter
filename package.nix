{ lib, stdenvNoCC, python3 }:

stdenvNoCC.mkDerivation {
  pname = "weishaupt-modbus-exporter";
  version = "1.0.0";

  src = ./weishaupt_modbus_exporter.py;
  dontUnpack = true;

  buildInputs = [ python3 ];

  installPhase = ''
    install -Dm755 $src $out/bin/weishaupt-modbus-exporter
    patchShebangs $out/bin
  '';

  meta = {
    description = "Prometheus exporter for Weishaupt WWP heat pumps via Modbus TCP";
    license = lib.licenses.mit;
    platforms = lib.platforms.linux;
    mainProgram = "weishaupt-modbus-exporter";
  };
}
