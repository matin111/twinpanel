#!/usr/bin/env ruby
# Generate a real NEPacketTunnelProvider target inside the Flutter-generated
# Xcode project. Run AFTER flutter create and BEFORE flutter build ios.
# This registers the fail-closed WireGuard fallback until official WireGuardKit
# and its wireguard-go-bridge are linked for a signed device build.
require 'xcodeproj'

project_file = File.expand_path('../ios/Runner.xcodeproj', __dir__)
raise "Flutter-generated Xcode project missing" unless File.directory?(project_file)
project = Xcodeproj::Project.open(project_file)
runner = project.targets.find { |t| t.name == 'Runner' }
raise 'No Runner target' unless runner
if project.targets.any? { |t| t.name == 'PacketTunnel' }
  puts 'PacketTunnel Xcode target already exists'
  exit 0
end

extension = project.new_target(:app_extension, 'PacketTunnel', :ios, '15.0')
extension.product_reference.name = 'PacketTunnel.appex'
extension.product_reference.path = 'PacketTunnel.appex'
extension.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['SWIFT_VERSION'] = '5.0'
  settings['IPHONEOS_DEPLOYMENT_TARGET'] = '15.0'
  settings['PRODUCT_BUNDLE_IDENTIFIER'] = 'com.twinpanel.twinconnect.PacketTunnel'
  settings['INFOPLIST_FILE'] = '../ios_native/PacketTunnel-Info.plist'
  settings['GENERATE_INFOPLIST_FILE'] = 'NO'
  settings['CODE_SIGN_ENTITLEMENTS'] = '../ios_native/PacketTunnel.entitlements'
  settings['APPLICATION_EXTENSION_API_ONLY'] = 'YES'
  settings['SKIP_INSTALL'] = 'YES'
  settings['TARGETED_DEVICE_FAMILY'] = '1,2'
  settings['CLANG_ENABLE_MODULES'] = 'YES'
  settings['CODE_SIGN_STYLE'] = 'Automatic'
end

files_group = project.main_group.new_group('TwinConnect Packet Tunnel', '../ios_native')
%w[PacketTunnelProvider.swift TwinConnectWireGuardEngine.swift].each do |file|
  reference = files_group.new_file(file)
  extension.source_build_phase.add_file_reference(reference)
end
info = files_group.new_file('PacketTunnel-Info.plist')
info.last_known_file_type = 'text.plist.xml'
entitlement = files_group.new_file('PacketTunnel.entitlements')
entitlement.last_known_file_type = 'text.plist.xml'

runner.add_dependency(extension)
embed = runner.new_copy_files_build_phase('Embed App Extensions')
embed.dst_subfolder_spec = '13' # PlugIns
embed.dst_path = ''
build_file = embed.add_file_reference(extension.product_reference)
build_file.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }

project.save
puts 'Created PacketTunnel Xcode target and embedded extension in Runner'
