#!/usr/bin/env ruby
# Compile-only integration: Xcode resolves the real official Libbox XCFramework
# inside PacketTunnel. This does not implement NEPacketTunnelFlow or turn on VPN.
require 'xcodeproj'
root = File.expand_path('../..', __dir__)
project_file = File.join(root, 'macos/Runner.xcodeproj')
framework = File.join(root, 'macos_native/build/libbox/Libbox.xcframework')
raise 'Generated macOS Xcode project missing' unless File.directory?(project_file)
raise 'Built Libbox framework missing' unless File.file?(File.join(framework, 'Info.plist'))
project = Xcodeproj::Project.open(project_file)
target = project.targets.find { |t| t.name == 'PacketTunnel' }
raise 'PacketTunnel extension missing' unless target
raise 'Libbox already linked' if target.frameworks_build_phase.files.any? { |f| f.file_ref&.path&.end_with?('Libbox.xcframework') }

group = project.main_group.find_subpath('TwinConnect Native Libbox', true)
group.set_source_tree('<group>')
ref = group.new_file(framework)
ref.source_tree = '<absolute>'
target.frameworks_build_phase.add_file_reference(ref)
target.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['MACOSX_DEPLOYMENT_TARGET'] = '13.0'
  settings['FRAMEWORK_SEARCH_PATHS'] = [
    '$(inherited)', '$(PROJECT_DIR)/../macos_native/build/libbox'
  ]
end
probe = group.new_file(File.join(root, 'macos_native/libbox/LibboxLinkProbe.swift'))
probe.source_tree = '<absolute>'
target.source_build_phase.add_file_reference(probe)
project.save
puts 'Linked Libbox XCFramework to PacketTunnel for compile-only validation'
