from pathlib import Path

SOURCE = Path("components/tunnel-protocol-runtime-v307.tsx").read_text()

assert "TWINPANEL_NEW_NODE_TUNNEL_READINESS_V357" in SOURCE
assert 'const readyIranNodes=useMemo(()=>iranNodes.filter(node=>normalize(node.status)==="online")' in SOURCE
assert 'const readyExitNodes=useMemo(()=>exitNodes.filter(node=>normalize(node.status)==="online")' in SOURCE
assert "!readyIranNodes.some(node=>node.id===draft.iran_node_id)" in SOURCE
assert "!readyExitNodes.some(node=>node.id===draft.exit_node_id)" in SOURCE
assert "const iran=readyIranNodes[0]" in SOURCE
assert "const exit=readyExitNodes[0]" in SOURCE
assert "readyIranNodes.length===0||readyExitNodes.length===0" in SOURCE
assert ">{readyIranNodes.map(node=><option" in SOURCE
assert ">{readyExitNodes.map(node=><option" in SOURCE
assert ">{iranNodes.map(node=><option" not in SOURCE
assert ">{exitNodes.map(node=><option" not in SOURCE
assert '||iranNodes[0]' not in SOURCE
assert '||exitNodes[0]' not in SOURCE
print("NEW_NODE_TUNNEL_READINESS_V357_SMOKE_OK")
