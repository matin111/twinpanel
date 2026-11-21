#!/usr/bin/env ruby
# Opt-in real WireGuardKit linking test for generated macOS Xcode projects.
# Run after install_packet_tunnel_target.rb, never in the unsigned UI preview.
require 'xcodeproj'
project_path = File.expand_path('../macos/Runner.xcodeproj', __dir__)
raise 'Missing Flutter macOS project' unless File.directory?(project_path)
project = Xcodeproj::Project.open(project_path)
extension = project.targets.find { |t| t.name == 'PacketTunnel' }
raise 'PacketTunnel target not installed' unless extension
raise 'WireGuardKit already linked' if extension.package_product_dependencies.any? { |p| p.product_name == 'WireGuardKit' }

pkg = project.new(Xcodeproj::Project::Object::XCLocalSwiftPackageReference)
# Official upstream source is pinned and locally patched ONLY for SwiftPM
# manifest compatibility. CI must verify commit SHA before using this path.
pkg.relative_path = '../macos_native/vendor-wireguard-apple'
project.root_object.package_references << pkg
product = project.new(Xcodeproj::Project::Object::XCSwiftPackageProductDependency)
product.product_name = 'WireGuardKit'
product.package = pkg
extension.package_product_dependencies << product
reference = project.new(Xcodeproj::Project::Object::PBXBuildFile)
reference.product_ref = product
extension.frameworks_build_phase.files << reference
extension.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['MACOSX_DEPLOYMENT_TARGET'] = '12.0'
  # libwg-go.a is built by the official WireGuard Makefile before Xcode build.
  settings['LIBRARY_SEARCH_PATHS'] =
    ['$(inherited)', '$(PROJECT_DIR)/../macos_native/build/wireguard']
end
project.save
puts 'WireGuardKit package and archive search path linked to macOS PacketTunnel'
