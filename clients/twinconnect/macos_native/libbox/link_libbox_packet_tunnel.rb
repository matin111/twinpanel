#!/usr/bin/env ruby
# Compile-only native Libbox framework linkage in the generated PacketTunnel.
# Resolve the concrete macOS framework slice: passing only the XCFramework
# parent folder to -F does not make its embedded Swift/Clang module visible.
require 'xcodeproj'
require 'xcodeproj/plist'
require 'open3'
require 'tmpdir'
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

# The upstream sing-box gomobile Apple binding is a *static* framework:
# its framework executable contains a fat ar archive (with go.o members).
# A static library has no LC_ID_DYLIB and never appears in otool -L on
# PacketTunnel. Inspect an architecture-thinned slice instead of misreading
# otool -D output from archive members as a dynamic install name.
framework_binary = File.join(framework, 'Versions/A/Libbox')
raise 'Libbox static framework binary missing' unless File.file?(framework_binary)
arch_output, arch_status = Open3.capture2('xcrun', 'lipo', '-archs', framework_binary)
raise 'Unable to inspect Libbox CPU architectures' unless arch_status.success?
archs = arch_output.split
host_arch = `uname -m`.strip
raise "Libbox missing host architecture #{host_arch}: #{archs.join(', ')}" unless
  archs.include?(host_arch)
Dir.mktmpdir('twinconnect-libbox-inspect') do |dir|
  thin = File.join(dir, 'libbox-arch.a')
  raise 'Cannot inspect Libbox architecture slice' unless
    system('xcrun', 'lipo', '-thin', host_arch,
           framework_binary, '-output', thin)
  members, ar_status = Open3.capture2('xcrun', 'ar', '-t', thin)
  unless ar_status.success? && members.lines.any? { |name| name.strip == 'go.o' }
    raise 'Libbox is not the expected Go static archive; refusing dynamic-link assumptions'
  end
end
puts "Verified static Libbox framework (#{archs.join(', ')}; go.o archive)"

project = Xcodeproj::Project.open(project_file)
target = project.targets.find { |t| t.name == 'PacketTunnel' }
raise 'PacketTunnel extension missing' unless target
group = project.main_group.find_subpath('TwinConnect Native Libbox', true)
group.set_source_tree('<group>')

# Remove previous installer-owned link/copy entries. This is a static
# framework: it belongs in Link Binary With Libraries, NOT in
# PacketTunnel.appex/Contents/Frameworks. Embedding it duplicates the
# entire Go runtime and does not create a dynamic load command.
libbox_entry = lambda do |build_file|
  reference = build_file.file_ref
  reference && (reference.path.to_s.end_with?('/Libbox.framework') ||
    reference.path.to_s == 'Libbox.framework')
end

target.frameworks_build_phase.files.select(&libbox_entry).each(&:remove_from_project)
target.copy_files_build_phases.select do |phase|
  phase.name == 'Embed Libbox Runtime'
end.each(&:remove_from_project)

ref = group.files.find { |entry| entry.path == framework }
unless ref
  ref = group.new_file(framework)
  ref.source_tree = '<absolute>'
end
ref.last_known_file_type = 'wrapper.framework'
target.frameworks_build_phase.add_file_reference(ref)

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
  # The Go binding is a static archive. Linking the framework resolves
  # ObjC/Go symbols into PacketTunnel itself (no otool -L entry). Do not
  # use -needed_library, -needed_framework, or install_name_tool here.
  # Its macOS code also needs these Apple SDK frameworks.
  settings['OTHER_LDFLAGS'] = [
    '$(inherited)', '-framework', 'Libbox',
    '-framework', 'IOUSBHost',
    '-framework', 'SystemConfiguration',
    '-framework', 'IOKit'
  ]
end
project.save
puts "Linked static macOS Libbox into PacketTunnel target: #{framework}"
puts 'Static library: verify ObjC/Go symbols with nm, not otool -L.'
puts 'Unsigned compile is NOT a verified live VPN.'
