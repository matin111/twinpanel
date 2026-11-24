#!/bin/bash
# Reproducible isolated iOS project preparation. Run in an iOS lab checkout.
# Does not alter network configuration or install a privileged service.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/flutter/bin:$HOME/.gem/ruby/2.6.0/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"
if [ ! -f ios/Runner.xcodeproj/project.pbxproj ]; then
  flutter create --platforms=ios --org com.twinpanel --project-name twinconnect --no-pub .
fi
# Flutter create may discover a local developer identity. Never persist it
# in the lab project, and explicitly disable signing on build commands.
ruby -rxcodeproj -e '
  p = Xcodeproj::Project.open("ios/Runner.xcodeproj")
  p.targets.each do |t|
    t.build_configurations.each { |c| c.build_settings.delete("DEVELOPMENT_TEAM") }
  end
  p.build_configurations.each { |c| c.build_settings.delete("DEVELOPMENT_TEAM") }
  p.root_object.attributes.fetch("TargetAttributes", {}).each_value do |a|
    a.delete("DevelopmentTeam")
  end
  p.save
'
ruby ios_native/install_packet_tunnel_target.rb
python3 tool/install_ios_lab_runner_bridge.py
for spec in "iphoneos arm64-apple-ios15.0" "iphonesimulator x86_64-apple-ios15.0-simulator"; do
  read -r sdk target <<< "$spec"
  xcrun --sdk "$sdk" swiftc -typecheck -target "$target" \
    -sdk "$(xcrun --sdk "$sdk" --show-sdk-path)" \
    ios_native/PacketTunnelProvider.swift ios_native/TwinConnectWireGuardEngine.swift
  echo "PASS: $sdk fallback source typecheck"
done
echo 'READY: generated Runner and fail-closed native extension; no runtime verification'
