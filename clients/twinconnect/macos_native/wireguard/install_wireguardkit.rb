#!/usr/bin/env ruby
# WireGuardKit local-package installer for generated Flutter macOS Xcode project.
# Official wireguard-apple currently declares swift-tools-version 5.3 although
# Package.swift uses .macOS(.v12) / .iOS(.v15), which require 5.5+.
# Clone the official source into ignored local build/, patch ONLY that manifest
# header, then refer to the local Swift package. No server data is touched.
require 'xcodeproj'
require 'fileutils'

root = File.expand_path('../..', __dir__)
project_path = File.join(root, 'macos/Runner.xcodeproj')
source_path = File.join(root, 'macos_native/build/wireguard-apple')
manifest_path = File.join(source_path, 'Package.swift')
abort('Generated Runner.xcodeproj missing') unless File.directory?(project_path)

unless File.file?(manifest_path)
  FileUtils.mkdir_p(File.dirname(source_path))
  ok = system('git', 'clone', '--depth', '1', '--branch', 'master',
              'https://github.com/WireGuard/wireguard-apple.git', source_path)
  abort('WireGuard upstream clone failed; Xcode project unchanged') unless ok && File.file?(manifest_path)
end
manifest = File.binread(manifest_path)
if manifest.start_with?("// swift-tools-version:5.3\n")
  File.binwrite(manifest_path, manifest.sub("// swift-tools-version:5.3\n",
                                            "// swift-tools-version:5.5\n"))
elsif !manifest.match?(/\A\/\/ swift-tools-version:5\.[5-9]/)
  abort('Unexpected WireGuard Package.swift header; Xcode project unchanged')
end

project = Xcodeproj::Project.open(project_path)
extension = project.targets.find { |t| t.name == 'PacketTunnel' }
app = project.targets.find { |t| t.name == 'Runner' }
abort('PacketTunnel and Runner targets must be installed first') unless extension && app

# The relative path is resolved from macos/Runner.xcodeproj.
relative_path = '../../macos_native/build/wireguard-apple'
references = project.root_object.package_references
package = references.find do |ref|
  ref.isa == 'XCLocalSwiftPackageReference' && ref.relative_path == relative_path
end
unless package
  package = project.new(Xcodeproj::Project::Object::XCLocalSwiftPackageReference)
  package.relative_path = relative_path
  references << package
end
[app, extension].each do |target|
  products = target.package_product_dependencies.select { |p| p.product_name == 'WireGuardKit' }
  product = products.first
  unless product
    product = project.new(Xcodeproj::Project::Object::XCSwiftPackageProductDependency)
    product.product_name = 'WireGuardKit'
    target.package_product_dependencies << product
  end
  product.package = package
  products.drop(1).each do |duplicate|
    target.package_product_dependencies.delete(duplicate)
    duplicate.remove_from_project
  end
  unless target.frameworks_build_phase.files.any? { |f| f.respond_to?(:product_ref) && f.product_ref == product }
    build_file = project.new(Xcodeproj::Project::Object::PBXBuildFile)
    build_file.product_ref = product
    target.frameworks_build_phase.files << build_file
  end
end

# Remove stale remote WireGuard references introduced by an earlier installer.
references.select do |ref|
  ref.isa == 'XCRemoteSwiftPackageReference' &&
    ref.repositoryURL.to_s.include?('wireguard-apple')
end.each do |ref|
  references.delete(ref)
  ref.remove_from_project
end

bridge = project.targets.find { |t| t.name == 'WireGuardGoBridgemacOS' }
working_dir = '$(SRCROOT)/../macos_native/build/wireguard-apple/Sources/WireGuardKitGo'
unless bridge
  bridge = Xcodeproj::Project::ProjectHelper.new_legacy_target(
    project, 'WireGuardGoBridgemacOS', '/usr/bin/make',
    'build', working_dir, '1'
  )
end
bridge.build_tool_path = '/usr/bin/make'
bridge.build_arguments_string = 'build'
bridge.build_working_directory = working_dir
bridge.build_configurations.each do |config|
  config.build_settings['SDKROOT'] = 'macosx'
  config.build_settings['ARCHS'] = 'x86_64'
end
extension.add_dependency(bridge) unless extension.dependencies.any? { |dep| dep.target == bridge }

# A WireGuardKitGo product links against libwg-go.a; the legacy target builds it
# under the active Xcode configuration's product dir.
extension.build_configurations.each do |configuration|
  settings = configuration.build_settings
  current = Array(settings['LIBRARY_SEARCH_PATHS'])
  needed = ['$(inherited)', '$(CONFIGURATION_BUILD_DIR)']
  settings['LIBRARY_SEARCH_PATHS'] = (current + needed).uniq
end

project.save
puts 'WireGuardKit local source prepared (Swift tools 5.5) and registered.'
puts 'WireGuardGoBridgemacOS uses official Go bridge Makefile.'
puts 'Next: run xcodebuild -resolvePackageDependencies, then unsigned build.'
puts 'Runtime VPN still requires signed Network Extension entitlement.'
