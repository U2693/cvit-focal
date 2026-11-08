{
  description = "biscvit - Centurion CPU6 terminal UI emulator/monitor";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
  };

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" "x86_64-darwin" "aarch64-darwin" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      packages = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          dotnet = pkgs.dotnetCorePackages;
        in
        {
          default = dotnet.buildDotnetModule {
            pname = "biscvit";
            version = "0.1.0";
            src = self;

            projectFile = "biscvit.csproj";
            nugetDeps = [ ];

            dotnet-sdk = dotnet.sdk_8_0;
            dotnet-runtime = dotnet.runtime_8_0;

            executables = [ "biscvit" ];
            doCheck = false;

            meta = with pkgs.lib; {
              description = "Centurion CPU6 terminal UI emulator/monitor";
              mainProgram = "biscvit";
              platforms = platforms.unix;
            };
          };
        });

      apps = forAllSystems (system: {
        default = {
          type = "app";
          program = "${self.packages.${system}.default}/bin/biscvit";
        };
      });

      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
        in
        {
          default = pkgs.mkShell {
            packages = [ pkgs.dotnetCorePackages.sdk_8_0 pkgs.dotnetCorePackages.runtime_8_0 ];
            DOTNET_ROOT = "${pkgs.dotnetCorePackages.runtime_8_0}";
          };
        });
    };
}
