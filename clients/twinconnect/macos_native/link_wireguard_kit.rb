#!/usr/bin/env ruby
# Link the locally prepared WireGuardKit Swift package and the built Go archive
# into PacketTunnel. Idempotent; does NOT set signing or declare a working VPN.
require 'xcodeproj'
root = File.expand_path('..', __dir__)
project_path = File.join(root, 'macos/Runner.xcodeproj')
source = File.join(root, '.dart_tool/twinconnect-wireguard-apple')
archive = File.join(root, '.dart_tool/twinconnect-wireguard-build/lib/libwg-go.a')
abort 'ERROR: build libwg-go.a first' unless File.size?(archive)
abort 'ERROR: prepare upstream WireGuardKit source first' unless File.file?(File.join(source, 'Package.swift'))
project = Xcodeproj::Project.open(project_path)
extension = project.targets.find { |t| t.name == 'PacketTunnel' }
abort 'ERROR: PacketTunnel target missing; run install_packet_tunnel_target.rb first' unless extension
abort 'ERROR: installed xcodeproj gem does not support local Swift packages' unless defined?(Xcodeproj::Project::Object::XCLocalSwiftPackageReference)
relative = '../.dart_tool/twinconnect-wireguard-apple'
package = project.root_object.package_references.find do |p|
  p.isa == 'XCLocalSwiftPackageReference' && p.relative_path == relative
end
unless package
  package = project.new(Xcodeproj::Project::Object::XCLocalSwiftPackageReference)
  package.relative_path = relative
  project.root_object.package_references << package
end
unless extension.package_product_dependencies.any? { |p| p.product_name == 'WireGuardKit' }
  product = project.new(Xcodeproj::Project::Object::XCSwiftPackageProductDependency)
  product.product_name = 'WireGuardKit'
  product.package = package
  extension.package_product_dependencies << product
  phase = extension.frameworks_build_phase
  build_file = project.new(Xcodeproj::Project::Object::PBXBuildFile)
  build_file.product_ref = product
  phase.files << build_file
end
# Keep archive linker flags explicitly scoped to the extension, not Runner.
extension.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['MACOSX_DEPLOYMENT_TARGET'] = '12.0' # upstream WireGuardKit minimum macOS
  paths = Array(settings['LIBRARY_SEARCH_PATHS'])
  paths = ['$(inherited)'] if paths.empty?
  lib_path = '$(PROJECT_DIR)/../.dart_tool/twinconnect-wireguard-build/lib'
  paths << lib_path unless paths.include?(lib_path)
  settings['LIBRARY_SEARCH_PATHS'] = paths
  flags = Array(settings['OTHER_LDFLAGS'])
  flags = ['$(inherited)'] if flags.empty?
  flags << '-lwg-go' unless flags.include?('-lwg-go')
  settings['OTHER_LDFLAGS'] = flags
end
project.save
puts 'SUCCESS: WireGuardKit package and libwg-go.a linker settings added to PacketTunnel'
puts 'NOTE: This is an unsigned compile integration, not a working signed VPN.'
