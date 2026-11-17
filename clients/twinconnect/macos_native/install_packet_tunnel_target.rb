#!/usr/bin/env ruby
# Registers a macOS packet tunnel target in the generated Flutter Xcode project.
# CODE_SIGNING_ALLOWED=NO can compile the extension in CI, but it cannot
# establish a VPN until signed with a suitable Network Extension entitlement.
require 'xcodeproj'
project_file = File.expand_path('../macos/Runner.xcodeproj', __dir__)
raise 'Flutter macOS project missing' unless File.directory?(project_file)
project = Xcodeproj::Project.open(project_file)
runner = project.targets.find { |t| t.name == 'Runner' }
raise 'Runner missing' unless runner
if project.targets.any? { |t| t.name == 'PacketTunnel' }
  puts 'macOS PacketTunnel target already exists'
  exit 0
end

extension = project.new_target(:app_extension, 'PacketTunnel', :osx, '11.0')
extension.product_reference.name = 'PacketTunnel.appex'
extension.product_reference.path = 'PacketTunnel.appex'
extension.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['PRODUCT_NAME'] = 'PacketTunnel'
  settings['SWIFT_VERSION'] = '5.0'
  settings['MACOSX_DEPLOYMENT_TARGET'] = '11.0'
  settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.twinpanel.twinconnect.PacketTunnel'
  settings['INFOPLIST_FILE'] = '../macos_native/PacketTunnel-Info.plist'
  settings['GENERATE_INFOPLIST_FILE'] = 'NO'
  settings['CODE_SIGN_ENTITLEMENTS'] = '../macos_native/PacketTunnel.entitlements'
  settings['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
  settings['SKIP_INSTALL'] = 'YES'
  settings['MARKETING_VERSION'] = '0.1.0'
  settings['CURRENT_PROJECT_VERSION'] = '1'
  settings['CODE_SIGN_STYLE'] = 'Automatic'
end
group = project.main_group.new_group('TwinConnect Mac PacketTunnel', '../macos_native')
%w[PacketTunnelProvider.swift TwinConnectWireGuardEngine.swift libbox/TwinConnectMacTunnelPolicy.swift libbox/TwinConnectMacLibboxPlatform.swift libbox/TwinConnectMacLibboxEngine.swift mieru/TwinConnectMacMieruCore.swift mieru/TwinConnectMacMieruTunnelEngine.swift].each do |file|
  ref = group.new_file(file)
  extension.source_build_phase.add_file_reference(ref)
end
group.new_file('PacketTunnel-Info.plist')
group.new_file('PacketTunnel.entitlements')
runner.add_dependency(extension)
embed = runner.new_copy_files_build_phase('Embed App Extensions')
embed.dst_subfolder_spec = '13'
embed.dst_path = ''
build_file = embed.add_file_reference(extension.product_reference)
build_file.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }
# macOS Flutter projects may omit the iOS-only "Thin Binary" phase.
# Embed before any shell scripts so generated build phases cannot introduce
# a dependency cycle; if there is no shell script, append at the end.
shell = runner.build_phases.find { |p| p.isa == 'PBXShellScriptBuildPhase' }
runner.build_phases.delete(embed)
if shell
  runner.build_phases.insert(runner.build_phases.index(shell), embed)
else
  runner.build_phases << embed
end
project.save
puts 'Created macOS PacketTunnel extension target (backend not linked)'
