#!/usr/bin/env ruby
# Register the official WireGuardKit Swift package and macOS Go bridge.
#
# Run after flutter create and install_packet_tunnel_target.rb.
# This edits the locally generated Xcode project, NOT server profiles.
# It does not bypass Network Extension code-signing requirements.
require 'xcodeproj'

root = File.expand_path('../..', __dir__)
project_path = File.join(root, 'macos/Runner.xcodeproj')
abort('Generated Runner.xcodeproj missing') unless File.directory?(project_path)
project = Xcodeproj::Project.open(project_path)
extension = project.targets.find { |target| target.name == 'PacketTunnel' }
app = project.targets.find { |target| target.name == 'Runner' }
abort('PacketTunnel and Runner targets must be installed first') unless extension && app

repo_url = 'https://github.com/WireGuard/wireguard-apple'
package = project.root_object.package_references.find do |reference|
  reference.isa == 'XCRemoteSwiftPackageReference' &&
    reference.repositoryURL == repo_url
end
unless package
  package = project.new(Xcodeproj::Project::Object::XCRemoteSwiftPackageReference)
  package.repositoryURL = repo_url
  package.requirement = { 'kind' => 'branch', 'branch' => 'master' }
  project.root_object.package_references << package
end

[app, extension].each do |target|
  product = target.package_product_dependencies.find do |dependency|
    dependency.product_name == 'WireGuardKit'
  end
  unless product
    product = project.new(Xcodeproj::Project::Object::XCSwiftPackageProductDependency)
    product.product_name = 'WireGuardKit'
    product.package = package
    target.package_product_dependencies << product
  end
  unless target.frameworks_build_phase.files.any? do |file|
      file.respond_to?(:product_ref) &&
        file.product_ref == product
    end
    file = project.new(Xcodeproj::Project::Object::PBXBuildFile)
    file.product_ref = product
    target.frameworks_build_phase.files << file
  end
end

# Official upstream WireGuardKit needs a separate native Go archive build:
# https://github.com/WireGuard/wireguard-apple#wireguardkit-integration
bridge = project.targets.find { |target| target.name == 'WireGuardGoBridgemacOS' }
unless bridge
  bridge = project.new(Xcodeproj::Project::Object::PBXLegacyTarget)
  bridge.name = 'WireGuardGoBridgemacOS'
  bridge.build_tool_path = '/usr/bin/make'
  bridge.build_arguments_string = ''
  bridge.build_working_directory =
    '${BUILD_DIR%Build/*}SourcePackages/checkouts/wireguard-apple/Sources/WireGuardKitGo'
  bridge.pass_build_settings_in_environment = '1'
  %w[Debug Profile Release].each do |name|
    config = bridge.add_build_configuration(name, :release)
    config.build_settings['SDKROOT'] = 'macosx'
  end
end
extension.add_dependency(bridge) unless extension.dependencies.any? do |dependency|
  dependency.target == bridge
end

project.save
puts 'Registered official WireGuardKit package + WireGuardGoBridgemacOS target.'
puts 'Xcode will resolve package and build Go bridge during the next build.'
puts 'This does not verify signed Network Extension or successful VPN traffic.'
