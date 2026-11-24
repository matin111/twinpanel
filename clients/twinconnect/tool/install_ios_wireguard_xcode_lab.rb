#!/usr/bin/env ruby
# Opt-in, generated Xcode project only. Device archive, not runtime readiness.
require 'xcodeproj'
require 'pathname'
root = File.expand_path('..', __dir__)
project_path = File.join(root, 'ios/Runner.xcodeproj')
p = Xcodeproj::Project.open(project_path)
t = p.targets.find { |target| target.name == 'PacketTunnel' } or abort 'PacketTunnel target missing'
rev = '2fec12a6e1f6e3460b6ee483aa00ad29cddadab1'
vendor = "../.dart_tool/ios-wireguard-lab/#{rev}/Sources"
out = '../build/ios-wireguard-lab/iphoneos'
%w[libwg-go.a kit/libWireGuardKit.a kit/key.o kit/x25519.o kit/WireGuardKit.swiftmodule].each do |f|
  abort "Missing library: #{f}" unless File.file?(File.expand_path("#{out}/#{f}", File.join(root,'ios')))
end
group = p.main_group.find_subpath('WireGuard Device Lab', true)
group.set_source_tree('SOURCE_ROOT')
group.set_path("#{out}/kit")
%w[TunnelConfiguration+WgQuickConfig.swift String+ArrayConversion.swift].each do |f|
  ref = group.files.find { |r| r.path == f } || group.new_file(f)
  t.source_build_phase.add_file_reference(ref, true) unless t.source_build_phase.files_references.include?(ref)
end
# Per-SDK conditions leave simulator fallback intact. No changes to entitlements
# or shipping readiness marker; the app must not advertise working VPN yet.
t.build_configurations.each do |c|
  s = c.build_settings
  base = '$(PROJECT_DIR)/'
  s['SWIFT_INCLUDE_PATHS[sdk=iphoneos*]'] = ['$(inherited)', "#{base}#{out}/kit", "#{base}#{vendor}/WireGuardKitC", "#{base}#{vendor}/WireGuardKitGo"]
  s['LIBRARY_SEARCH_PATHS[sdk=iphoneos*]'] = ['$(inherited)', "#{base}#{out}", "#{base}#{out}/kit"]
  s['OTHER_LDFLAGS[sdk=iphoneos*]'] = ['$(inherited)', '-lWireGuardKit', '-lwg-go', "#{base}#{out}/kit/key.o", "#{base}#{out}/kit/x25519.o"]
  s['EXCLUDED_SOURCE_FILE_NAMES[sdk=iphonesimulator*]'] = ['$(inherited)', 'TunnelConfiguration+WgQuickConfig.swift', 'String+ArrayConversion.swift']
end
p.save
puts 'Installed device-only WireGuard linkage in generated PacketTunnel target'
