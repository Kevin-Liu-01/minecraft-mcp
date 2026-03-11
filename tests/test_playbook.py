from minecraft_dedalus_mcp.models import BotStatus, InventoryEntry, Position
from minecraft_dedalus_mcp.playbook import recommend_goal


def test_recommend_goal_requires_connection() -> None:
    status = BotStatus(connected=False)
    recommendation = recommend_goal(status, "beat-minecraft")
    assert recommendation.phase == "connect"
    assert "join_game" in recommendation.suggested_tools


def test_recommend_goal_starts_with_wood() -> None:
    status = BotStatus(
        connected=True,
        mode="simulate",
        position=Position(x=0, y=64, z=0),
        inventory=[InventoryEntry(item="dirt", count=8)],
    )
    recommendation = recommend_goal(status, "beat-minecraft")
    assert recommendation.phase == "wood-age"
    assert "mine_resource" in recommendation.suggested_tools


def test_recommend_goal_reaches_final_phase() -> None:
    status = BotStatus(
        connected=True,
        mode="simulate",
        position=Position(x=0, y=64, z=0),
        inventory=[
            InventoryEntry(item="iron_pickaxe", count=1),
            InventoryEntry(item="blaze_rod", count=6),
            InventoryEntry(item="ender_pearl", count=12),
            InventoryEntry(item="eye_of_ender", count=12),
        ],
    )
    recommendation = recommend_goal(status, "beat-minecraft")
    assert recommendation.phase == "stronghold-and-dragon"
    assert "Enter the End" in " ".join(recommendation.checklist)

