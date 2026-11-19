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

# Apple's runtime loader must resolve the framework inside PacketTunnel.appex,
# not a machine-specific Xcode DerivedData path. Correct only the generated
# local XCFramework binary, before Xcode copies/signs the extension bundle.
framework_binary = File.join(framework, 'Versions/A/Libbox')
abort('Libbox dynamic library missing') unless File.file?(framework_binary)
portable_id = '@rpath/Libbox.framework/Versions/A/Libbox'
existing_id_output = IO.popen(['xcrun', 'otool', '-D', framework_binary], &:read)
abort('Unable to read Libbox dylib install name') unless $?.success?
existing_id = existing_id_output.lines.map(&:strip).reject(&:empty?)[1]
abort('Libbox is missing LC_ID_DYLIB') unless existing_id
unless existing_id == portable_id
  abort('Failed to set portable Libbox install name') unless
    system('xcrun', 'install_name_tool', '-id', portable_id, framework_binary)
  puts "Adjusted local Libbox install name: #{portable_id}"
end

project = Xcodeproj::Project.open(project_file)
target = project.targets.find { |t| t.name == 'PacketTunnel' }
raise 'PacketTunnel extension missing' unless target
group = project.main_group.find_subpath('TwinConnect Native Libbox', true)
group.set_source_tree('<group>')

# Re-running the installer must not create multiple build tasks that copy
# Libbox.framework to the same PacketTunnel.app extension destination.
# Remove only installer-owned Libbox entries, preserving other dependencies.
libbox_entry = lambda do |build_file|
  reference = build_file.file_ref
  reference && (reference.path.to_s.end_with?('/Libbox.framework') ||
    reference.path.to_s == 'Libbox.framework')
end

target.frameworks_build_phase.files.select(&libbox_entry).each(&:remove_from_project)
embed_phases = target.copy_files_build_phases.select do |phase|
  phase.name == 'Embed Libbox Runtime'
end
embed_phases.each do |phase|
  phase.files.select(&libbox_entry).each(&:remove_from_project)
end
embed = embed_phases.shift || target.new_copy_files_build_phase('Embed Libbox Runtime')
embed_phases.each(&:remove_from_project)
embed.dst_subfolder_spec = '10' # Frameworks
embed.dst_path = ''

ref = group.files.find { |entry| entry.path == framework }
unless ref
  ref = group.new_file(framework)
  ref.source_tree = '<absolute>'
end
ref.last_known_file_type = 'wrapper.framework'
target.frameworks_build_phase.add_file_reference(ref)
embedded = embed.add_file_reference(ref)
embedded.settings = { 'ATTRIBUTES' => ['CodeSignOnCopy', 'RemoveHeadersOnCopy'] }

probe_path = File.join(root, 'macos_native/libbox/LibboxLinkProbe.swift')
# Some generated Xcode projects store the reference as a relative path,
# and older installer runs may have created multiple references to this file.
# Match the leaf name (only inside PacketTunnel's Compile Sources phase) so
# a rerun removes every duplicate build file, regardless of reference style.
target.source_build_phase.files.select do |build_file|
  reference = build_file.file_ref
  reference && File.basename(reference.path.to_s) == 'LibboxLinkProbe.swift'
end.each(&:remove_from_project)
probe = group.files.find do |entry|
  File.basename(entry.path.to_s) == 'LibboxLinkProbe.swift'
end
unless probe
  probe = group.new_file(probe_path)
end
probe.source_tree = '<absolute>'
probe.path = probe_path
target.source_build_phase.add_file_reference(probe)

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
  # Force-link the concrete dylib rather than depending on framework name
  # lookup or Swift's imported-symbol reachability. The binary's LC_ID_DYLIB
  # is portable (@rpath), so the resulting LC_LOAD_DYLIB must also be portable.
  settings['OTHER_LDFLAGS'] = [
    '$(inherited)', "-Wl,-needed_library,#{framework_binary}",
    '-framework', 'IOUSBHost',
    '-framework', 'SystemConfiguration',
    '-framework', 'IOKit'
  ]
end
project.save
puts "Linked and embedded macOS arm64 Libbox runtime framework: #{framework}"
