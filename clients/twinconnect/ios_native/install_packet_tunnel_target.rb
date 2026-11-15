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
  # Explicit product naming is required. With no PRODUCT_NAME Xcode
  # computes a bare ".appex" output for the new app-extension target,
  # which collides with the embed/copy phase during Flutter builds.
  settings['PRODUCT_NAME'] = 'PacketTunnel'
  settings['WRAPPER_EXTENSION'] = 'appex'
  # The extension has its own build settings; unlike the Runner target, it
  # does not inherit Flutter's generated version configuration. Leaving
  # MARKETING_VERSION / CURRENT_PROJECT_VERSION unset produces an invalid
  # Info.plist and iOS simctl install fails with IXErrorDomain code 2
  # ("Invalid placeholder attributes") despite a successful Xcode build.
  settings['MARKETING_VERSION'] = '0.1.0'
  settings['CURRENT_PROJECT_VERSION'] = '1'
  settings['DEVELOPMENT_LANGUAGE'] = 'en'
  settings['PRODUCT_MODULE_NAME'] = 'PacketTunnel'
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

runner.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['CODE_SIGN_ENTITLEMENTS'] = '../ios_native/Runner.entitlements'
  settings['INFOPLIST_KEY_TwinConnectKeychainAccessGroup'] =
    '$(AppIdentifierPrefix)com.twinpanel.twinconnect.shared'
end

runner.add_dependency(extension)
embed = runner.new_copy_files_build_phase('Embed App Extensions')
embed.dst_subfolder_spec = '13' # PlugIns
embed.dst_path = ''
build_file = embed.add_file_reference(extension.product_reference)
build_file.settings = { 'ATTRIBUTES' => ['RemoveHeadersOnCopy'] }

# Flutter's Runner target has a `Thin Binary` shell-script phase. Xcode's
# new build system reports a dependency cycle if `Embed App Extensions` is
# appended AFTER it (Copy .appex -> Thin Binary -> ProcessInfoPlist -> Copy).
# Order the extension copy phase BEFORE Thin Binary so there is no cycle.
thin_binary = runner.build_phases.find do |phase|
  phase.isa == 'PBXShellScriptBuildPhase' && phase.name == 'Thin Binary'
end
raise 'Flutter Runner Thin Binary build phase missing' unless thin_binary
phases = runner.build_phases
phases.delete(embed)
thin_index = phases.index(thin_binary)
raise 'Unable to locate Thin Binary in Runner build phases' unless thin_index
phases.insert(thin_index, embed)
raise 'Embed App Extensions must precede Thin Binary' unless
  runner.build_phases.index(embed) < runner.build_phases.index(thin_binary)

project.save
puts 'Created PacketTunnel Xcode target and embedded extension in Runner'
