"""Execute the actual Swift resolver with synthetic, non-secret profiles."""
import pathlib
import subprocess
import tempfile
import unittest

class WireGuardProfileSelectionTests(unittest.TestCase):
    def test_actual_resolver(self):
        source=pathlib.Path(__file__).with_name("TwinConnectMacOSNativeDirectory.swift").read_text()
        start=source.index("    private static func resolveWireGuardProfile(")
        end=source.index("    func prepareWireGuardProfile(",start)
        resolver=source[start:end].replace("private static func","static func",1)
        script="import Foundation\nstruct Resolver {\n"+resolver+"\n}\n"+r"""
let raw = "[Interface]\nPrivateKey = synthetic-not-a-real-key\nAddress = 10.0.0.2/32\n[Peer]\nPublicKey = synthetic\nEndpoint = example.invalid:51820\n"
let selected: [String:Any] = ["id":"25","country_code":"DE","node_online":true]
let alternative: [String:Any] = ["id":28,"country_code":"de","node_online":true,"latency_ms":15]
let offline: [String:Any] = ["id":"31","country_code":"DE","node_online":false,"latency_ms":1]
let other: [String:Any] = ["id":"40","country_code":"FR","node_online":true,"latency_ms":1]
let servers = [selected,alternative,offline,other]
func item(_ id:Any, _ config:String = raw, _ format:String = "wireguard") -> [String:Any] {
    ["node_id":id,"config":config,"config_format":format]
}
func select(_ rows:[[String:Any]], _ protocolCode:String = "wireguard", _ nodes:[[String:Any]] = servers) -> (id:String?,raw:String?,reason:String) {
    Resolver.resolveWireGuardProfile(servers:nodes,items:rows,serverID:"25",protocolCode:protocolCode)
}
precondition(select([item(25),item(28)]).id == "25")
precondition(select([item(28),item(31),item(40)]).id == "28")
precondition(select([item(31),item(40)]).reason == "WG_SERVER_PROFILE_MISSING")
precondition(select([item(25,"bad"),item(28)]).reason == "WG_SERVER_PROFILE_INVALID")
precondition(select([item(25),item("25"),item(28)]).reason == "WG_DUPLICATE_SERVER_PROFILE")
precondition(select([item(28),item("28")]).id == nil)
precondition(select([item(28)],"amneziawg").id == nil)
precondition(select([item(28,raw,"amneziawg")],"amneziawg").id == "28")
precondition(select([item(28)],"wireguard",[selected,alternative,alternative]).id == nil)
print("9 Swift resolver cases passed")
"""
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/"resolver.swift"
            path.write_text(script)
            result=subprocess.run(["xcrun","swift",str(path)],capture_output=True,text=True,timeout=30)
            self.assertEqual(result.returncode,0,result.stderr[-3000:])
            self.assertIn("9 Swift resolver cases passed",result.stdout)

if __name__=="__main__": unittest.main()
