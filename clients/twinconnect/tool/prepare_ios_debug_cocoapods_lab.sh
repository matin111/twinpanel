#!/bin/bash
# Generated debug-only lab checkout. Never use this as release preparation.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="$HOME/.gem/ruby/2.6.0/bin:/usr/local/bin:$PATH" LANG=en_US.UTF-8
test -f ios/Flutter/Generated.xcconfig
test -f .flutter-plugins-dependencies
python3 - <<'PY'
from pathlib import Path
import json
p=Path(".flutter-plugins-dependencies")
d=json.loads(p.read_text())
d.setdefault("swift_package_manager_enabled",{})["ios"]=False
p.write_text(json.dumps(d))
p=Path("ios/Podfile")
s=p.read_text().replace("# platform :ios, '15.0'", "platform :ios, '15.0'")
a=s.index("post_install do |installer|")
s=s[:a]+'''# Debug-only lab: no profile or release Flutter artifacts are installed.
post_install do |installer|
  debug_engine = File.join(flutter_root, 'bin/cache/artifacts/engine/ios/Flutter.xcframework')
  installer.pods_project.targets.each do |target|
    target.build_configurations.each do |config|
      next unless config.type == :debug
      s = config.build_settings
      s['IPHONEOS_DEPLOYMENT_TARGET'] = '15.0'
      s['ONLY_ACTIVE_ARCH'] = 'NO'
      s['CODE_SIGNING_ALLOWED'] = 'NO'
      s['CODE_SIGNING_REQUIRED'] = 'NO'
      next unless depends_on_flutter(target, 'Flutter')
      s['FRAMEWORK_SEARCH_PATHS[sdk=iphoneos*]'] = %Q("#{debug_engine}/ios-arm64" $(inherited))
      s['FRAMEWORK_SEARCH_PATHS[sdk=iphonesimulator*]'] = %Q("#{debug_engine}/ios-arm64_x86_64-simulator" $(inherited))
      s['OTHER_LDFLAGS'] = '$(inherited) -framework Flutter'
      s['CLANG_WARN_QUOTED_INCLUDE_IN_FRAMEWORK_HEADER'] = 'NO'
      s['ENABLE_BITCODE'] = 'NO'
    end
  end
end
'''
p.write_text(s)
PY
ruby -rxcodeproj -e '
p=Xcodeproj::Project.open("ios/Runner.xcodeproj")
r=p.targets.find{|t|t.name=="Runner"}
r.frameworks_build_phase.files.select{|f|f.product_ref&.product_name=="FlutterGeneratedPluginSwiftPackage"}.each(&:remove_from_project)
r.package_product_dependencies.select{|d|d.product_name=="FlutterGeneratedPluginSwiftPackage"}.each(&:remove_from_project)
p.root_object.package_references.select{|r|r.respond_to?(:relative_path)&&r.relative_path.include?("FlutterGeneratedPluginSwiftPackage")}.each(&:remove_from_project)
p.save
'
(cd ios && pod install --no-repo-update)
echo 'DEBUG LAB ONLY: regenerate normal Flutter iOS integration after installing complete engine artifacts.'
