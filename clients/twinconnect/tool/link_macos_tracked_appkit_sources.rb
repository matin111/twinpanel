#!/usr/bin/env ruby
# Relink existing native AppKit source references to the Git-tracked Swift
# implementations. The generated macOS Xcode project is intentionally not
# committed. Avoid accidentally compiling a stale copied dashboard.
require 'xcodeproj'

root = File.expand_path('..', __dir__)
project_path = File.join(root, 'macos/Runner.xcodeproj')
abort 'MACOS_XCODE_PROJECT_MISSING' unless Dir.exist?(project_path)
project = Xcodeproj::Project.open(project_path)
runner = project.targets.find { |target| target.name == 'Runner' }
abort 'RUNNER_TARGET_MISSING' unless runner

files = %w[TwinConnectMacOSNativeDashboard.swift TwinConnectMacOSNativeDirectory.swift]
changed = false
files.each do |name|
  source = File.join(root, 'macos_native', name)
  abort "TRACKED_APPKIT_SOURCE_MISSING: #{name}" unless File.file?(source)
  matches = runner.source_build_phase.files_references.select do |ref|
    ref && (ref.path.to_s.split('/').last == name || ref.name.to_s == name)
  end
  abort "APPKIT_NOT_IN_RUNNER_TARGET: #{name}" unless matches.length == 1
  reference = matches.first
  if reference.path != source || reference.source_tree != '<absolute>'
    reference.path = source
    reference.source_tree = '<absolute>'
    changed = true
  end
  puts "RUNNER_COMPILES_TRACKED_SOURCE: #{name}"
end

project.save if changed
puts changed ? 'RELINKED_TRACKED_APPKIT_SOURCES' : 'APPKIT_SOURCES_ALREADY_LINKED'
