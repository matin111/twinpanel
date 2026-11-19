#!/usr/bin/env ruby
# Compile-only native Libbox framework linkage in the generated PacketTunnel.
# Resolve the concrete macOS framework slice: passing only the XCFramework
# parent folder to -F does not make its embedded Swift/Clang module visible.
require 'xcodeproj'
require 'xcodeproj/plist'
root = File.expand_path('../..', __dir__)
project_file = File.join(root, 'macos/Runner.xcodeproj')
xcframework = File.join(root, 'macos_native/build/libbox/Libbox.xcframework')
plist_file = File.join(xcframework, 'Info.plist')
raise 'Generated macOS Xcode project missing' unless File.directory?(project_file)
raise 'Built Libbox XCFramework missing' unless File.file?(plist_file)

metadata = Xcodeproj::Plist.read_from_path(plist_file)
libraries = metadata.fetch('AvailableLibraries')
arm64 = libraries.find do |library|
  library['SupportedPlatform'] == 'macos' &&
    Array(library['SupportedArchitectures']).include?('arm64')
end
raise 'No macOS arm64 Libbox framework slice found' unless arm64
slice = File.join(xcframework, arm64.fetch('LibraryIdentifier'))
framework = File.join(slice, arm64.fetch('LibraryPath'))
raise 'Libbox.framework slice missing' unless File.directory?(framework)
raise 'Libbox module map missing' unless
  File.file?(File.join(framework, 'Modules/module.modulemap')) ||
  File.file?(File.join(framework, 'Versions/A/Modules/module.modulemap'))

project = Xcodeproj::Project.open(project_file)
target = project.targets.find { |t| t.name == 'PacketTunnel' }
raise 'PacketTunnel extension missing' unless target
group = project.main_group.find_subpath('TwinConnect Native Libbox', true)
group.set_source_tree('<group>')
ref = group.new_file(framework)
ref.source_tree = '<absolute>'
ref.last_known_file_type = 'wrapper.framework'
target.frameworks_build_phase.add_file_reference(ref)
# A successful Swift import is not enough for a dynamic framework: it must
# also travel inside PacketTunnel.appex/Contents/Frameworks at runtime.
embed = target.new_copy_files_build_phase('Embed Libbox Runtime')
embed.dst_subfolder_spec = '10' # Frameworks
embed.dst_path = ''
embedded = embed.add_file_reference(ref)
embedded.settings = { 'ATTRIBUTES' => ['CodeSignOnCopy', 'RemoveHeadersOnCopy'] }
target.build_configurations.each do |configuration|
  settings = configuration.build_settings
  settings['MACOSX_DEPLOYMENT_TARGET'] = '13.0'
  settings['FRAMEWORK_SEARCH_PATHS'] = ['$(inherited)', slice]
  settings['LIBRARY_SEARCH_PATHS'] = ['$(inherited)', slice]
  settings['LD_RUNPATH_SEARCH_PATHS'] = [
    '$(inherited)', '@executable_path/../Frameworks'
  ]
  # libbox's native macOS Go/C implementation references IOKit USB Host
  # controls and SystemConfiguration proxy/dynamic store symbols.
  # Explicitly link their Apple SDK frameworks into PacketTunnel.
  settings['OTHER_LDFLAGS'] = [
    '$(inherited)', '-framework', 'Libbox',
    '-framework', 'IOUSBHost',
    '-framework', 'SystemConfiguration',
    '-framework', 'IOKit'
  ]
end
probe = group.new_file(File.join(root, 'macos_native/libbox/LibboxLinkProbe.swift'))
probe.source_tree = '<absolute>'
target.source_build_phase.add_file_reference(probe)
project.save
puts "Linked and embedded macOS arm64 Libbox runtime framework: #{framework}"
