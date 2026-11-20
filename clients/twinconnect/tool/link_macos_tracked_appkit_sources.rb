#!/usr/bin/env ruby
# On Metal-less Macs, AppKit classes are deliberately CONCATENATED into
# generated macos/Runner/MainFlutterWindow.swift by install_macos_bridge.py.
# They are NOT standalone Xcode Runner source-phase files.
# Refresh that generated source on every build rather than incorrectly
# searching for standalone PBXBuildFile entries.
require 'digest'

root = File.expand_path('..', __dir__)
window = File.join(root, 'macos/Runner/MainFlutterWindow.swift')
installer = File.join(root, 'macos_native/install_macos_bridge.py')
abort 'MACOS_MAIN_WINDOW_MISSING' unless File.file?(window)
abort 'MACOS_BRIDGE_INSTALLER_MISSING' unless File.file?(installer)

unless system('/usr/bin/env', 'python3', installer)
  abort 'MACOS_BRIDGE_REFRESH_FAILED'
end

generated = File.read(window, encoding: 'UTF-8')
{
  'TwinConnectMacOSNativeDirectory.swift' => '// TWINCONNECT_MACOS_NATIVE_DIRECTORY_V1',
  'TwinConnectMacOSNativeDashboard.swift' => '// TWINCONNECT_MACOS_NATIVE_DASHBOARD_V1'
}.each do |filename, marker|
  file = File.join(root, 'macos_native', filename)
  abort "TRACKED_APPKIT_SOURCE_MISSING: #{filename}" unless File.file?(file)
  source = File.read(file, encoding: 'UTF-8')
  abort "APPKIT_MARKER_MISSING: #{filename}" unless generated.scan(marker).length == 1
  # Installer appends the two complete files to generated MainFlutterWindow;
  # a partial or stale copy must make the build fail, not silently succeed.
  abort "APPKIT_STALE_GENERATED_SOURCE: #{filename}" unless generated.include?(source)
  puts "APPKIT_EMBED_VERIFIED: #{filename} SHA256=#{Digest::SHA256.hexdigest(source)[0, 12]}"
end
puts 'APPKIT_GENERATED_SOURCE_REFRESHED'
