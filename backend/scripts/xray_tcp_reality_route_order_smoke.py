"""Regression for Xray TCP REALITY service route after V87 and before V49."""
import ast
from pathlib import Path
from types import SimpleNamespace

root=Path(__file__).resolve().parents[1] / "app"
adaptive=(root/"xray_adaptive_three_profiles_v47.py").read_text("utf8")
runtime=(root/"self_hosted_runtime.py").read_text("utf8")
compile(adaptive,"xray_adaptive_three_profiles_v47.py","exec")
compile(runtime,"self_hosted_runtime.py","exec")

first=runtime.index("    apply_protocol_dataplane_desired_state_v87()")
middle=runtime.index("    reattach_service_routes_v47_after_v87()")
last=runtime.index("    apply_unified_l3_core_v49()")
assert first < middle < last

tree=ast.parse(adaptive)
func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=="reattach_service_routes_v47_after_v87")
func.returns=None
code=compile(ast.fix_missing_locations(ast.Module(body=[func],type_ignores=[])),"<test>","exec")

def final_authority(*args):return [{"protocol":"v2ray","public_port":24013}]
def v47_wrapper(*args):return [{"protocol":"v2ray","public_port":38013}]

tunnels=SimpleNamespace(_service_routes_for_exit=final_authority)
namespace={"tunnels":tunnels,"_service_routes_v47":v47_wrapper,"_original_service_routes":None}
exec(code,namespace)
namespace["reattach_service_routes_v47_after_v87"]()
assert tunnels._service_routes_for_exit is v47_wrapper
assert namespace["_original_service_routes"] is final_authority
namespace["reattach_service_routes_v47_after_v87"]()
assert namespace["_original_service_routes"] is final_authority
assert 'target_port": _tcp_reality_target_port(base_port)' in adaptive
assert "TCP_REALITY_PUBLIC_BASE = 38000" in adaptive
print("XRAY_TCP_REALITY_ROUTE_ORDER=PASS")
