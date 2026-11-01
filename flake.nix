{
  description = "Prometheus exporter for Weishaupt WWP heat pumps via Modbus TCP";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = nixpkgs.legacyPackages.${system};
    in
    {
      packages.${system}.default = pkgs.callPackage ./package.nix { };

      overlays.default = final: prev: {
        weishaupt-modbus-exporter = final.callPackage ./package.nix { };
      };

      nixosModules.default = { pkgs, ... }: {
        imports = [ ./module.nix ];
        services.weishaupt-modbus-exporter.package = nixpkgs.lib.mkDefault
          self.packages.${pkgs.stdenv.hostPlatform.system}.default;
      };
    };
}
