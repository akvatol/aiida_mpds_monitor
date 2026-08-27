from types import SimpleNamespace
from unittest.mock import MagicMock

from aiida_mpds_monitor.daemon import filter_nodes_by_element_count


def _node(pk, label):
    return SimpleNamespace(pk=pk, label=label, process_label="BaseCrystalWorkChain")


def test_daemon_filter_keeps_only_nodes_matching_every_rule():
    logger = MagicMock()
    nodes = [
        _node(1, "BaMnO3/185: Geometry optimization"),
        _node(2, "HgI2/191: Geometry optimization"),
        _node(3, "BaPrMn2O6/123: Geometry optimization"),
    ]

    result = filter_nodes_by_element_count(
        nodes,
        allowed_counts={3, 4},
        logger=logger,
        greater_than=2,
        allowed_compounds={"BaMnO3", "BaPrMn2O6"},
        selected_elements={"Ba", "Mn"},
        elements_match="all",
    )

    assert result == [nodes[0], nodes[2]]
    logger.info.assert_called_once()
    assert logger.info.call_args.args[3] == nodes[1].label


def test_daemon_filter_returns_original_nodes_when_disabled():
    logger = MagicMock()
    nodes = [_node(1, "label without a formula")]

    result = filter_nodes_by_element_count(nodes, None, logger)

    assert result is nodes
    logger.info.assert_not_called()
